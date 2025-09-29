#!/bin/bash
# --- SGE (Sun Grid Engine) Directives ---
#$ -N pubmed_process_array  # Job Name for the whole array
#$ -cwd                     # Run from the current working directory
#$ -j y                     # Merge standard error and standard out
#$ -l h_vmem=128000M        # Request 128GB of memory (adjusted based on our findings)
#$ -pe smp 2                # Request 2 CPU cores

# --- Main Logic ---
source "/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/pubmed/pubmed.env"

# 3. Set up the Conda environment
# IMPORTANT: Replace with the actual path to your Conda installation
source /home/scc/tgur/programs/miniconda3/etc/profile.d/conda.sh
conda activate "$CONDA_ENV"

# 4. Execute the Python script
cd "$SCRIPTS_DIR" || { echo "Failed to change directory to $SCRIPTS_DIR"; exit 1; }
python merge0.py

echo "Job submitted"
