#!/bin/bash
# Monitor Qdrant patent_compounds indexing progress
# Usage: ./check_qdrant_indexing.sh [interval_seconds] [collection]

INTERVAL=${1:-5}
COLLECTION="${2:-patent_compounds}"
HOST="localhost:6333"

echo "Monitoring $COLLECTION indexing (Ctrl+C to stop)..."
echo "============================================================"
echo "BASELINE: 14 segments @ ~2.2M vectors each"
echo "WARNING: If segments grow to 30+, consider reverting!"
echo "============================================================"

while true; do
    curl -s "http://$HOST/collections/$COLLECTION" | python3 -c "
import json, sys
from datetime import datetime
data = json.load(sys.stdin)
result = data.get('result', {})
indexed = result.get('indexed_vectors_count', 0)
total = result.get('points_count', 0)
status = result.get('status')
optimizer = result.get('optimizer_status')
segments = result.get('segments_count', 0)
pct = (indexed / total * 100) if total > 0 else 0
avg_segment_size = total // segments if segments > 0 else 0

# Status indicator
if status == 'green' and indexed == total:
    indicator = '✅ COMPLETE'
elif status == 'yellow':
    indicator = '🔄 INDEXING'
elif indexed == 0:
    indicator = '❌ NOT STARTED'
else:
    indicator = '⏳ IN PROGRESS'

# Segment warning
if segments > 30:
    seg_warn = '⚠️  TOO MANY SEGMENTS!'
elif segments > 20:
    seg_warn = '⚠️  Segments growing'
else:
    seg_warn = '✓'

print(f'[{datetime.now().strftime(\"%H:%M:%S\")}] {indicator}')
print(f'  Status: {status} | Optimizer: {optimizer}')
print(f'  Segments: {segments} (avg {avg_segment_size:,} vectors/segment) {seg_warn}')
print(f'  Indexed: {indexed:,} / {total:,} ({pct:.2f}%)')
print()
"
    sleep $INTERVAL
done
