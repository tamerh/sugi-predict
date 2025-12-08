#!/bin/bash
# Interactive LLM test script

echo "Starting BioYoda LLM Interactive Test..."
echo ""

# Run with conda environment
conda run -n bioyoda python modules/agent_system/tests/interactive_llm_test.py
