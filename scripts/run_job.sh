#!/bin/bash

# --- Main Logic ---
echo "Job running on host: $(hostname)"
echo "Received input file: ${INPUT_FILE}"
echo "Will write output to: ${OUTPUT_DIR}"

# 1. Set up the Conda environment
# IMPORTANT: Replace with the actual path to your Conda installation
source /home/scc/tgur/programs/miniconda3/etc/profile.d/conda.sh
conda activate biotech_engine

# 2. Execute the Python script
# The variables $INPUT_FILE and $OUTPUT_DIR will be passed in by qsub
python process_single_file.py "${INPUT_FILE}" "${OUTPUT_DIR}"

echo "Job finished successfully."