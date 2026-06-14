#!/usr/bin/env python3
"""
Insert data from FAISS indices to Qdrant

Sequential insertion from unmerged FAISS files to Qdrant collection.
Designed for HPC cluster environment with Singularity-based Qdrant server.

Uses document unique IDs (PMID for PubMed, NCT ID for Clinical Trials) as Qdrant point IDs
to enable proper upsert behavior for incremental updates.

Usage:
    python insert_from_faiss.py --faiss-dir /path/to/processed \
                                 --collection collection_name \
                                 --qdrant-url http://nodeXXX:6333 \
                                 --batch-size 1000
"""

import os
import sys
import argparse
import pickle
import gc
import time
import hashlib
from glob import glob
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np
import psutil
import requests
from tqdm import tqdm
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

def log_with_timestamp(message: str) -> None:
    """Prints a message with timestamp and memory usage."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
    log_line = f"[{timestamp}] [MEM: {memory_mb:.1f}MB] {message}"
    print(log_line, flush=True)

def get_qdrant_telemetry(qdrant_url: str) -> dict:
    """
    Get Qdrant server telemetry metrics.

    Args:
        qdrant_url: Qdrant server URL

    Returns:
        Dictionary with telemetry metrics, or empty dict if unavailable
    """
    try:
        response = requests.get(f"{qdrant_url}/telemetry", timeout=5)
        if response.status_code == 200:
            data = response.json()

            # Extract key metrics
            metrics = {}

            # Memory metrics (in MB)
            if 'app' in data and 'memory' in data['app']:
                memory = data['app']['memory']
                metrics['memory_used_mb'] = memory.get('used_bytes', 0) / 1024 / 1024
                metrics['memory_total_mb'] = memory.get('total_bytes', 0) / 1024 / 1024

            # Collection count
            if 'collections' in data:
                metrics['collections_count'] = len(data['collections'])

            return metrics
        else:
            return {}
    except Exception as e:
        # Silent fail - telemetry is optional
        return {}

def get_point_id_from_metadata(meta: dict, fallback_id: int) -> int:
    """
    Extract point ID from metadata using document unique identifiers.

    Priority order:
    1. pmid (PubMed) - use directly as integer
    2. nct_id (Clinical Trials) - hash to integer (NCT IDs are alphanumeric)
    3. patent_id (Patents) - hash to integer (Patent IDs are alphanumeric)
    4. surechembl_id (Patent Compounds) - hash to integer (SureChEMBL IDs are alphanumeric)
    5. fallback_id - sequential ID for backward compatibility

    Args:
        meta: Metadata dictionary
        fallback_id: Fallback sequential ID

    Returns:
        Integer point ID for Qdrant
    """
    # Try PMID first (PubMed)
    if 'pmid' in meta:
        try:
            return int(meta['pmid'])
        except (ValueError, TypeError):
            log_with_timestamp(f"  └─ WARNING: Invalid PMID '{meta.get('pmid')}', using fallback ID")
            return fallback_id

    # Try NCT ID (Clinical Trials) — MULTI-CHUNK.
    # A trial yields several section chunks (summary / primary_outcome /
    # secondary_outcome / eligibility / description...). chunk_id is NOT unique within a
    # trial (summary, primary_outcome, secondary_outcome all use chunk_id=0), so we key on
    # the per-file global_chunk_id running counter to give each SECTION a distinct point.
    # (Falls back to chunk_type:chunk_id, then bare nct_id.) Pair with insert --update-mode,
    # which deletes ALL of a trial's old points by nct_id payload filter before re-inserting,
    # so refreshes stay consistent even though these ids differ from the legacy hash(nct_id).
    if 'nct_id' in meta:
        nct_id = str(meta['nct_id'])
        disc = meta.get('global_chunk_id')
        if disc is None:
            ct, ci = meta.get('chunk_type'), meta.get('chunk_id')
            disc = f"{ct}:{ci}" if ct is not None or ci is not None else None
        key = f"{nct_id}:{disc}" if disc is not None else nct_id
        hash_bytes = hashlib.sha256(key.encode()).digest()[:8]
        point_id = int.from_bytes(hash_bytes, byteorder='big', signed=False)
        # Ensure positive and within reasonable range (Qdrant uses unsigned 64-bit)
        return point_id & 0x7FFFFFFFFFFFFFFF  # Ensure positive 63-bit number

    # Try Patent ID (Patents text)
    if 'patent_id' in meta:
        patent_id = str(meta['patent_id'])
        # Hash patent ID to get consistent integer
        hash_bytes = hashlib.sha256(patent_id.encode()).digest()[:8]
        point_id = int.from_bytes(hash_bytes, byteorder='big', signed=False)
        return point_id & 0x7FFFFFFFFFFFFFFF  # Ensure positive 63-bit number

    # Try SureChEMBL ID (Patent compounds)
    if 'surechembl_id' in meta:
        surechembl_id = str(meta['surechembl_id'])
        # Hash SureChEMBL ID to get consistent integer
        hash_bytes = hashlib.sha256(surechembl_id.encode()).digest()[:8]
        point_id = int.from_bytes(hash_bytes, byteorder='big', signed=False)
        return point_id & 0x7FFFFFFFFFFFFFFF  # Ensure positive 63-bit number

    # Try Protein ID (ESM-2 proteins) - UniProt accession, alphanumeric
    # NOTE: the original 573K esm2 points predate this case and were inserted
    # with sequential fallback IDs (0..N). Hash IDs land in the ~10^18 range, so
    # they CANNOT collide with that low sequential block -> additive delta inserts
    # of NEW proteins are safe, and become idempotent (protein_id -> fixed point).
    if 'protein_id' in meta:
        protein_id = str(meta['protein_id'])
        hash_bytes = hashlib.sha256(protein_id.encode()).digest()[:8]
        point_id = int.from_bytes(hash_bytes, byteorder='big', signed=False)
        return point_id & 0x7FFFFFFFFFFFFFFF  # Ensure positive 63-bit number

    # No unique ID found, use fallback
    return fallback_id

def upsert_with_retry(client: QdrantClient, collection_name: str, points: list,
                      max_retries: int = 5, initial_delay: float = 2.0) -> bool:
    """
    Upsert points with exponential backoff retry on WAL errors.

    Args:
        client: Qdrant client
        collection_name: Collection to insert into
        points: List of PointStruct to insert
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds (doubles each retry)

    Returns:
        True if successful, False otherwise
    """
    delay = initial_delay

    for attempt in range(max_retries):
        try:
            client.upsert(collection_name=collection_name, points=points)
            return True

        except UnexpectedResponse as e:
            error_msg = str(e)

            # Extract detailed error from response if available
            if hasattr(e, 'content'):
                log_with_timestamp(f"  └─ Response content: {e.content}")

            # Check if it's a WAL-related error
            if "WAL" in error_msg or "segment creator" in error_msg:
                if attempt < max_retries - 1:
                    log_with_timestamp(f"  └─ WAL/segment error (attempt {attempt + 1}/{max_retries}): {error_msg}")
                    log_with_timestamp(f"  └─ Waiting {delay:.1f}s before retry...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                    continue
                else:
                    log_with_timestamp(f"  └─ FAILED after {max_retries} attempts")
                    log_with_timestamp(f"  └─ ERROR: {error_msg}")
                    log_with_timestamp(f"  └─ HINT: Qdrant server may need restart or storage cleanup")
                    return False
            else:
                # Non-WAL error, don't retry
                log_with_timestamp(f"  └─ Non-recoverable error: {error_msg}")
                return False

        except Exception as e:
            log_with_timestamp(f"  └─ ERROR: {type(e).__name__}: {e}")
            return False

    return False

def create_collection_if_needed(client: QdrantClient, collection_name: str,
                                 vector_size: int = 768, enable_quantization: bool = True,
                                 hnsw_m: int = 16, hnsw_ef_construct: int = 100,
                                 max_segment_size: int = 2_000_000,
                                 default_segment_number: int = 2,
                                 indexing_threshold: int = 1_000_000) -> None:
    """Create Qdrant collection if it doesn't exist.

    Args:
        client: Qdrant client
        collection_name: Collection name
        vector_size: Vector dimension
        enable_quantization: Enable scalar quantization (default: True, recommended for large collections)
        hnsw_m: HNSW m parameter (graph connectivity, default: 16)
        hnsw_ef_construct: HNSW ef_construct parameter (build quality, default: 100)
        max_segment_size: Maximum segment size in points (default: 2_000_000)
        default_segment_number: Default number of segments (default: 2, set to 0 for dynamic)
        indexing_threshold: Minimum points before indexing starts (default: 1_000_000, higher = fewer segments)
    """
    try:
        client.get_collection(collection_name)
        log_with_timestamp(f"Collection '{collection_name}' already exists")
    except Exception:
        log_with_timestamp(f"Creating collection '{collection_name}'...")

        # Prepare quantization config if enabled
        quantization_config = None
        if enable_quantization:
            log_with_timestamp(f"  ✓ Scalar quantization ENABLED (int8, quantile=0.99)")
            quantization_config = models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(
                    type=models.ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True
                )
            )
        else:
            log_with_timestamp(f"  ⚠ Quantization DISABLED")

        log_with_timestamp(f"  HNSW config: m={hnsw_m}, ef_construct={hnsw_ef_construct}")
        log_with_timestamp(f"  Segment config: default_segment_number={default_segment_number}, max_segment_size={max_segment_size:,} points")
        log_with_timestamp(f"  Indexing threshold: {indexing_threshold:,} points (higher = fewer segments during bulk insert)")

        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            ),
            # Optimize for large datasets with better WAL handling
            hnsw_config=models.HnswConfigDiff(
                m=hnsw_m,
                ef_construct=hnsw_ef_construct,
                full_scan_threshold=10000
            ),
            optimizers_config=models.OptimizersConfigDiff(
                deleted_threshold=0.2,
                vacuum_min_vector_number=1000,
                default_segment_number=default_segment_number,
                max_segment_size=max_segment_size,
                memmap_threshold=500_000,     # Lower threshold for memory mapping
                indexing_threshold=indexing_threshold,  # Configurable indexing threshold
                flush_interval_sec=30         # Flush WAL more frequently (every 30 seconds)
            ),
            # Explicitly set WAL config for NFS environments
            wal_config=models.WalConfigDiff(
                wal_capacity_mb=256,          # Limit WAL size to 256MB
                wal_segments_ahead=2          # Keep fewer WAL segments ahead
            ),
            # Add quantization config if enabled
            quantization_config=quantization_config
        )
        log_with_timestamp(f"Collection '{collection_name}' created with quantization={enable_quantization}")

def find_faiss_files(faiss_dir: str) -> list:
    """Find all FAISS index files in directory."""
    pattern = os.path.join(faiss_dir, "**", "*.index")
    files = sorted(glob(pattern, recursive=True))
    return files

def map_faiss_to_source_file(index_path: str, faiss_dir: str) -> str:
    """
    Map a FAISS index file path to its source XML filename for tracking.

    Args:
        index_path: Full path to FAISS index (e.g., /path/to/processed/pubmed/baseline/pubmed25n0001.index)
        faiss_dir: Base FAISS directory (e.g., /path/to/processed/pubmed)

    Returns:
        Relative source filename (e.g., "baseline/pubmed25n0001.xml.gz")
    """
    # Get relative path from faiss_dir
    rel_path = os.path.relpath(index_path, faiss_dir)

    # Extract subdirectory and basename
    # e.g., "baseline/pubmed25n0001.index" -> ("baseline", "pubmed25n0001.index")
    parts = rel_path.split(os.sep)
    subdir = parts[0] if len(parts) > 1 else ""
    basename = os.path.basename(index_path)

    # Convert .index to .xml.gz
    # e.g., "pubmed25n0001.index" -> "pubmed25n0001.xml.gz"
    source_basename = basename.replace('.index', '.xml.gz')

    # Combine subdir and basename
    if subdir:
        return f"{subdir}/{source_basename}"
    else:
        return source_basename

def load_faiss_and_metadata(index_path: str) -> tuple:
    """Load FAISS index and corresponding metadata.

    Expects consistent naming: file.index + file.json (dict format with string keys)
    Falls back to file_metadata.pkl for legacy data.
    """
    index = faiss.read_index(index_path)

    # Try .json first (standard format for both PubMed and Clinical Trials)
    metadata_path_json = index_path.replace('.index', '.json')
    metadata_path_pkl = index_path.replace('.index', '_metadata.pkl')

    if os.path.exists(metadata_path_json):
        import json
        with open(metadata_path_json, 'r') as f:
            metadata = json.load(f)
    elif os.path.exists(metadata_path_pkl):
        with open(metadata_path_pkl, 'rb') as f:
            metadata = pickle.load(f)
    else:
        raise FileNotFoundError(f"Metadata not found: tried {metadata_path_json} and {metadata_path_pkl}")

    return index, metadata

def wait_for_green_status(client: QdrantClient, collection_name: str) -> tuple:
    """
    Wait for collection to reach GREEN status after insertion.

    After bulk insertion, Qdrant needs time to optimize and index vectors.
    Status transitions: YELLOW (optimizing) → GREEN (ready for queries)

    Args:
        client: Qdrant client
        collection_name: Collection name

    Returns:
        Tuple of (status, wait_time_seconds)
    """
    log_with_timestamp("")
    log_with_timestamp("="*80)
    log_with_timestamp("WAITING FOR COLLECTION OPTIMIZATION")
    log_with_timestamp("="*80)
    log_with_timestamp("Collection is optimizing in background (HNSW indexing, segment merging)")
    log_with_timestamp("This is normal after bulk insertion - wait for GREEN status before queries")
    log_with_timestamp("")

    wait_time = 0
    check_interval = 5  # Check every 5 seconds
    log_interval = 30   # Log every 30 seconds
    last_log_time = 0

    while True:
        try:
            info = client.get_collection(collection_name)
            status = info.status

            # Get additional info for logging
            points_count = info.points_count if hasattr(info, 'points_count') else 0
            indexed_count = info.indexed_vectors_count if hasattr(info, 'indexed_vectors_count') else 0
            segments_count = info.segments_count if hasattr(info, 'segments_count') else 0

            if status == "green":
                log_with_timestamp("")
                log_with_timestamp(f"✓ Collection is GREEN after {wait_time}s")
                log_with_timestamp(f"  Points: {points_count:,}")
                log_with_timestamp(f"  Indexed: {indexed_count:,} ({indexed_count/points_count*100:.1f}%)" if points_count > 0 else "  Indexed: N/A")
                log_with_timestamp(f"  Segments: {segments_count}")
                log_with_timestamp(f"  Collection is ready for queries!")
                return (status, wait_time)

            # Log status periodically
            if wait_time - last_log_time >= log_interval or wait_time == 0:
                indexed_pct = (indexed_count/points_count*100) if points_count > 0 else 0

                # Get telemetry for memory info
                from urllib.parse import urlparse
                base_url = f"{urlparse(client._client.rest_uri).scheme}://{urlparse(client._client.rest_uri).netloc}"
                telemetry = get_qdrant_telemetry(base_url)
                memory_info = ""
                if telemetry and 'memory_used_mb' in telemetry:
                    memory_info = f" | Memory: {telemetry['memory_used_mb']:.1f}MB"

                log_with_timestamp(f"⏳ Status: {status.upper()} | Waiting: {wait_time}s | Points: {points_count:,} | Indexed: {indexed_pct:.1f}% | Segments: {segments_count}{memory_info}")
                last_log_time = wait_time

            # Wait before next check
            time.sleep(check_interval)
            wait_time += check_interval

        except Exception as e:
            log_with_timestamp(f"⚠ Error checking status: {e}")
            log_with_timestamp(f"  Retrying in {check_interval}s...")
            time.sleep(check_interval)
            wait_time += check_interval
            continue

def delete_trial_vectors(client: QdrantClient, collection_name: str, nct_ids: list) -> int:
    """
    Delete all vectors for given NCT IDs from the collection.

    This is used in update mode to remove old vectors before inserting updated trials.

    Args:
        client: Qdrant client
        collection_name: Collection name
        nct_ids: List of NCT IDs to delete

    Returns:
        Number of NCT IDs processed for deletion
    """
    deleted_count = 0

    for nct_id in nct_ids:
        try:
            client.delete(
                collection_name=collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="nct_id",
                                match=models.MatchValue(value=nct_id)
                            )
                        ]
                    )
                )
            )
            deleted_count += 1

            # Log every 100 deletions
            if deleted_count % 100 == 0:
                log_with_timestamp(f"    Deleted vectors for {deleted_count}/{len(nct_ids)} trials...")

        except Exception as e:
            log_with_timestamp(f"    WARNING: Failed to delete vectors for {nct_id}: {e}")
            continue

    return deleted_count

def insert_from_faiss(faiss_dir: str, collection_name: str, qdrant_url: str,
                      batch_size: int = 1000, start_id: int = 0,
                      vector_size: int = 768, tracking_file: str = None,
                      chunk_tracking_file: str = None,
                      update_mode: bool = False,
                      hnsw_m: int = 16, hnsw_ef_construct: int = 100,
                      max_segment_size: int = 2_000_000,
                      default_segment_number: int = 2,
                      indexing_threshold: int = 1_000_000,
                      enable_quantization: bool = True,
                      prefer_grpc: bool = False) -> int:
    """
    Insert data from FAISS files to Qdrant

    Args:
        faiss_dir: Directory containing *.index and *.json metadata files (or legacy *_metadata.pkl)
        collection_name: Qdrant collection name
        qdrant_url: Qdrant server URL
        batch_size: Batch size for insertion
        start_id: Starting point ID (for resuming)
        vector_size: Vector dimension
        tracking_file: Optional path to PubMed tracking JSON file (for incremental updates)
        chunk_tracking_file: Optional path to chunk tracking JSON file (for clinical trials)
        update_mode: If True, delete old vectors before inserting (for clinical trials updates)
        hnsw_m: HNSW m parameter (graph connectivity, default: 16)
        hnsw_ef_construct: HNSW ef_construct parameter (build quality, default: 100)
        max_segment_size: Maximum segment size in points (default: 2_000_000)
        default_segment_number: Default number of segments (default: 2, set to 0 for dynamic)
        indexing_threshold: Minimum points before indexing starts (default: 1_000_000, set higher for large datasets)
        enable_quantization: Enable scalar quantization (default: True)
        prefer_grpc: Prefer gRPC protocol over HTTP (20-30% faster for bulk inserts, default: False)

    Returns:
        Total number of vectors inserted
    """
    log_with_timestamp("="*80)
    log_with_timestamp("FAISS to Qdrant Sequential Insertion")
    log_with_timestamp("="*80)
    log_with_timestamp(f"FAISS directory: {faiss_dir}")
    log_with_timestamp(f"Collection: {collection_name}")
    log_with_timestamp(f"Qdrant URL: {qdrant_url}")
    log_with_timestamp(f"Batch size: {batch_size}")
    log_with_timestamp(f"Starting point ID: {start_id}")
    if tracking_file:
        log_with_timestamp(f"PubMed tracking file: {tracking_file}")
    if chunk_tracking_file:
        log_with_timestamp(f"Chunk tracking file: {chunk_tracking_file}")
    if update_mode:
        log_with_timestamp(f"Update mode: ENABLED (will delete old vectors before inserting)")
    log_with_timestamp("")

    # Load tracking data if provided
    tracker = None
    chunk_tracker = None
    already_inserted = set()

    # Load chunk tracking for clinical trials
    if chunk_tracking_file:
        try:
            # Import chunk tracking module
            import importlib.util
            chunk_tracking_module_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(faiss_dir))),
                "modules", "clinical_trials", "scripts", "chunk_tracking.py"
            )
            if not os.path.exists(chunk_tracking_module_path):
                # Try alternative path
                chunk_tracking_module_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", "..", "clinical_trials", "scripts", "chunk_tracking.py"
                )

            if os.path.exists(chunk_tracking_module_path):
                spec = importlib.util.spec_from_file_location("chunk_tracking", chunk_tracking_module_path)
                chunk_tracking_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(chunk_tracking_module)
                ChunkTracker = chunk_tracking_module.ChunkTracker

                chunk_tracker = ChunkTracker(chunk_tracking_file)
                already_inserted = chunk_tracker.get_chunks_not_inserted_to_qdrant()
                # Invert: we want chunks that ARE inserted, not those that are NOT inserted
                all_chunks = set(chunk_tracker.tracking_data["chunks"].keys())
                already_inserted = all_chunks - already_inserted
                log_with_timestamp(f"Loaded chunk tracking: {len(already_inserted)} chunks already inserted to Qdrant")
            else:
                log_with_timestamp(f"WARNING: Could not find chunk_tracking.py, proceeding without chunk tracking")
        except Exception as e:
            log_with_timestamp(f"WARNING: Could not load chunk tracking: {e}")
            log_with_timestamp(f"Proceeding without chunk tracking...")

    # Load PubMed tracking if provided
    if tracking_file:
        try:
            # Import tracking module (assume it's in pubmed/scripts)
            import importlib.util
            tracking_module_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(faiss_dir))),
                "modules", "pubmed", "scripts", "tracking.py"
            )
            if not os.path.exists(tracking_module_path):
                # Try alternative path
                tracking_module_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", "..", "pubmed", "scripts", "tracking.py"
                )

            if os.path.exists(tracking_module_path):
                spec = importlib.util.spec_from_file_location("tracking", tracking_module_path)
                tracking_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(tracking_module)
                PubMedTracker = tracking_module.PubMedTracker

                tracker = PubMedTracker(tracking_file)
                already_inserted = set(f for f in tracker.tracking_data["files"].keys()
                                      if tracker.tracking_data["files"][f].get("qdrant_inserted", False))
                log_with_timestamp(f"Loaded tracking: {len(already_inserted)} files already inserted to Qdrant")
            else:
                log_with_timestamp(f"WARNING: Could not find tracking.py, proceeding without tracking")
        except Exception as e:
            log_with_timestamp(f"WARNING: Could not load tracking: {e}")
            log_with_timestamp(f"Proceeding without tracking...")

    # Initialize Qdrant client
    log_with_timestamp("Connecting to Qdrant...")
    try:
        # Parse URL to extract host and port
        from urllib.parse import urlparse
        parsed_url = urlparse(qdrant_url)
        host = parsed_url.hostname or 'localhost'
        http_port = parsed_url.port or 6333

        # Initialize client with gRPC preference if requested
        if prefer_grpc:
            # Try gRPC first (default gRPC port is HTTP port + 1)
            grpc_port = http_port + 1
            log_with_timestamp(f"Attempting gRPC connection to {host}:{grpc_port}...")
            try:
                client = QdrantClient(
                    host=host,
                    port=http_port,
                    grpc_port=grpc_port,
                    prefer_grpc=True,
                    timeout=300
                )
                # Test connection
                collections = client.get_collections()
                log_with_timestamp(f"✓ Connected via gRPC (20-30% faster for bulk inserts)")
                log_with_timestamp(f"  Existing collections: {len(collections.collections)}")
                log_with_timestamp(f"  Timeout: 300 seconds")
            except Exception as grpc_error:
                # Fall back to HTTP
                log_with_timestamp(f"⚠ gRPC connection failed: {grpc_error}")
                log_with_timestamp(f"Falling back to HTTP...")
                client = QdrantClient(url=qdrant_url, timeout=300)
                collections = client.get_collections()
                log_with_timestamp(f"✓ Connected via HTTP (fallback)")
                log_with_timestamp(f"  Existing collections: {len(collections.collections)}")
                log_with_timestamp(f"  Timeout: 300 seconds")
        else:
            # Use HTTP
            client = QdrantClient(url=qdrant_url, timeout=300)
            collections = client.get_collections()
            log_with_timestamp(f"✓ Connected via HTTP")
            log_with_timestamp(f"  Existing collections: {len(collections.collections)}")
            log_with_timestamp(f"  Timeout: 300 seconds")
            log_with_timestamp(f"  Tip: Use --prefer-grpc for 20-30% faster bulk inserts")
    except Exception as e:
        log_with_timestamp(f"ERROR: Failed to connect to Qdrant at {qdrant_url}")
        log_with_timestamp(f"Error: {e}")
        raise

    # Create collection if needed
    create_collection_if_needed(client, collection_name, vector_size,
                                enable_quantization=enable_quantization,
                                hnsw_m=hnsw_m,
                                hnsw_ef_construct=hnsw_ef_construct,
                                max_segment_size=max_segment_size,
                                default_segment_number=default_segment_number,
                                indexing_threshold=indexing_threshold)

    # Find all FAISS files
    index_files = find_faiss_files(faiss_dir)

    if not index_files:
        log_with_timestamp(f"WARNING: No FAISS index files found in {faiss_dir}")
        return 0

    log_with_timestamp(f"Found {len(index_files)} FAISS files to process")

    # Filter out already-inserted files if tracking is enabled
    if (tracker or chunk_tracker) and already_inserted:
        original_count = len(index_files)
        filtered_files = []
        for index_path in index_files:
            # For chunk tracking (clinical trials): use chunk filename directly
            if chunk_tracker:
                # Extract chunk filename from path (e.g., "trials_chunk_0001.json")
                # The index file is "trials_chunk_0001.index", we need the .json version
                chunk_filename = os.path.basename(index_path).replace('.index', '.json')
                if chunk_filename not in already_inserted:
                    filtered_files.append(index_path)
                else:
                    log_with_timestamp(f"  Skipping {os.path.basename(index_path)} (already inserted)")
            # For PubMed tracking: map to source XML file
            elif tracker:
                source_file = map_faiss_to_source_file(index_path, faiss_dir)
                if source_file not in already_inserted:
                    filtered_files.append(index_path)
                else:
                    log_with_timestamp(f"  Skipping {os.path.basename(index_path)} (already inserted)")

        index_files = filtered_files
        skipped_count = original_count - len(index_files)
        if skipped_count > 0:
            log_with_timestamp(f"Filtered out {skipped_count} already-inserted files/chunks")
        log_with_timestamp(f"Processing {len(index_files)} new files/chunks")

    if not index_files:
        log_with_timestamp(f"No new files to insert")
        return 0

    log_with_timestamp("")

    # Detect ID strategy from first file's metadata
    id_strategy = "sequential"  # Default
    if index_files:
        try:
            _, sample_metadata = load_faiss_and_metadata(index_files[0])
            if sample_metadata:
                first_meta = sample_metadata.get('0', {})
                if 'pmid' in first_meta:
                    id_strategy = "pmid"
                elif 'nct_id' in first_meta:
                    id_strategy = "nct_id"
                elif 'patent_id' in first_meta:
                    id_strategy = "patent_id"
                elif 'surechembl_id' in first_meta:
                    id_strategy = "surechembl_id"
                elif 'protein_id' in first_meta:
                    id_strategy = "protein_id"
        except Exception:
            pass  # Ignore errors, will use sequential as fallback

    log_with_timestamp(f"Point ID strategy: {id_strategy}")
    if id_strategy == "pmid":
        log_with_timestamp("  Using PMID as point ID (enables upsert for incremental updates)")
    elif id_strategy == "nct_id":
        log_with_timestamp("  Using hashed NCT ID as point ID (enables upsert for incremental updates)")
    elif id_strategy == "patent_id":
        log_with_timestamp("  Using hashed Patent ID as point ID (enables upsert for incremental updates)")
    elif id_strategy == "surechembl_id":
        log_with_timestamp("  Using hashed SureChEMBL ID as point ID (enables upsert for incremental updates)")
    elif id_strategy == "protein_id":
        log_with_timestamp("  Using hashed protein ID as point ID (additive delta; cannot collide with legacy sequential esm2 IDs)")
    else:
        log_with_timestamp("  Using sequential IDs (fallback mode)")
    log_with_timestamp("")

    global_point_id = start_id
    total_inserted = 0
    batch = []

    # Process each FAISS file sequentially
    for file_idx, index_path in enumerate(index_files, 1):
        log_with_timestamp(f"[{file_idx}/{len(index_files)}] {os.path.basename(index_path)}")

        try:
            # Load FAISS index and metadata
            index, metadata = load_faiss_and_metadata(index_path)
            n_vectors = index.ntotal

            log_with_timestamp(f"  └─ Vectors: {n_vectors:,}")

            if n_vectors == 0:
                log_with_timestamp(f"  └─ Skipping (empty)")
                continue

            # If update mode is enabled for clinical trials, delete old vectors first
            if update_mode and "clinical_trials" in collection_name.lower():
                log_with_timestamp(f"  └─ Update mode: Collecting NCT IDs for deletion...")

                # Extract unique NCT IDs from metadata
                nct_ids_in_chunk = set()
                for meta_key in metadata:
                    meta = metadata[meta_key]
                    nct_id = meta.get('nct_id')
                    if nct_id:
                        nct_ids_in_chunk.add(nct_id)

                if nct_ids_in_chunk:
                    log_with_timestamp(f"  └─ Found {len(nct_ids_in_chunk)} unique NCT IDs")
                    log_with_timestamp(f"  └─ Deleting old vectors for these trials...")
                    deleted_count = delete_trial_vectors(client, collection_name, list(nct_ids_in_chunk))
                    log_with_timestamp(f"  └─ Deleted vectors for {deleted_count} trials")
                else:
                    log_with_timestamp(f"  └─ WARNING: No NCT IDs found in metadata")

            # Extract vectors
            vectors = np.zeros((n_vectors, vector_size), dtype=np.float32)
            for i in range(n_vectors):
                vectors[i] = index.reconstruct(i)

            # Create points
            for i in range(n_vectors):
                meta_key = str(i)
                if meta_key not in metadata:
                    log_with_timestamp(f"  └─ WARNING: Missing metadata for index {i}")
                    continue

                meta = metadata[meta_key]

                # Get point ID from document unique identifier (PMID or NCT ID)
                # Falls back to sequential ID for backward compatibility
                point_id = get_point_id_from_metadata(meta, global_point_id)

                # Create point with flexible payload
                point = PointStruct(
                    id=point_id,
                    vector=vectors[i].tolist(),
                    payload={
                        **meta,  # Include all metadata fields
                        'source': meta.get('source', collection_name.split('_')[0]),
                        'date_processed': datetime.now().isoformat()
                    }
                )
                batch.append(point)
                global_point_id += 1  # Still increment for fallback case
                total_inserted += 1

                # Batch insert
                if len(batch) >= batch_size:
                    success = upsert_with_retry(client, collection_name, batch)
                    if success:
                        log_with_timestamp(f"  └─ Inserted batch ({total_inserted:,} total)")
                        batch = []
                    else:
                        log_with_timestamp(f"  └─ Batch insert failed, stopping file processing")
                        break

            # Mark as inserted in tracking if enabled
            if chunk_tracker:
                try:
                    # Detect chunk extension from tracking data (e.g., .json for clinical trials, .parquet for patents)
                    chunk_extension = '.json'  # Default
                    if chunk_tracker.tracking_data.get("chunks"):
                        # Get extension from first chunk name in tracking data
                        first_chunk = next(iter(chunk_tracker.tracking_data["chunks"].keys()), None)
                        if first_chunk:
                            chunk_extension = os.path.splitext(first_chunk)[1]

                    chunk_filename = os.path.basename(index_path).replace('.index', chunk_extension)
                    chunk_tracker.mark_inserted_to_qdrant(chunk_filename)
                    log_with_timestamp(f"  └─ Marked {chunk_filename} as inserted in chunk tracking")
                except Exception as e:
                    log_with_timestamp(f"  └─ WARNING: Could not update chunk tracking: {e}")
            elif tracker:
                try:
                    source_file = map_faiss_to_source_file(index_path, faiss_dir)
                    tracker.mark_inserted_to_qdrant(source_file)
                    log_with_timestamp(f"  └─ Marked {source_file} as inserted in tracking")
                except Exception as e:
                    log_with_timestamp(f"  └─ WARNING: Could not update tracking: {e}")

            # Clear memory
            del index, vectors, metadata
            gc.collect()

            # Log Qdrant telemetry after each file
            telemetry = get_qdrant_telemetry(qdrant_url)
            if telemetry:
                memory_used = telemetry.get('memory_used_mb', 0)
                memory_total = telemetry.get('memory_total_mb', 0)
                if memory_total > 0:
                    memory_pct = (memory_used / memory_total) * 100
                    log_with_timestamp(f"  └─ Qdrant memory: {memory_used:.1f}MB / {memory_total:.1f}MB ({memory_pct:.1f}%)")
                else:
                    log_with_timestamp(f"  └─ Qdrant memory: {memory_used:.1f}MB")

        except Exception as e:
            log_with_timestamp(f"  └─ ERROR: {e}")
            log_with_timestamp(f"  └─ Continuing with next file...")
            continue

    # Insert final batch
    if batch:
        success = upsert_with_retry(client, collection_name, batch)
        if success:
            log_with_timestamp(f"Inserted final batch")
        else:
            log_with_timestamp(f"WARNING: Final batch insertion failed")

    log_with_timestamp("")
    log_with_timestamp("="*80)
    log_with_timestamp(f"Insertion complete!")
    log_with_timestamp(f"Total vectors inserted: {total_inserted:,}")
    log_with_timestamp(f"Final point ID: {global_point_id}")
    log_with_timestamp("="*80)

    # Wait for collection to reach GREEN status
    # This is critical - collection is not ready for queries until GREEN
    try:
        final_status, optimization_time = wait_for_green_status(client, collection_name)
        log_with_timestamp("")
        log_with_timestamp("="*80)
        log_with_timestamp(f"COLLECTION READY FOR PRODUCTION")
        log_with_timestamp("="*80)
        log_with_timestamp(f"Total insertion time: (see logs above)")
        log_with_timestamp(f"Optimization time: {optimization_time}s ({optimization_time/60:.1f} minutes)")
        log_with_timestamp(f"Final status: {final_status.upper()}")
        log_with_timestamp("="*80)
    except Exception as e:
        log_with_timestamp(f"WARNING: Error waiting for GREEN status: {e}")
        log_with_timestamp(f"Collection may not be fully optimized yet")

    return total_inserted

def main():
    parser = argparse.ArgumentParser(
        description="Insert FAISS indices to Qdrant sequentially"
    )
    parser.add_argument(
        '--faiss-dir',
        required=True,
        help='Directory containing FAISS index files'
    )
    parser.add_argument(
        '--collection',
        required=True,
        help='Qdrant collection name'
    )
    parser.add_argument(
        '--qdrant-url',
        required=True,
        help='Qdrant server URL (e.g., http://node042:6333)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=500,
        help='Batch size for insertion (default: 500, reduce to 100-250 for NFS/slow storage)'
    )
    parser.add_argument(
        '--start-id',
        type=int,
        default=0,
        help='Starting point ID for resuming (default: 0)'
    )
    parser.add_argument(
        '--vector-size',
        type=int,
        default=768,
        help='Vector dimension (default: 768)'
    )
    parser.add_argument(
        '--tracking-file',
        type=str,
        default=None,
        help='Path to PubMed tracking JSON file (for incremental updates, avoids reprocessing)'
    )
    parser.add_argument(
        '--chunk-tracking-file',
        type=str,
        default=None,
        help='Path to chunk tracking JSON file (for clinical trials, tracks chunk-level insertion)'
    )
    parser.add_argument(
        '--update-mode',
        action='store_true',
        help='Enable update mode (delete old vectors before inserting for clinical trials)'
    )
    parser.add_argument(
        '--hnsw-m',
        type=int,
        default=16,
        help='HNSW m parameter (graph connectivity, default: 16)'
    )
    parser.add_argument(
        '--hnsw-ef-construct',
        type=int,
        default=100,
        help='HNSW ef_construct parameter (index build quality, default: 100)'
    )
    parser.add_argument(
        '--max-segment-size',
        type=int,
        default=2_000_000,
        help='Maximum segment size in points (default: 2,000,000)'
    )
    parser.add_argument(
        '--default-segment-number',
        type=int,
        default=2,
        help='Default number of segments (default: 2, set to 0 for dynamic segmentation)'
    )
    parser.add_argument(
        '--indexing-threshold',
        type=int,
        default=1_000_000,
        help='Minimum points before indexing starts (default: 1M, use 5M+ for large datasets to reduce segments)'
    )
    parser.add_argument(
        '--enable-quantization',
        action='store_true',
        default=True,
        help='Enable scalar quantization (default: True)'
    )
    parser.add_argument(
        '--disable-quantization',
        dest='enable_quantization',
        action='store_false',
        help='Disable scalar quantization'
    )
    parser.add_argument(
        '--prefer-grpc',
        action='store_true',
        default=False,
        help='Prefer gRPC protocol over HTTP (20-30%% faster for bulk inserts, auto-fallback to HTTP)'
    )

    args = parser.parse_args()

    # Validate inputs
    if not os.path.exists(args.faiss_dir):
        log_with_timestamp(f"ERROR: FAISS directory not found: {args.faiss_dir}")
        sys.exit(1)

    # Run insertion
    try:
        insert_from_faiss(
            faiss_dir=args.faiss_dir,
            collection_name=args.collection,
            qdrant_url=args.qdrant_url,
            batch_size=args.batch_size,
            start_id=args.start_id,
            vector_size=args.vector_size,
            tracking_file=args.tracking_file,
            chunk_tracking_file=args.chunk_tracking_file,
            update_mode=args.update_mode,
            hnsw_m=args.hnsw_m,
            hnsw_ef_construct=args.hnsw_ef_construct,
            max_segment_size=args.max_segment_size,
            default_segment_number=args.default_segment_number,
            indexing_threshold=args.indexing_threshold,
            enable_quantization=args.enable_quantization,
            prefer_grpc=args.prefer_grpc
        )
    except KeyboardInterrupt:
        log_with_timestamp("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        log_with_timestamp(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
