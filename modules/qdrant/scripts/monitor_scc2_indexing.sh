#!/bin/bash
# Monitor Qdrant indexing progress on scc2

echo "Monitoring Qdrant on scc2 (PID: 117918)"
echo "Press Ctrl+C to stop"
echo ""

while true; do
    timestamp=$(date '+%H:%M:%S')

    # Get collection status
    status_json=$(curl -s "http://scc2:6333/collections/patents_compounds" 2>/dev/null)
    status=$(echo "$status_json" | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['status'])" 2>/dev/null)
    indexed=$(echo "$status_json" | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['indexed_vectors_count'])" 2>/dev/null)
    total=$(echo "$status_json" | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['points_count'])" 2>/dev/null)

    # Get memory usage
    mem_info=$(ssh scc2 "ps -o vsz=,rss= -p 117918 2>/dev/null")
    vsz_gb=$(echo "$mem_info" | awk '{printf "%.1f", $1/1024/1024}')
    rss_gb=$(echo "$mem_info" | awk '{printf "%.1f", $2/1024/1024}')

    # Calculate percentage
    if [ -n "$indexed" ] && [ -n "$total" ] && [ "$total" -gt 0 ]; then
        pct=$(echo "scale=2; $indexed * 100 / $total" | bc)
    else
        pct="0.00"
    fi

    echo "[$timestamp] Status: $status | Indexed: $indexed / $total ($pct%) | VSZ: ${vsz_gb}GB | RSS: ${rss_gb}GB"

    sleep 30
done
