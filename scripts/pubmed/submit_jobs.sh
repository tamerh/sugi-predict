#!/bin/bash

# --- Configuration ---
FILE_LIST="all_files_to_process.txt"
LOG_DIR="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/logs"

# --- Main Logic ---
echo "Starting job array submission..."
mkdir -p $LOG_DIR

# 1. Get the total number of tasks from our file list
NUM_TASKS=$(wc -l < $FILE_LIST)
echo "Submitting a job array with ${NUM_TASKS} tasks."

# 2. Submit the single job array command
# The -t flag tells SGE to create an array from 1 to NUM_TASKS
# The log files will now be named uniquely with the job and task ID
qsub -r y -q scc \
     -l h_rt=168:00:00 \
     -o "${LOG_DIR}/pubmed_process.\$JOB_ID.\$TASK_ID.out" \
     -e "${LOG_DIR}/pubmed_process.\$JOB_ID.\$TASK_ID.err" \
     -t 1-${NUM_TASKS} \
     run_job2.sh

echo "Job array submitted."
