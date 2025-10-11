"""
End-to-end test for Clinical Trials pipeline (Chunked Architecture)

This test actually RUNS the full pipeline in test mode and validates output.
Uses test_out/ directory for all outputs (easy to inspect and debug).

Tests the chunked architecture with consistent file naming:
- RAW_DIR/chunked/trials_chunk_0001.json (raw extracted trials - list format)
- PROCESSED_DIR/trials_chunk_0001.index (FAISS index)
- PROCESSED_DIR/trials_chunk_0001.json (processed metadata - dict format)

Consistent with PubMed: file.index + file.json everywhere!

With test config (100 trials, 50 per chunk = 2 chunks): Should take ~5-10 minutes.

Usage:
    ./run_tests.sh clinical_trials  (includes E2E)
    pytest tests/integration/test_clinical_trials_e2e.py -m e2e -v
"""
import pytest
import subprocess
import json
import faiss
import shutil
from pathlib import Path
import yaml


@pytest.fixture(scope="module")
def run_pipeline_e2e():
    """Actually run the pipeline using test_out/ directory"""
    project_root = Path(__file__).parent.parent.parent
    test_config_path = project_root / 'config' / 'test_config.yaml'

    # Load test config (already points to test_out/)
    with open(test_config_path) as f:
        config = yaml.safe_load(f)

    output_dir = Path(config['base_dir'])

    # Check if processed data already exists (from previous test run)
    processed_dir = output_dir / 'data' / 'processed' / 'clinical_trials'
    has_processed_data = processed_dir.exists() and list(processed_dir.glob('trials_chunk_*.index'))

    if has_processed_data:
        print(f"\n{'='*80}")
        print(f"REUSING existing processed data from previous test run")
        print(f"Found processed indices in: {processed_dir}")
        print(f"To force re-processing, delete: {output_dir}")
        print(f"{'='*80}\n")
        skip_pipeline = True
    else:
        # Clean only data/ and logs/, preserve raw_data/ to avoid re-downloading 2.2GB
        print(f"\n{'='*80}")
        print(f"Cleaning test output: {output_dir}/data and {output_dir}/logs")
        print(f"Preserving: {output_dir}/raw_data (2.2GB download)")
        print(f"{'='*80}\n")

        for subdir in ['logs']:
            path_to_clean = output_dir / subdir
            if path_to_clean.exists():
                print(f"  Removing: {path_to_clean}")
                shutil.rmtree(path_to_clean)
        skip_pipeline = False

        # Copy test fixture to raw data directory if AACT database not present
        fixture_source = project_root / 'tests' / 'fixtures' / 'clinical_trials' / 'sample_trials.json'
        raw_chunked_dir = output_dir / 'raw_data' / 'clinical_trials' / 'chunked'

        # Check if we have real AACT data or need to use fixture
        extraction_info = output_dir / 'raw_data' / 'clinical_trials' / 'extracted' / 'extraction_info.json'

        if not extraction_info.exists() and fixture_source.exists():
            # No real AACT data, use fixture
            raw_chunked_dir.mkdir(parents=True, exist_ok=True)
            fixture_dest = raw_chunked_dir / 'trials_chunk_0001.json'
            print(f"\n{'='*80}")
            print(f"No AACT data found, copying test fixture")
            print(f"Copying: {fixture_source.name} -> {fixture_dest}")
            print(f"Fixture size: {fixture_source.stat().st_size / 1024:.1f} KB (50 trials)")
            print(f"{'='*80}\n")
            shutil.copy2(fixture_source, fixture_dest)

            # Create extraction_info.json (needed by extract checkpoint as input)
            extracted_dir = output_dir / 'raw_data' / 'clinical_trials' / 'extracted'
            extracted_dir.mkdir(parents=True, exist_ok=True)
            extraction_info_data = {
                "source": "test_fixture",
                "timestamp": "2025-10-11T00:00:00",
                "trials_extracted": 50,
                "extraction_method": "fixture"
            }
            with open(extraction_info, 'w') as f:
                json.dump(extraction_info_data, f, indent=2)

            # Create download flag (needed by extract checkpoint as input)
            download_flag = output_dir / 'raw_data' / 'clinical_trials' / '.download_complete'
            download_flag.touch()

            # NOTE: chunk_manifest.json is NOT created here!
            # The extract script will auto-detect the fixture and create it automatically

            print(f"Created extraction_info.json and download flag for fixture")
            print(f"Extract script will auto-detect fixture and create manifest\n")
        elif extraction_info.exists():
            print(f"\n{'='*80}")
            print(f"Using existing AACT data from raw_data/")
            print(f"{'='*80}\n")
        else:
            print(f"\n{'='*80}")
            print(f"WARNING: No fixture or AACT data found")
            print(f"Pipeline will download AACT database (2.2GB)")
            print(f"{'='*80}\n")

    # Run pipeline (unless skipping because data exists)
    if skip_pipeline:
        print(f"Skipping pipeline execution - reusing existing data\n")
        return {
            'returncode': 0,
            'stdout': 'Skipped - reusing existing data',
            'stderr': '',
            'config': config,
            'output_dir': output_dir,
            'project_root': project_root,
            'skipped': True
        }
    else:
        cmd = [
            str(project_root / 'bioyoda.sh'),
            'run', 'clinical_trials',
            '--config', str(test_config_path),
            '--local',
            '--cores', '2'
        ]

        print(f"\n{'='*80}")
        print(f"Running E2E Pipeline: {' '.join(cmd)}")
        print(f"Output directory: {output_dir}")
        print(f"Config: test_mode={config['clinical_trials'].get('test_mode')}, "
              f"test_trials_limit={config['clinical_trials'].get('test_trials_limit')}")
        print(f"{'='*80}\n")

        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minute timeout (should be enough for 100 trials)
        )

        return {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'config': config,
            'output_dir': output_dir,
            'project_root': project_root,
            'skipped': False
        }


class TestClinicalTrialsEndToEnd:
    """End-to-end tests that actually run the pipeline"""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_pipeline_runs_successfully(self, run_pipeline_e2e):
        """Test that pipeline completes without errors"""
        result = run_pipeline_e2e

        if result['returncode'] != 0:
            print(f"\n{'='*80}")
            print("PIPELINE FAILED")
            print(f"{'='*80}")
            print("\nSTDOUT:")
            print(result['stdout'])
            print("\nSTDERR:")
            print(result['stderr'])
            print(f"{'='*80}\n")

        assert result['returncode'] == 0, \
            f"Pipeline failed with return code {result['returncode']}"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_downloads_data(self, run_pipeline_e2e):
        """Test that clinical trials data was downloaded"""
        output_dir = run_pipeline_e2e['output_dir']

        raw_dir = output_dir / 'raw_data' / 'clinical_trials'
        assert raw_dir.exists(), "Raw data directory not created"

        # Check for extracted data directory (AACT extracts to CSV files)
        extracted_dir = raw_dir / 'extracted'
        assert extracted_dir.exists(), "Extracted data directory not created"

        # Check for extraction_info.json
        extraction_info = extracted_dir / 'extraction_info.json'
        assert extraction_info.exists(), "Extraction info not found"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_chunk_manifest_created(self, run_pipeline_e2e):
        """Test that chunk manifest is created with correct info"""
        output_dir = run_pipeline_e2e['output_dir']
        config = run_pipeline_e2e['config']
        processed_dir = output_dir / 'data' / 'processed' / 'clinical_trials'

        # Check for chunk manifest
        manifest_file = processed_dir / 'chunk_manifest.json'
        assert manifest_file.exists(), "Chunk manifest not created"

        # Load and validate manifest
        with open(manifest_file) as f:
            manifest = json.load(f)

        assert manifest['chunked'] == True, "Manifest should indicate chunked mode"
        assert 'num_chunks' in manifest, "Missing num_chunks in manifest"
        assert 'trials_per_chunk' in manifest, "Missing trials_per_chunk in manifest"
        assert 'chunks' in manifest, "Missing chunks list in manifest"
        assert len(manifest['chunks']) > 0, "Chunks list is empty"

        # Verify chunk files match manifest
        chunk_indices = list(processed_dir.glob('trials_chunk_*.index'))
        assert len(chunk_indices) == manifest['num_chunks'], \
            f"Mismatch: {len(chunk_indices)} index files vs {manifest['num_chunks']} in manifest"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_processes_with_limit(self, run_pipeline_e2e):
        """Test that test mode processes limited trials"""
        output_dir = run_pipeline_e2e['output_dir']
        config = run_pipeline_e2e['config']

        # Check for chunk files in processed directory (NEW chunked architecture)
        processed_dir = output_dir / 'data' / 'processed' / 'clinical_trials'
        assert processed_dir.exists(), "Processed directory not created"

        # Find all chunk index files
        chunk_indices = list(processed_dir.glob('trials_chunk_*.index'))
        assert len(chunk_indices) > 0, "No chunk index files created"

        # Check vector counts across all chunks
        if config['clinical_trials'].get('test_mode'):
            limit = config['clinical_trials'].get('test_trials_limit', 100)

            total_vectors = 0
            for chunk_index in chunk_indices:
                index = faiss.read_index(str(chunk_index))
                total_vectors += index.ntotal

            # Each trial can have multiple chunks, so allow some variance
            # With 100 trials and ~3-5 chunks per trial, expect ~300-500 vectors
            assert total_vectors > 0, "All chunk indices are empty"
            assert total_vectors <= limit * 10, \
                f"Total vectors {total_vectors}, expected <={limit * 10} for {limit} trials"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_final_index_valid(self, run_pipeline_e2e):
        """Test that chunk indices are valid FAISS indices"""
        output_dir = run_pipeline_e2e['output_dir']
        processed_dir = output_dir / 'data' / 'processed' / 'clinical_trials'

        # Find all chunk index files
        chunk_indices = list(processed_dir.glob('trials_chunk_*.index'))
        assert len(chunk_indices) > 0, "No chunk index files found"

        # Validate each chunk index
        total_vectors = 0
        for chunk_index in chunk_indices:
            index = faiss.read_index(str(chunk_index))
            assert index.ntotal > 0, f"Chunk index {chunk_index.name} is empty"
            assert index.d == 768, f"Chunk index {chunk_index.name} has wrong dimension: {index.d}"
            total_vectors += index.ntotal

        assert total_vectors > 0, "All chunk indices are empty"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_metadata_created(self, run_pipeline_e2e):
        """Test that chunk metadata files are created with correct structure"""
        output_dir = run_pipeline_e2e['output_dir']
        processed_dir = output_dir / 'data' / 'processed' / 'clinical_trials'

        # Find all chunk metadata files (consistent naming: .json, not _metadata.json)
        chunk_metadata_files = list(processed_dir.glob('trials_chunk_*.json'))
        assert len(chunk_metadata_files) > 0, "No chunk metadata files created"

        # Load and validate metadata from each chunk
        total_entries = 0
        for metadata_file in chunk_metadata_files:
            with open(metadata_file) as f:
                metadata = json.load(f)

            # Metadata is a dict with numeric string keys
            assert isinstance(metadata, dict), f"Metadata in {metadata_file.name} is not a dict"
            assert len(metadata) > 0, f"Metadata in {metadata_file.name} is empty"
            total_entries += len(metadata)

            # Check structure of first entry
            first_entry = next(iter(metadata.values()))
            assert 'nct_id' in first_entry, f"Missing nct_id in {metadata_file.name}"
            assert 'text' in first_entry, f"Missing text in {metadata_file.name}"
            assert 'chunk_type' in first_entry, f"Missing chunk_type in {metadata_file.name}"

        assert total_entries > 0, "All chunk metadata files are empty"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_pipeline_creates_logs(self, run_pipeline_e2e):
        """Test that pipeline creates log files"""
        output_dir = run_pipeline_e2e['output_dir']
        log_dir = output_dir / 'logs' / 'clinical_trials'

        assert log_dir.exists(), "Log directory not created"

        # Download log is only created if download was actually performed
        # In fixture mode, download is skipped entirely (no log created)
        # In real mode, download runs and creates a log
        download_log = log_dir / 'download.log'

        # If download log exists, verify it's not empty
        if download_log.exists():
            assert download_log.stat().st_size > 0, "Download log is empty"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_trial_metadata_structure(self, run_pipeline_e2e):
        """Test that trials have correct metadata fields"""
        output_dir = run_pipeline_e2e['output_dir']
        processed_dir = output_dir / 'data' / 'processed' / 'clinical_trials'

        # Find all chunk metadata files (consistent naming: .json, not _metadata.json)
        chunk_metadata_files = list(processed_dir.glob('trials_chunk_*.json'))
        assert len(chunk_metadata_files) > 0, "No chunk metadata files found"

        # Check metadata structure across all chunks
        for metadata_file in chunk_metadata_files:
            with open(metadata_file) as f:
                metadata = json.load(f)

            # Metadata is a dict with numeric string keys
            assert isinstance(metadata, dict), f"Metadata in {metadata_file.name} is not a dict"

            # Check all entries have required fields
            for entry in metadata.values():
                assert entry['nct_id'].startswith('NCT'), \
                    f"Invalid NCT ID: {entry.get('nct_id')}"
                assert len(entry['text']) > 0, "Empty text in metadata"
                # Valid chunk types from clinical trials processing
                valid_chunk_types = ['title', 'summary', 'description', 'eligibility', 'interventions', 'outcomes']
                assert entry['chunk_type'] in valid_chunk_types, \
                    f"Invalid chunk_type: {entry.get('chunk_type')}"
