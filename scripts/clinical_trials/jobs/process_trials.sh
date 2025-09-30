#!/bin/bash
#$ -N ct_process
#$ -q scc
#$ -l h_vmem=64G
#$ -l h_rt=24:00:00
#$ -cwd
#$ -V
#$ -pe smp 4

# Process clinical trials to create FAISS embeddings

set -e

echo "Starting clinical trials processing job..."
echo "Job ID: $JOB_ID"
echo "Hostname: $(hostname)"
echo "CPUs: $NSLOTS"
echo "Timestamp: $(date)"

# Navigate to clinical trials directory
cd /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/clinical_trials

# Activate conda environment
source /home/scc/tgur/programs/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda

# Install required packages if not already installed
pip install sentence-transformers faiss-cpu pandas --quiet

# System information
echo "System Resources:"
echo "  CPUs: $NSLOTS"
echo "  Memory: $(free -h | grep Mem | awk '{print $2}')"

# Run complete processing pipeline
./clinical_trials.sh all

echo "Clinical trials processing job completed: $(date)"