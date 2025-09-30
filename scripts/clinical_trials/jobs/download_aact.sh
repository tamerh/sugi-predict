#!/bin/bash
#$ -N ct_download
#$ -q scc
#$ -l h_vmem=16G
#$ -l h_rt=4:00:00
#$ -cwd
#$ -V

# Download AACT database snapshot for clinical trials processing

set -e

echo "Starting AACT database download job..."
echo "Job ID: $JOB_ID"
echo "Hostname: $(hostname)"
echo "Timestamp: $(date)"

# Navigate to clinical trials directory
cd /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/clinical_trials

# Activate conda environment
source /home/scc/tgur/programs/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda

# Install required packages if not already installed
pip install requests beautifulsoup4 psycopg2-binary --quiet

# Run download
./clinical_trials.sh download --recreate

echo "AACT download job completed: $(date)"