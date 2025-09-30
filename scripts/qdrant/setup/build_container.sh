#!/bin/bash
#$ -N build_qdrant
#$ -q scc
#$ -l h_vmem=8G
#$ -l h_rt=1:00:00
#$ -cwd
#$ -V

# Build Qdrant Singularity container for HPC cluster

set -e

echo "Building Qdrant Singularity container..."
echo "Timestamp: $(date)"

# Change to singularity directory
cd singularity/

# Build the container
singularity build qdrant.sif qdrant.def

echo "Container build completed: $(pwd)/qdrant.sif"
echo "Container size: $(du -h qdrant.sif)"

# Test the container
echo "Testing container..."
singularity exec qdrant.sif /qdrant/qdrant --help

echo "Build process completed successfully!"