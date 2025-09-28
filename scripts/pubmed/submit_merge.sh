#!/bin/bash

# --- Configuration ---
LOG_DIR="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/logs/pubmed/merge"

# --- Main Logic ---
echo "starting merge job submission..."
mkdir -p $LOG_DIR


# 2. Submit the single job array command
# The -t flag tells SGE to create an array from 1 to NUM_TASKS
# The log files will now be named uniquely with the job and task ID
qsub -r y -q scc  -N merge_bioyoda -l h_vmem=128000M -pe smp 2 \
     -l h_rt=168:00:00 \
     -o "${LOG_DIR}/pubmed_merge_process.\$JOB_ID.\$TASK_ID.out" \
     -e "${LOG_DIR}/pubmed_merge_process.\$JOB_ID.\$TASK_ID.err" \
      run_merge_job.sh

echo "Job submitted."
