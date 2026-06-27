# Virtual Memory Limit Investigation for Qdrant On-Disk HNSW

## Current Situation

**Node:** scc140
**Date:** October 30, 2025

### Observed Limits

```
Physical RAM:        472 GB
Swap:               143 GB
Total:              615 GB

Shell VSZ Limit:    512 GB  (Max address space)
Shell RSS Limit:    254 GB  (Max resident set)
```

### The Problem

Qdrant on-disk HNSW indexing for our patent_compounds collection requires:
- 30.8M points × 2048 dimensions
- mmap operations for on-disk storage
- **Estimated VSZ needed: >512GB** (even though RSS stays low ~30-50GB)

When optimizer starts, mmap allocations fail with:
```
Cannot allocate memory (os error 12)
VSZ: 500GB (already at limit)
VSZ limit: 512GB
```

## Root Cause Analysis

### 1. This is NOT an SGE Job Limit

We are currently in an **interactive session**, not an SGE job:
- `$JOB_ID` is not set
- No SGE resource limits applied
- Getting default shell limits from the system

### 2. SGE Queue Limits (for reference)

When submitting jobs to `scc` queue:

| Hostgroup | h_vmem Limit |
|-----------|--------------|
| Default | 320 GB |
| @scc-sandy-128GB | 160 GB |
| @scc-haswell-128GB | 160 GB |
| @scc-haswell-64GB | 96 GB |

**Note:** These are LOWER than the interactive session limit (512GB)!

### 3. The 512GB Limit Source

The 512GB VSZ limit comes from:
- System-wide shell default (ulimit)
- Set via `/etc/security/limits.conf` or similar
- Applied to all interactive sessions
- NOT related to SGE job scheduler

## Diagnostic Commands Used

Here are the commands used to gather this information:

### Check Process Limits
```bash
# Current shell limits
cat /proc/self/limits

# Qdrant process limits (get PID first)
ps aux | grep '[q]drant' | head -1
cat /proc/<PID>/limits

# Convert to GB
echo "VSZ: $((549755813888 / 1024 / 1024 / 1024)) GB"
echo "RSS: $((272730423296 / 1024 / 1024 / 1024)) GB"
```

### Check System Memory
```bash
# Physical memory
free -h

# Total available
grep MemTotal /proc/meminfo
```

### Check SGE Configuration
```bash
# Check if in SGE job
echo $JOB_ID

# Queue limits
qconf -sq scc | grep -E "h_vmem|s_vmem"

# Complex configuration
qconf -sc | grep vmem

# Available hostgroups
qconf -shgrpl
```

### Check Current Environment
```bash
# SGE environment variables
env | grep -E "^SGE_|^JOB_|^QUEUE" | sort

# Current hostname
hostname

# ulimit settings (all)
ulimit -a
```

### Monitor Qdrant Memory Usage
```bash
# Real-time monitoring
ps aux | grep '[q]drant'

# Detailed process info
top -p <PID>

# Or use ps with custom format
ps -p <PID> -o pid,vsz,rss,cmd
```

### Check Qdrant Logs for Errors
```bash
# Check for memory allocation errors
grep -i "cannot allocate memory\|out of memory" logs/qdrant/*.log

# Check optimizer status via API
curl -s http://localhost:6333/collections/patent_compounds | \
  python3 -c "import sys,json; d=json.load(sys.stdin)['result']; \
  print(f\"Optimizer: {d.get('optimizer_status', 'OK')}\")"
```

## Questions for System Administrator

### Priority 1: Can the Node Support Higher VSZ?

**Question:**
*"Node scc140 has 472GB RAM + 143GB swap = 615GB total. Can the max address space limit (currently 512GB) be increased to support larger memory-mapped file operations?"*

**Technical details:**
- Current: `ulimit -v` = 512GB (549755813888 bytes)
- Request: Increase to 1TB or unlimited for specific users/groups
- Use case: Memory-mapped vector indexing (low RSS, high VSZ)
- File: Likely `/etc/security/limits.conf`

### Priority 2: SGE Job Memory Requests

**Question:**
*"Can we request higher h_vmem when submitting SGE jobs? For example, can we do: `qsub -l h_vmem=800G` for memory-mapped operations?"*

**Technical details:**
- SGE complex shows h_vmem is requestable
- Default queue limit: 320GB
- Need: 800GB-1TB for large-scale vector indexing
- Would only use ~50GB actual RAM (RSS)

### Priority 3: Alternative Solutions

**Question:**
*"Are there specific nodes or hostgroups with higher virtual memory limits configured for large-scale data processing?"*

### Why We Need This

**Qdrant on-disk HNSW indexing:**
- Uses mmap (memory-mapped files) for efficient disk-based indexing
- mmap counts against VSZ (virtual memory) but NOT RSS (physical memory)
- Our data: 30.8M vectors × 2048 dimensions = requires ~600-800GB VSZ
- Actual memory usage: Only ~30-50GB RSS

**Benefits of on-disk HNSW:**
- Dramatically lower memory usage (30GB vs 140GB)
- Enables indexing of larger datasets
- Standard approach for large vector databases

**Current workaround:**
- Using in-memory HNSW with reduced parameters
- Works but uses more RAM and lower search quality
- Would prefer on-disk for production

## Recommendations

### Short Term (Immediate)

1. **Continue with in-memory HNSW** (Option 1 from our docs)
   - `hnsw_m: 16` (reduced from 32)
   - `hnsw_ef_construct: 128` (reduced from 256)
   - Memory: ~70-80GB (fits in 254GB limit)
   - Quality: Acceptable for most use cases

### Medium Term (After Admin Response)

2. **If higher VSZ limit available:**
   - Test on-disk HNSW with increased VSZ limit
   - Expected to work perfectly with 1TB VSZ limit
   - Would enable production-scale deployment

3. **If higher h_vmem allowed in SGE:**
   - Submit Qdrant server as SGE job with:
     ```bash
     qsub -l h_vmem=800G -l h_rt=172800 ...
     ```
   - Run in cluster mode instead of interactive

## Test Plan (Once Limits Increased)

```bash
# 1. Verify new limit
ulimit -v  # Should show new limit

# 2. Start Qdrant with mock cgroups
./bioyoda.sh qdrant start --mock-cgroups

# 3. Test on-disk HNSW indexing
# Collection should index without "Cannot allocate memory" error

# 4. Monitor memory usage
ps aux | grep qdrant
# VSZ can be >512GB, RSS should stay ~30-50GB
```

## Files for Reference

- **Documentation:** `modules/qdrant/README.md` (section: "Mock cgroups Workaround")
- **Implementation:** `modules/qdrant/scripts/start_server.sh` (mock cgroups code)
- **Configuration:** `config/config.yaml` (HNSW settings)
- **This analysis:** `modules/qdrant/VIRTUAL_MEMORY_LIMIT_INVESTIGATION.md`

## Contact

Feel free to reach out if you need:
- More technical details about our use case
- Performance benchmarks
- Testing assistance once limits are adjusted

---

**Summary for Admin:** We need higher VSZ limits (512GB → 1TB+) for memory-mapped file operations with Qdrant vector database. Physical RAM usage will stay low (~50GB), but virtual memory needs are high due to mmap.
