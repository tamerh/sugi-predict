#!/bin/bash

# --- Configuration ---
BASE_DATA_DIR="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/raw/pubmed"
BASELINE_INPUT_DIR="${BASE_DATA_DIR}/baseline"
UPDATEFILES_INPUT_DIR="${BASE_DATA_DIR}/updatefiles"

# The master list of all files to be processed
FILE_LIST="all_files_to_process.txt"

# --- Main Logic ---
echo "Creating master file list at ${FILE_LIST}..."

# Find all .xml.gz files in both directories and write their full paths to the list
# Use > to create/overwrite the file with the baseline list
find $BASELINE_INPUT_DIR -name "*.xml.gz" > $FILE_LIST
# Use >> to append the updatefiles list to the same file
find $UPDATEFILES_INPUT_DIR -name "*.xml.gz" >> $FILE_LIST

# Get the total number of tasks
NUM_TASKS=$(wc -l < $FILE_LIST)
echo "Found ${NUM_TASKS} files to process."
