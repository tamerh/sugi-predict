# Automated Backup System

This directory contains scripts for automated backups of the bioyoda_dev2 project.

## Quick Start

### Option 1: Interactive Setup (Recommended)
```bash
cd /data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2
./scripts/setup_backup_cron.sh
```

This will show you a menu to:
- Test the backup
- Set up automated backups (every 12 hours)
- View/manage cron jobs

### Option 2: Manual Setup

#### Test the backup first:
```bash
./scripts/backup.sh
```

#### Set up cron job for every 12 hours:
```bash
# Add to crontab
(crontab -l 2>/dev/null; echo "0 */12 * * * /data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2/scripts/backup.sh >/dev/null 2>&1") | crontab -
```

## Backup Details

- **Source**: `/data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2/`
- **Destination**: `/data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2.bkp`
- **Method**: rsync (incremental, efficient)
- **Schedule**: Every 12 hours (customizable)

## What Gets Backed Up

Everything in the source directory EXCEPT:
- Temporary files (`*.tmp`, `*.swp`)
- Git objects (to save space)
- Generated wrapper scripts (`run_*.sh`)
- Core dumps
- nohup.out files

## Monitoring

### View backup logs:
```bash
tail -f logs/backup.log
```

### Check last backup:
```bash
ls -lh /data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2.bkp
```

### View current cron jobs:
```bash
crontab -l
```

## Cron Schedule Examples

- Every 12 hours: `0 */12 * * *`
- Every 6 hours: `0 */6 * * *`
- Daily at 2 AM: `0 2 * * *`
- Twice daily (2 AM and 2 PM): `0 2,14 * * *`

## Manual Backup

To run a backup manually at any time:
```bash
./scripts/backup.sh
```

## Restoring from Backup

If you need to restore:
```bash
rsync -avh --delete /data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2.bkp/ /data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2/
```

**WARNING**: This will overwrite current files with backup versions!

## Removing Automated Backup

To remove the cron job:
```bash
crontab -l | grep -v backup.sh | crontab -
```

Or use the interactive setup script (option 6).

## Disk Space

The backup uses rsync which is very efficient:
- First backup: Full copy
- Subsequent backups: Only changed files are copied
- Deleted files in source are removed from backup (--delete flag)

Monitor disk usage:
```bash
du -sh /data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2
du -sh /data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2.bkp
```

## Troubleshooting

### Check if cron is running:
```bash
systemctl status cron   # or crond on some systems
```

### Check cron logs:
```bash
grep CRON /var/log/syslog  # or /var/log/cron
```

### Verify backup script permissions:
```bash
ls -l scripts/backup.sh
# Should show: -rwxr-xr-x
```

### Test rsync manually:
```bash
rsync -avhn --delete /data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2/ /data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2.bkp
# (The 'n' flag does a dry-run without actually copying)
```
