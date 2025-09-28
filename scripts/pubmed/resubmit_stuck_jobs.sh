#!/bin/bash

# --- Configuration ---
# The complete list of all task IDs that were stuck or failed.
STUCK_TASKS="98 99 100 101 102 103 104 105 106 107 108 109 329 330 576 577 578 579 580"
LOG_DIR="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/logs"

echo "Starting resubmission of specific stuck tasks..."

# --- Main Loop ---
# This loop will iterate through each number in the STUCK_TASKS string.
for TASK_ID in $STUCK_TASKS; do
    echo "Resubmitting job for Task ID: ${TASK_ID}"
    
    # We submit one job for each task. The -t flag with a single number
    # creates a job array of size 1, which is a clean way to do this.
    qsub -r y -q scc \
         -l h_rt=168:00:00 \
         -l h_vmem=8G \
         -pe smp 1 \
         -o "${LOG_DIR}/pubmed_process.\$JOB_ID.${TASK_ID}.out" \
         -e "${LOG_DIR}/pubmed_process.\$JOB_ID.${TASK_ID}.err" \
         -t ${TASK_ID} \
         run_job.sh
done

echo "All stuck jobs have been resubmitted."