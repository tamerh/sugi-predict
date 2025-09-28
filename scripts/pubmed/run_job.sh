#!/bin/bash
# --- SGE (Sun Grid Engine) Directives ---
#$ -N pubmed_process_array  # Job Name for the whole array
#$ -cwd                     # Run from the current working directory
#$ -j y                     # Merge standard error and standard out
#$ -l h_vmem=8G             # Request 8GB of memory (adjusted based on our findings)
#$ -pe smp 1                # Request 1 CPU core

# --- Main Logic ---
echo "Job Array Task ${SGE_TASK_ID} running on host: $(hostname)"

# 1. Get the input file for this specific task from the master list
FILE_LIST="all_files_to_process.txt"
INPUT_FILE=$(sed -n "${SGE_TASK_ID}p" $FILE_LIST)

# 2. Determine the correct output directory based on the input path
BASE_OUTPUT_DIR="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/processed/pubmed"
if [[ $INPUT_FILE == *"baseline"* ]]; then
    OUTPUT_DIR="${BASE_OUTPUT_DIR}/baseline"
else
    OUTPUT_DIR="${BASE_OUTPUT_DIR}/updatefiles"
fi

echo "Input file: ${INPUT_FILE}"
echo "Output dir: ${OUTPUT_DIR}"
mkdir -p $OUTPUT_DIR

# 3. Set up the Conda environment
# IMPORTANT: Replace with the actual path to your Conda installation
source /home/scc/tgur/programs/miniconda3/etc/profile.d/conda.sh
conda activate biotech_engine

# 4. Execute the Python script
python process_single_file.py "${INPUT_FILE}" "${OUTPUT_DIR}"

echo "Task ${SGE_TASK_ID} finished successfully."
