#!/bin/bash

# Helper script to set up automated backups via cron

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup.sh"

echo "=========================================="
echo "Backup Cron Setup Helper"
echo "=========================================="
echo ""

# Check if backup script exists
if [ ! -f "$BACKUP_SCRIPT" ]; then
    echo "ERROR: Backup script not found at $BACKUP_SCRIPT"
    exit 1
fi

# Make sure it's executable
chmod +x "$BACKUP_SCRIPT"

echo "This script will help you set up automated backups."
echo ""
echo "Backup script location: $BACKUP_SCRIPT"
echo "Source: /data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2/"
echo "Destination: /data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2.bkp"
echo ""
echo "Available options:"
echo "1. Run backup now (test)"
echo "2. Set up cron job (every 12 hours)"
echo "3. Set up cron job (daily at 2 AM)"
echo "4. Set up cron job (custom schedule)"
echo "5. Show existing cron jobs"
echo "6. Remove backup cron job"
echo "7. Exit"
echo ""

read -p "Select an option (1-7): " option

case $option in
    1)
        echo ""
        echo "Running backup now..."
        "$BACKUP_SCRIPT"
        ;;
    2)
        CRON_LINE="0 */12 * * * $BACKUP_SCRIPT >/dev/null 2>&1"
        (crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT"; echo "$CRON_LINE") | crontab -
        echo ""
        echo "Cron job added! Backup will run every 12 hours."
        echo "Schedule: Every day at 00:00 and 12:00"
        ;;
    3)
        CRON_LINE="0 2 * * * $BACKUP_SCRIPT >/dev/null 2>&1"
        (crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT"; echo "$CRON_LINE") | crontab -
        echo ""
        echo "Cron job added! Backup will run daily at 2:00 AM."
        ;;
    4)
        echo ""
        echo "Cron format: minute hour day month weekday"
        echo "Examples:"
        echo "  0 */6 * * *    - Every 6 hours"
        echo "  0 0,12 * * *   - At midnight and noon"
        echo "  30 3 * * *     - Daily at 3:30 AM"
        echo ""
        read -p "Enter cron schedule: " schedule
        CRON_LINE="$schedule $BACKUP_SCRIPT >/dev/null 2>&1"
        (crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT"; echo "$CRON_LINE") | crontab -
        echo ""
        echo "Cron job added with custom schedule: $schedule"
        ;;
    5)
        echo ""
        echo "Current cron jobs:"
        crontab -l 2>/dev/null || echo "No cron jobs found"
        ;;
    6)
        crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT" | crontab -
        echo ""
        echo "Backup cron job removed (if it existed)"
        ;;
    7)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid option"
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "Current cron jobs:"
crontab -l 2>/dev/null || echo "No cron jobs found"
echo "=========================================="
echo ""
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
echo "To view backup logs: tail -f ${PROJECT_ROOT}/logs/backup.log"
echo "To run backup manually: $BACKUP_SCRIPT"
echo ""
