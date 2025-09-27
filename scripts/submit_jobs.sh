#!/bin/bash

# --- Configuration ---
# Base path for the raw data
BASE_DATA_DIR="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/raw/pubmed"
# Base path for the processed output
BASE_OUTPUT_DIR="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/processed/pubmed"

# Specific input directories based on the download script's structure
BASELINE_INPUT_DIR="${BASE_DATA_DIR}/baseline"
UPDATEFILES_INPUT_DIR="${BASE_DATA_DIR}/updatefiles"

# Specific output directories to keep results organized
BASELINE_OUTPUT_DIR="${BASE_OUTPUT_DIR}/baseline"
UPDATEFILES_OUTPUT_DIR="${BASE_OUTPUT_DIR}/updatefiles"

# --- Main Logic ---

echo "Starting job submission process..."
# Create the output directories if they don't exist
mkdir -p $BASELINE_OUTPUT_DIR
mkdir -p $UPDATEFILES_OUTPUT_DIR

# --- Submit jobs for BASELINE files ---
echo "--- Submitting jobs for BASELINE files in ${BASELINE_INPUT_DIR} ---"
for F in $(find $BASELINE_INPUT_DIR -name "*.xml.gz"); do
    echo "Submitting baseline job for file: $F"

    # Submit the job, directing output to the baseline output directory
    qsub -r y -q scc -pe smp 1 -l h_rt=168:00:00 \
    -l h_vmem=16000M -N pm_base_proc \
    -j y -e /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/logs \
    -o /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/logs \
    -v INPUT_FILE=$F,OUTPUT_DIR=$BASELINE_OUTPUT_DIR run_job.sh
done

# --- Submit jobs for UPDATEFILES ---
echo "--- Submitting jobs for UPDATEFILES in ${UPDATEFILES_INPUT_DIR} ---"
for F in $(find $UPDATEFILES_INPUT_DIR -name "*.xml.gz"); do
    echo "Submitting update job for file: $F"

    # Submit the job, directing output to the updatefiles output directory
    qsub -r y -q scc -pe smp 1 -l h_rt=168:00:00 \
    -l h_vmem=16000M -N pm_update_proc \
    -j y -e /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/logs \
    -o /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/logs \
    -v INPUT_FILE=$F,OUTPUT_DIR=$UPDATEFILES_OUTPUT_DIR run_job.sh
done

echo "All jobs submitted."
