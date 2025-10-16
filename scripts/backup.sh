#!/bin/bash

# Backup script for bioyoda_dev2 project
# This script uses rsync to create incremental backups

# Configuration
SOURCE_DIR="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2/"
BACKUP_DIR="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2.bkp"
LOG_DIR="${SOURCE_DIR}/logs"
LOG_FILE="${LOG_DIR}/backup.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_message "========================================"
log_message "Starting backup process"

# Check if source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    log_message "ERROR: Source directory does not exist: $SOURCE_DIR"
    exit 1
fi

# Create backup directory if it doesn't exist
if [ ! -d "$BACKUP_DIR" ]; then
    log_message "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
fi

# Calculate directory size before backup
SOURCE_SIZE=$(du -sh "$SOURCE_DIR" 2>/dev/null | cut -f1)
log_message "Source directory size: $SOURCE_SIZE"

# Rsync options:
# -a: archive mode (preserves permissions, timestamps, etc.)
# -v: verbose
# -h: human-readable
# --delete: delete files in destination that don't exist in source
# --exclude: exclude certain patterns
# --stats: show transfer statistics

log_message "Running rsync..."

rsync -avh \
    --delete \
    --exclude='*.tmp' \
    --exclude='*.swp' \
    --exclude='.git/objects' \
    --exclude='nohup.out' \
    --exclude='run_*.sh' \
    --exclude='core.*' \
    --stats \
    "$SOURCE_DIR" \
    "$BACKUP_DIR" 2>&1 | tee -a "$LOG_FILE"

# Check rsync exit status
RSYNC_EXIT=$?

if [ $RSYNC_EXIT -eq 0 ]; then
    log_message "Backup completed successfully"
    BACKUP_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
    log_message "Backup directory size: $BACKUP_SIZE"
else
    log_message "ERROR: Backup failed with exit code $RSYNC_EXIT"
    exit $RSYNC_EXIT
fi

# Keep only last 30 days of logs
find "$LOG_DIR" -name "backup.log.*" -type f -mtime +30 -delete 2>/dev/null

log_message "Backup process finished"
log_message "========================================"

# Rotate log file if it gets too large (>10MB)
LOG_SIZE=$(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null)
if [ "$LOG_SIZE" -gt 10485760 ]; then
    mv "$LOG_FILE" "$LOG_FILE.$(date '+%Y%m%d_%H%M%S')"
    log_message "Log file rotated"
fi
