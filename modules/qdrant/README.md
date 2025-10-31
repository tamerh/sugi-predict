# Qdrant Module

Standalone vector database operations for BioYoda.

## Overview

This module manages Qdrant vector database operations **independently** from data processing:
- **Server Management**: Start/stop Qdrant server (local or cluster)
- **Data Insertion**: Insert FAISS indices to Qdrant collections
- **Status Monitoring**: Check server and collection status
- **Flexible Deployment**: Run on GPU nodes for long-running sessions

**Key Architecture Change (v0.2.0)**: Qdrant operations are now **completely separate** from data processing pipelines.

## Quick Start

### Basic Workflow

```bash
# 1. Start Qdrant server
./bioyoda.sh qdrant start

# 2. Insert data (after processing)
./bioyoda.sh qdrant insert pubmed
./bioyoda.sh qdrant insert clinical_trials

# 3. Check status
./bioyoda.sh qdrant status

# 4. Stop server
./bioyoda.sh qdrant stop
```

### Production Workflow (GPU Node)

```bash
# 1. Start on GPU node for long-running session
./bioyoda.sh qdrant start --mode cluster --queue gpu --runtime 168

# 2. Insert data when ready (can be days later)
./bioyoda.sh qdrant insert all --cluster --jobs 20

# 3. Server keeps running for weeks
./bioyoda.sh qdrant status

# 4. Stop when done
./bioyoda.sh qdrant stop
```

## Commands

### Start Server

```bash
# Local mode (default)
./bioyoda.sh qdrant start

# Cluster mode on SCC queue
./bioyoda.sh qdrant start --mode cluster --queue scc --runtime 48

# Cluster mode on GPU queue (recommended for production)
./bioyoda.sh qdrant start --mode cluster --queue gpu --runtime 168

# Custom memory allocation
./bioyoda.sh qdrant start --memory 64000  # 64GB
```

**Start Options**:
- `--mode <local|cluster>`: Run mode (default: local)
- `--queue <name>`: SGE queue (default: scc, options: gpu)
- `--runtime <hours>`: Server runtime in hours (default: 48)
- `--memory <mb>`: Memory in MB (default: 32000)

**Output**: Creates `data/qdrant/connection_info.txt` with server URL

### Stop Server

```bash
# Stop server and clean up
./bioyoda.sh qdrant stop
```

Stops both local and cluster-based servers, removes PID files and connection info.

### Check Status

```bash
# Comprehensive status check
./bioyoda.sh qdrant status
```

Shows:
- Server running state (local/cluster)
- Connection information
- Collections and point counts
- Storage size
- Insertion completion markers

### Insert Data

```bash
# Insert specific dataset
./bioyoda.sh qdrant insert pubmed
./bioyoda.sh qdrant insert clinical_trials

# Insert all datasets
./bioyoda.sh qdrant insert all

# Insert with cluster resources
./bioyoda.sh qdrant insert pubmed --cluster --jobs 10

# Insert locally
./bioyoda.sh qdrant insert pubmed --local --cores 4
```

**Insert Options**:
- `--cluster`: Submit insertion jobs to cluster
- `--local`: Run insertion locally (default)
- `--cores N`: Number of cores for local mode
- `--jobs N`: Max parallel jobs for cluster mode

**Incremental Updates:**
- Insertion automatically integrates with PubMed tracking system
- Skips already-inserted files (tracked in `state/pubmed/processed_files.json`)
- Uses PMID-based upsert: Same document = same point ID → replaces old version
- No duplicates, no redundant work

## Architecture

### Standalone Design

```
Data Processing                    Qdrant Module
(Independent)                      (Independent)
     ↓                                  ↓
FAISS Files  ─────────────→  Server Running
(data ready)                   (local/cluster)
                                      ↓
                              Insert Operations
                                (Snakemake)
                                      ↓
                              Collections Ready
                                (searchable)
```

### Components

```
modules/qdrant/
├── Snakefile                    # Insertion workflows (standalone)
├── README.md                    # This file
├── scripts/
│   ├── start_server.sh          # Start server (bash)
│   ├── stop_server.sh           # Stop server (bash)
│   ├── check_status.sh          # Status checker (bash)
│   └── insert_from_faiss.py     # Insertion script (Snakemake)
└── setup/
    └── singularity/
        └── qdrant.sif           # Qdrant container

config/
└── qdrant_config.yaml           # Qdrant server configuration
```

### Workflow Logic

**Server Management** (Pure Bash):
- Simple operations: start/stop/status
- Direct execution via `bioyoda.sh`
- No Snakemake overhead

**Data Insertion** (Snakemake):
- Complex workflow with dependencies
- Automatic resumability
- Batch tracking with `.done` markers

## Collections

### PubMed Abstracts (`pubmed_abstracts`)

- **Source**: `data/processed/pubmed/`
- **Vectors**: ~30M (production), ~2000 (test)
- **Metadata**: PMID, title, abstract, journal, MeSH terms
- **Insertion Time**: 2-4 hours (production)

### Clinical Trials (`clinical_trials`)

- **Source**: `data/processed/clinical_trials/` (chunked indices)
- **Vectors**: ~3M chunks (production), ~500 (test)
- **Metadata**: NCT ID, chunk type, title, status, conditions
- **Insertion Time**: 30-60 minutes (production)

## Incremental Updates & Upsert Strategy

### Smart Point IDs

The insertion script uses **document-based point IDs** instead of sequential IDs:

**PubMed:**
- Point ID = PMID (e.g., `12345678`)
- Same article → same point ID → automatic replacement via upsert

**Clinical Trials:**
- Point ID = Deterministic hash of NCT ID
- Same trial → same point ID → automatic replacement

### Tracking Integration

**PubMed tracking** (`state/pubmed/processed_files.json`):
```json
{
  "files": {
    "baseline/pubmed25n0001.xml.gz": {
      "status": "completed",
      "qdrant_inserted": true,
      "qdrant_inserted_date": "2025-10-12T17:44:01"
    }
  }
}
```

**Workflow:**
1. Insertion script checks tracking file
2. Skips files with `qdrant_inserted: true`
3. Processes only new files
4. Marks them as inserted after success

### Update Scenario

**Day 1 - Initial Load:**
```bash
# Insert 1200 baseline files
./bioyoda.sh qdrant insert pubmed
# Result: 30M vectors, all marked as qdrant_inserted: true
```

**Day 2 - Daily Update:**
```bash
# Process new updatefiles (e.g., 2 new files)
./bioyoda.sh run pubmed --mode update --cluster --bg

# Insert new data
./bioyoda.sh qdrant insert pubmed
# Result:
# - Skips 1200 baseline files (already inserted)
# - Inserts 2 new updatefiles
# - If PMID exists → replaces old vector (upsert)
# - If PMID new → adds new vector
```

**Benefits:**
- ⚡ **Efficient**: Only processes new files
- 🔄 **Upsert**: Updated articles automatically replace old versions
- 📊 **Trackable**: Know exactly what's been inserted
- 💾 **No Duplicates**: PMID-based IDs ensure uniqueness

**Technical Details:**
- See `modules/qdrant/UPSERT_STRATEGY.md` for full implementation details
- Tracking uses file locking for parallel safety
- Works seamlessly with Snakemake dependency system

## Configuration

### Qdrant Server Configuration

Qdrant server settings are in **`config/qdrant_config.yaml`**. This file is bind-mounted into the Singularity container when starting the server.

Key settings (optimized for HPC/NFS):
```yaml
service:
  host: 0.0.0.0
  http_port: 6333

storage:
  wal_capacity_mb: 256            # 256MB WAL for better NFS tolerance
  wal_segments_ahead: 2
  flush_interval_sec: 30          # Flush WAL every 30 seconds

optimizer:
  max_segment_size: 2147483648    # 2GB segments (reduced for WAL stability)
  memmap_threshold: 524288000     # 500MB
  indexing_threshold: 1073741824  # 1GB
```

### Insertion Settings

Insertion settings are in **`config/config.yaml`**:

```yaml
qdrant:
  batch_size: 500                    # Insertion batch size (reduced for NFS stability)

  server:
    memory_mb: 131072                # 128GB for server
    runtime_hours: 48                # 2 days default

pubmed:
  qdrant:
    collection_name: "pubmed_abstracts"
    memory_mb: 8192                  # Memory for insertion job

clinical_trials:
  qdrant:
    collection_name: "clinical_trials"
    memory_mb: 8192
```

### WAL Optimization for NFS

The configuration includes optimizations for HPC environments with NFS storage:

- **Increased WAL capacity** (256MB): Reduces WAL flush frequency
- **Smaller segments** (2GB vs 5GB): Better for incremental writes
- **Frequent flushes** (30s): Prevents WAL buildup
- **Lower thresholds**: Triggers memory mapping and indexing earlier
- **Retry logic**: Automatic exponential backoff on WAL errors in insert script

To modify Qdrant server settings, edit `config/qdrant_config.yaml` and restart the server:
```bash
./bioyoda.sh qdrant stop
./bioyoda.sh qdrant start
```

## Output & Storage

### Directory Structure

```
data/qdrant/
├── connection_info.txt          # Server URL (created on start)
├── qdrant.pid                   # Process ID (local mode only)
├── storage/                     # Qdrant data directory
│   ├── collections/
│   │   ├── pubmed_abstracts/
│   │   └── clinical_trials/
│   └── meta.json
└── collections/
    ├── pubmed_abstracts.done    # Insertion markers
    └── clinical_trials.done
```

### Connection Info

After starting server, check connection:

```bash
cat data/qdrant/connection_info.txt
# Output:
# export QDRANT_URL="http://nodeXXX:6333"
# export QDRANT_HOST="nodeXXX"
# export QDRANT_PORT="6333"
```

### Query Collections

```bash
# Source connection info
source data/qdrant/connection_info.txt

# List collections
curl $QDRANT_URL/collections

# Get collection info
curl $QDRANT_URL/collections/pubmed_abstracts

# Query vectors (example)
curl -X POST "$QDRANT_URL/collections/pubmed_abstracts/points/search" \
  -H 'Content-Type: application/json' \
  -d '{
    "vector": [...],  # Your query vector
    "limit": 10
  }'
```

## Troubleshooting

### Server Won't Start

```bash
# Check if already running
./bioyoda.sh qdrant status

# Check logs
tail -f logs/qdrant/server.log

# Stop and restart
./bioyoda.sh qdrant stop
./bioyoda.sh qdrant start
```

### Insertion Fails

```bash
# Check if server is running
./bioyoda.sh qdrant status

# Check if data exists
ls -lh data/processed/pubmed/baseline/*.index
ls -lh data/processed/clinical_trials/*.index

# Check insertion logs
tail -f logs/qdrant/insert_pubmed.log

# Re-run insertion
./bioyoda.sh qdrant insert pubmed
```

### Connection Issues

```bash
# Verify connection file exists
cat data/qdrant/connection_info.txt

# Test connection
source data/qdrant/connection_info.txt
curl $QDRANT_URL/collections

# Check if server is on correct node
qstat -u $(whoami) | grep q_server
```

### Performance Issues

**Slow insertions**:
- Increase batch size in config (default: 500)
- Check NFS performance (Qdrant on network storage)
- Consider local SSD for Qdrant storage

**Memory issues**:
- Increase server memory: `--memory 64000`
- Reduce batch size in config
- Use GPU node with more RAM

### WAL Errors

**"segment creator thread already failed" or WAL errors**:

This indicates Qdrant's Write-Ahead Log system has failed, usually due to:
- Disk space exhaustion
- NFS/network filesystem issues
- Too many concurrent writes

**Solutions**:

1. **Restart Qdrant server** (required):
```bash
./bioyoda.sh qdrant stop
./bioyoda.sh qdrant start
```

2. **Check disk space**:
```bash
df -h /path/to/qdrant/storage
```

3. **Reduce batch size** (edit `config/config.yaml`):
```yaml
qdrant:
  batch_size: 250  # Reduce from 500
```

4. **Check Qdrant logs**:
```bash
tail -f out/logs/qdrant/server.log
tail -f out/logs/qdrant/insert_pubmed.log
```

The insert script now includes automatic retry logic with exponential backoff, but persistent errors require server restart.

### On-Disk HNSW and cgroups Panic (Singularity/SGE Environment)

**CRITICAL ISSUE** for large high-dimensional collections in HPC environments.

#### Problem Description

When using `hnsw_on_disk: true` for collections with high-dimensional vectors (e.g., 2048-dim), Qdrant's optimizer crashes with a cgroups-related panic:

```
ERROR: Optimization task panicked: called `Result::unwrap()` on an `Err` value:
Error { kind: ReadFailed("/sys/fs/cgroup/system.slice/sgeexecd.SCC.service/memory.high"),
cause: Some(Os { code: 2, kind: NotFound, message: "No such file or directory" }) }
```

**Root Cause:**
- Qdrant tries to read cgroup memory limits to manage memory during optimization
- In Singularity containers running under SGE, cgroup paths are different/unavailable
- The Rust cgroups library (cgroups-rs) used by Qdrant panics when it can't read these files
- This causes the entire optimizer thread to crash

#### When This Occurs

This issue appears when:
1. Using **`hnsw_on_disk: true`** in collection config
2. Collection reaches **indexing_threshold** and optimizer starts
3. Running in **Singularity container** on **SGE/HPC cluster**
4. Especially with **large collections** (30M+ points) and **high-dimensional vectors** (2048-dim)

#### Symptoms

```bash
# Collection status
Status: red
Optimizer: {'error': 'Service internal error: Optimization task panicked: ...'}
Indexed: 0 / 30,000,000  (stuck at 0%)

# Server logs show
2025-10-30T06:18:11.844330Z ERROR qdrant::startup: Panic occurred in file
/usr/local/cargo/registry/src/index.crates.io-1949cf8c6b5b557f/cgroups-rs-0.3.4/src/memory.rs
at line 587: called `Result::unwrap()` on an `Err` value

# Memory behavior
- Memory jumps from ~15GB to ~27GB when optimizer starts
- Then stays stable (optimizer crashed)
- CPU usage minimal (~1-2%, not doing work)
```

#### Why On-Disk HNSW Needs cgroups

On-disk HNSW storage requires careful memory management:
- HNSW graph building is memory-intensive
- Qdrant needs to know available memory to avoid OOM
- It queries cgroups to get memory limits
- Without this info, it can't safely manage on-disk operations

#### Solutions & Workarounds

**Option 1: Use In-Memory HNSW with Reduced Parameters** (Temporary Workaround)

For collections that would benefit from on_disk but hit this issue:

```yaml
# In config.yaml - patents compounds example
patents:
  qdrant:
    compounds_hnsw_m: 16                  # Instead of 32 (50% less memory)
    compounds_hnsw_ef_construct: 128      # Instead of 256 (50% less memory)
    compounds_hnsw_on_disk: false         # Use in-memory
    compounds_indexing_threshold: 30000000
```

**Memory impact:**
- m=32, ef=256: ~140-210GB during indexing (OOM on 128GB server)
- m=16, ef=128: ~70-80GB during indexing (fits in 128GB)
- Trade-off: Slightly lower search quality (~5-10% recall reduction)

**Option 2: Newer Qdrant Version** (Needs Testing)

The cgroups panic might be fixed in newer Qdrant versions (> 1.15.4):
- Check Qdrant releases for cgroups-related fixes
- Build/download newer Singularity container
- Test with sample collection before production use

**Option 3: Patch Qdrant Container** (Advanced)

Modify the Qdrant binary to handle cgroups errors gracefully:
- Fork Qdrant source
- Patch cgroups detection to return defaults on failure
- Build custom container with patch
- Requires Rust knowledge and testing

**Option 4: Mock cgroup Files** (Experimental)

Create fake cgroup files that Qdrant can read:
```bash
# In Singularity startup script
mkdir -p /sys/fs/cgroup/system.slice/sgeexecd.SCC.service/
echo "max" > /sys/fs/cgroup/system.slice/sgeexecd.SCC.service/memory.high
# Bind-mount when starting container
```
**Warning:** Untested, may cause other issues.

#### Recommended Approach (As of Oct 2025)

For **large high-dimensional collections** (e.g., patents_compounds with 2048-dim, 30M+ points):

1. **Try reduced HNSW parameters first** (Option 1)
   - Quick to implement
   - Known to work
   - Acceptable quality trade-off for most use cases

2. **Monitor Qdrant releases** for cgroups fix
   - Subscribe to Qdrant GitHub releases
   - Test new versions when available

3. **Consider splitting collections** if quality is critical
   - Multiple smaller collections instead of one large one
   - Each can use higher quality settings without OOM

#### Related Issues

- Qdrant GitHub: Search for "cgroups" and "Singularity" issues
- Related to: Memory detection in containerized HPC environments
- Affects: Optimization operations (indexing, segment merging)
- Does NOT affect: Data insertion, search operations, in-memory HNSW

#### Testing On-Disk HNSW

Before deploying on_disk HNSW in production:

```bash
# 1. Create test collection with small dataset
curl -X PUT http://localhost:6333/collections/test_ondisk \
  -H 'Content-Type: application/json' \
  -d '{
    "vectors": {"size": 2048, "distance": "Cosine"},
    "hnsw_config": {"on_disk": true, "m": 32, "ef_construct": 256},
    "optimizer_config": {"indexing_threshold": 1000}
  }'

# 2. Insert 2000 test points
# (Use insert script with small dataset)

# 3. Monitor for cgroups panic
tail -f logs/qdrant/server.log | grep -i "panic\|cgroup"

# 4. Check if indexing completes
curl http://localhost:6333/collections/test_ondisk
# Look for: status=green, indexed_vectors_count > 0
```

If test succeeds, on_disk should work. If it panics, use workaround (Option 1).

#### Mock cgroups Workaround - Implementation Results (Oct 2025)

**Option 4 was successfully implemented and tested.** Here are the findings:

**✅ SUCCESS: Mock cgroups fixed the panic**

The workaround creates fake cgroup files with realistic memory values and bind-mounts them into the Singularity container:

```bash
# Create mock cgroup directory
MOCK_DIR="/tmp/qdrant_mock_cgroups_$$"
mkdir -p "$MOCK_DIR"

# Write realistic values for 128GB system
echo "128849018880" > "$MOCK_DIR/memory.max"      # 120GB limit
echo "118111600640" > "$MOCK_DIR/memory.high"     # 110GB soft limit
echo "21474836480" > "$MOCK_DIR/memory.current"   # 20GB current usage

# Bind-mount into container
singularity run --bind "$MOCK_DIR:/sys/fs/cgroup/system.slice/sgeexecd.SCC.service" ...
```

**Result:** Qdrant successfully reads mock cgroups and reports `free: 107374182400` (100GB). No more cgroups panic!

**❌ NEW ISSUE DISCOVERED: Virtual Memory Limit**

The optimizer then fails with:
```
ERROR: Optimization error: Out of memory, free: 107374182400, IO Error: Cannot allocate memory (os error 12)
VSZ: 524,656,320 KB (500GB) - already at limit!
Virtual memory limit: 536,870,912 KB (512GB) - hard limit from SGE/Singularity
```

**Root cause:** Even though on-disk HNSW uses mmap (low RSS), mmap still counts against VSZ (virtual memory). With 30M points × 2048-dim, the mmap allocations push VSZ beyond the 512GB limit imposed by the SGE job scheduler.

**Troubleshooting Steps Performed:**

1. **Verify mock cgroups are read:**
   ```bash
   # After optimizer starts, check logs - should show "free: 107374182400" not "free: 0"
   grep "Out of memory" logs/qdrant/server.log
   ```

2. **Trigger indexing manually if needed:**
   ```bash
   # Lower indexing_threshold to trigger optimizer
   curl -X PATCH http://localhost:6333/collections/patents_compounds \
     -H 'Content-Type: application/json' \
     -d '{"optimizers_config": {"indexing_threshold": 1000000}}'

   # Or nudge the threshold slightly
   curl -X PATCH http://localhost:6333/collections/patents_compounds \
     -H 'Content-Type: application/json' \
     -d '{"optimizers_config": {"indexing_threshold": 1000001}}'

   # Wait 2-3 minutes, then check status
   curl http://localhost:6333/collections/patents_compounds | \
     python3 -c "import sys,json; d=json.load(sys.stdin)['result']; \
     print(f\"Status: {d['status']}, Indexed: {d['indexed_vectors_count']}\")"
   ```

3. **Monitor memory usage:**
   ```bash
   # Check both RSS (actual) and VSZ (virtual) memory
   ps aux | grep '[q]drant' | awk '{print "RSS: "$6/1024" MB, VSZ: "$5/1024" MB"}'

   # Check system limits
   cat /proc/$(pgrep qdrant)/limits | grep "Max address space"
   ```

**Conclusion:**

Mock cgroups workaround **WORKS** for fixing the cgroups panic. However, on-disk HNSW may still fail due to:
- **Virtual memory limits** imposed by job schedulers (SGE/SLURM)
- **Data size**: Large collections (30M+ points) with high dimensions (2048) require >512GB VSZ
- **Environment**: Singularity containers inherit host VSZ limits

**When to use mock cgroups:**
- ✅ Nodes with high virtual memory limits (>1TB VSZ available)
- ✅ Smaller collections that fit within VSZ constraints
- ✅ Testing if cgroups is the only blocker

**When to use Option 1 instead:**
- ❌ Standard HPC nodes with 512GB VSZ limit
- ❌ Large high-dimensional collections (30M+ × 2048-dim)
- ❌ Need reliable production deployment

**Implementation:** Mock cgroups support is available in `./bioyoda.sh qdrant start` with `--mock-cgroups` flag (enabled by default on Singularity). See script documentation for details.

#### ✅ SUCCESSFUL DEPLOYMENT: scc2 with Unlimited Virtual Memory (Oct 2025)

**THE SOLUTION THAT WORKED:**

After encountering VSZ limits on scc140 (512GB), we discovered that **scc2 node has unlimited virtual memory**. By combining mock cgroups with scc2's unlimited vmem, we successfully indexed the entire patents_compounds collection.

**Final Configuration:**
```yaml
# config.yaml - patents_compounds (PRODUCTION)
patents:
  qdrant:
    compounds_hnsw_m: 32                      # Full quality (not reduced)
    compounds_hnsw_ef_construct: 256          # Full quality (not reduced)
    compounds_hnsw_on_disk: true              # ON-DISK HNSW - works on scc2!
    compounds_hnsw_max_indexing_threads: 8    # CPU thread limiting (prevents cluster overload)
    compounds_indexing_threshold: 30000000    # 30M points - delay indexing until all data loaded
    compounds_max_segment_size: 20000000      # 20M points per segment
```

**Deployment Steps:**

1. **Transfer data to scc2** (249 GB):
   ```bash
   rsync -avh --progress /localscratch/tgur/qdrant_scc140_20251029/ \
     scc2:/localscratch/tgur/qdrant_scc140_20251029/
   ```

2. **Start Qdrant on scc2** with mock cgroups:
   ```bash
   # SSH to scc2 first
   ssh scc2

   # Start Qdrant with mock cgroups (automatic in bioyoda.sh)
   ./bioyoda.sh qdrant start --mode local --memory 128000
   ```

3. **Monitor indexing progress:**
   ```bash
   curl -s "http://scc2:6333/collections/patents_compounds" | \
     python3 -c "import sys, json; d=json.load(sys.stdin)['result']; \
     print(f'Status: {d[\"status\"]}, Indexed: {d[\"indexed_vectors_count\"]:,} / {d[\"points_count\"]:,}')"
   ```

**Results:**
- ✅ **30,802,486 vectors** fully indexed (100%)
- ✅ **Status: GREEN** - production ready
- ✅ **VSZ usage:** ~600-800 GB (no limit on scc2!)
- ✅ **RSS usage:** ~30-50 GB (actual physical RAM - low due to on-disk)
- ✅ **CPU usage:** Limited to 8 threads (prevents cluster overload)
- ✅ **Segments:** 14 optimized segments
- ✅ **Indexing time:** ~8-12 hours for full 30.8M dataset

**Key Success Factors:**

1. **Mock cgroups workaround** - Fixes Singularity cgroups panic
2. **scc2 unlimited vmem** - No 512GB VSZ limit (critical for mmap)
3. **On-disk HNSW** - Enables indexing 2048-dim vectors without OOM
4. **Thread limiting** - Configured via `max_indexing_threads: 8` to prevent CPU overload
5. **Local scratch storage** - Fast disk I/O for mmap operations

**Checking Virtual Memory Limits on Different Nodes:**

```bash
# Interactive session (no SGE) on scc140
ulimit -v
# Output: 536870912 (512 GB)

# qlogin session (with SGE) on scc140
qlogin -l hostname=scc140
ulimit -v
# Output: 1048576 (1 GB!) - too low!

# Interactive session on scc2
ssh scc2
ulimit -v
# Output: unlimited - perfect for on-disk HNSW!
```

**When to Use This Approach:**

✅ **Use scc2 + mock cgroups for:**
- Large high-dimensional collections (30M+ points, 2048-dim)
- On-disk HNSW requirements (>512GB VSZ needed)
- Production deployments needing full HNSW quality (m=32, ef_construct=256)

❌ **Don't use on scc140 because:**
- 512GB VSZ limit (interactive) or 1GB (qlogin)
- Will fail with "Cannot allocate memory" when mmap hits limit
- Need Option 1 (reduced parameters, in-memory) instead

**Production Recommendation:**

For **patents_compounds** and similar large collections:
1. Deploy on **scc2** (unlimited vmem)
2. Use **on-disk HNSW** (handles 2048-dim efficiently)
3. Set **max_indexing_threads: 8** (prevents CPU overload)
4. Monitor with `curl` commands (check status, indexed count)
5. Wait for **GREEN** status before production queries

This configuration successfully indexed 30.8M chemical fingerprints and is now serving production chemical similarity searches.

## Performance

### Test Mode
- Data: ~2500 vectors total
- Insertion: 5-10 minutes
- Memory: 16GB server, 4GB insertion jobs

### Production Mode
- Data: ~33M vectors total
- Insertion: 2-4 hours
- Memory: 32GB+ server, 16GB insertion jobs
- Storage: 50-100GB

**Optimization Tips**:
- Run server on GPU nodes (more RAM, better I/O)
- Use local SSD instead of NFS for storage
- Increase batch size for faster insertion
- Keep server running for multiple insertions

## Related Documentation

- **Root README**: `../../README.md` - Overall system architecture
- **PubMed Module**: `../pubmed/README.md` - Data processing
- **Clinical Trials Module**: `../clinical_trials/README.md` - Data processing
- **Configuration**: `../../config/README.md` - Config options

---

**Module Version**: 0.2.0
**Last Updated**: October 2025
**Major Changes**: Standalone operation, separated from data processing pipeline
