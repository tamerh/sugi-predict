import os
import gzip
import shutil
import sys
import time
from ftplib import FTP
from tqdm import tqdm
from datetime import datetime

def log(message):
    """Print message with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

# --- Configuration ---
# Will be set from command-line arguments in main()
BASE_DATA_DIR = None
BASELINE_DIR = None
UPDATE_DIR = None

PUBMED_FTP_SERVER = 'ftp.ncbi.nlm.nih.gov'
BASELINE_FTP_PATH = '/pubmed/baseline/'
UPDATE_FTP_PATH = '/pubmed/updatefiles/'
PUBMED_ROOT_PATH = '/pubmed/'

DELETED_PMIDS_GZ = 'deleted.pmids.gz'
DELETED_PMIDS_SORTED_GZ = 'deleted.pmids.sorted.gz'

# --- FTP Helper Functions ---
def download_ftp_file_with_progress(ftp, remote_path, local_path):
    """
    Downloads a single file from an FTP server with a TQDM progress bar.
    Handles potential issues with getting file size.
    Raises exception on download failure.
    """
    total_size = 0
    log(f"Preparing to download {remote_path} to {local_path}...")
    base_name = os.path.basename(local_path)
    try:
        # Attempt to get the file size. This may fail on some servers/modes.
        total_size = ftp.size(remote_path)
    except Exception as e:
        log(f"Warning: Could not determine file size for {base_name}. Error: {str(e) or 'Unknown error'}")

    try:
        with open(local_path, 'wb') as f, tqdm(
            desc=base_name,
            total=total_size if total_size > 0 else None, # Set total to None if size is unknown
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
            disable=True # This will make the progress bar silent
        ) as bar:
            def callback(chunk):
                f.write(chunk)
                bar.update(len(chunk))
            # Use retrbinary for a binary transfer, which is correct for .gz files
            ftp.retrbinary(f'RETR {remote_path}', callback)
        log(f"Successfully downloaded {base_name}")
    except Exception as e:
        error_msg = str(e) if str(e) else f"{type(e).__name__} (no error message)"
        log(f"ERROR: Failed to download {remote_path}: {error_msg}")
        # Clean up partially downloaded file
        if os.path.exists(local_path):
            os.remove(local_path)
        # Re-raise to stop the pipeline
        raise RuntimeError(f"Download failed for {remote_path}: {error_msg}") from e


def download_pubmed_directory(ftp_path, local_dir, limit=None, reconnect_every=50, delay_seconds=1):
    """Downloads all .xml.gz files from a directory with connection management.

    Args:
        ftp_path: Remote FTP path
        local_dir: Local directory to save files
        limit: Optional limit on number of files to download (for debug mode)
        reconnect_every: Reconnect FTP after N files to prevent timeout (default: 50)
        delay_seconds: Seconds to wait between downloads to avoid rate limiting (default: 1)
    """
    os.makedirs(local_dir, exist_ok=True)
    log(f"\n--- Checking directory: {ftp_path} ---")

    # Get file list with initial connection
    with FTP(PUBMED_FTP_SERVER) as ftp:
        ftp.login()
        ftp.cwd(ftp_path)
        filenames = ftp.nlst()

    target_files = [f for f in filenames if f.endswith('.xml.gz')]
    target_files = sorted(target_files)  # Sort for consistent ordering

    if limit is not None:
        log(f"DEBUG MODE: Limiting download to first {limit} files")
        target_files = target_files[:limit]

    log(f"Found {len(target_files)} files to download.")

    downloaded = 0
    for i, filename in enumerate(target_files, 1):
        local_path = os.path.join(local_dir, filename)
        remote_path = f"{ftp_path.rstrip('/')}/{filename}"

        if os.path.exists(local_path):
            log(f"[{i}/{len(target_files)}] Skipping {filename}, already exists.")
            continue

        # Reconnect every N files to prevent timeout
        if downloaded > 0 and downloaded % reconnect_every == 0:
            log(f"[{i}/{len(target_files)}] Reconnecting FTP after {reconnect_every} downloads...")

        log(f"[{i}/{len(target_files)}] Starting download for {filename}...")

        # Use fresh connection for each file to avoid broken pipe
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                with FTP(PUBMED_FTP_SERVER) as ftp:
                    ftp.login()
                    download_ftp_file_with_progress(ftp, remote_path, local_path)
                downloaded += 1

                # Wait between downloads to avoid rate limiting (skip for last file)
                if delay_seconds > 0 and i < len(target_files):
                    time.sleep(delay_seconds)

                break  # Success, exit retry loop
            except Exception as e:
                error_msg = str(e) if str(e) else f"{type(e).__name__}"
                if attempt < max_retries:
                    log(f"[{i}/{len(target_files)}] Retry {attempt}/{max_retries} after error: {error_msg}")
                    time.sleep(2 ** attempt)  # Exponential backoff: 2s, 4s, 8s
                else:
                    log(f"[{i}/{len(target_files)}] FAILED after {max_retries} attempts: {error_msg}")
                    raise

def download_single_file(ftp, ftp_path, filename, local_dir):
    """Downloads a single specific file."""
    os.makedirs(local_dir, exist_ok=True)
    log(f"\n--- Checking for single file: {filename} ---")
    ftp.cwd(ftp_path)
    local_path = os.path.join(local_dir, filename)
    remote_path = f"{ftp_path.rstrip('/')}/{filename}"
    if os.path.exists(local_path):
        log(f"Skipping {filename}, already exists.")
        return True
    log(f"Starting download for {filename}...")
    download_ftp_file_with_progress(ftp, remote_path, local_path)
    return True

# --- Post-Download Processing ---
def sort_deleted_pmids(base_dir):
    """Extracts, sorts, and re-compresses the deleted PMIDs file."""
    gz_path = os.path.join(base_dir, DELETED_PMIDS_GZ)
    sorted_gz_path = os.path.join(base_dir, DELETED_PMIDS_SORTED_GZ)

    if not os.path.exists(gz_path):
        log(f"Error: {DELETED_PMIDS_GZ} not found. Cannot sort.")
        return

    if os.path.exists(sorted_gz_path):
        log(f"{DELETED_PMIDS_SORTED_GZ} already exists. Skipping sort.")
        return

    log(f"Processing {gz_path} to create a sorted version...")
    try:
        with gzip.open(gz_path, 'rt') as f_in:
            pmids = [line.strip() for line in f_in]

        pmids.sort(key=int)

        with gzip.open(sorted_gz_path, 'wt') as f_out:
            for pmid in pmids:
                f_out.write(pmid + '\n')
        log(f"Successfully created sorted file: {sorted_gz_path}")

    except Exception as e:
        log(f"ERROR: Failed to sort PMIDs: {e}")
        raise

# --- Main Execution ---
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Download PubMed data from NCBI FTP')
    parser.add_argument('--raw-dir', required=True, help='Base directory for raw data')
    parser.add_argument('--debug', type=int, default=0, help='Debug mode: limit number of files to download (0 = disabled)')
    parser.add_argument('--test-fixture', default=None, help='Path to test fixture file (skips downloads if present)')

    args = parser.parse_args()

    # Set configuration from arguments
    BASE_DATA_DIR = args.raw_dir
    BASELINE_DIR = os.path.join(BASE_DATA_DIR, 'baseline')
    UPDATE_DIR = os.path.join(BASE_DATA_DIR, 'updatefiles')

    # Ensure directories exist
    os.makedirs(BASE_DATA_DIR, exist_ok=True)
    os.makedirs(BASELINE_DIR, exist_ok=True)
    os.makedirs(UPDATE_DIR, exist_ok=True)

    # Check for test fixture file
    test_fixture_exists = False
    if args.test_fixture:
        test_fixture_exists = os.path.exists(args.test_fixture)
    else:
        # Auto-detect common test fixture names in baseline directory
        common_fixture_names = ['test_abstracts.xml.gz', 'test_pubmed.xml.gz', 'fixture.xml.gz']
        for fixture_name in common_fixture_names:
            fixture_path = os.path.join(BASELINE_DIR, fixture_name)
            if os.path.exists(fixture_path):
                test_fixture_exists = True
                log(f"Auto-detected test fixture: {fixture_path}")
                break

    # If test fixture exists, skip all downloads
    if test_fixture_exists:
        fixture_display = args.test_fixture if args.test_fixture else "auto-detected fixture"
        log("=" * 70)
        log(f"TEST FIXTURE MODE: Using existing fixture file")
        log(f"Fixture: {fixture_display}")
        log("Skipping FTP downloads entirely")
        log("=" * 70)

        # Still download deleted PMIDs if not present
        try:
            deleted_pmids_path = os.path.join(BASE_DATA_DIR, DELETED_PMIDS_GZ)
            if not os.path.exists(deleted_pmids_path):
                log("\nDownloading deleted PMIDs file (required for filtering)...")
                with FTP(PUBMED_FTP_SERVER) as ftp:
                    ftp.login()
                    download_single_file(ftp, PUBMED_ROOT_PATH, DELETED_PMIDS_GZ, BASE_DATA_DIR)
            else:
                log(f"\nDeleted PMIDs file already exists: {deleted_pmids_path}")
        except Exception as e:
            log(f"Warning: Could not download deleted PMIDs file: {e}")
            log("Continuing without deleted PMIDs filtering...")

        # Sort deleted PMIDs if needed
        sort_deleted_pmids(BASE_DATA_DIR)

        log("\nTest fixture mode complete - ready for processing")
        sys.exit(0)

    # Check for debug mode
    debug_mode = args.debug > 0
    debug_limit = args.debug if debug_mode else 3

    if debug_mode:
        log("=" * 70)
        log(f"DEBUG MODE: Limited download ({debug_limit} files)")
        log("=" * 70)
    else:
        log("Starting comprehensive PubMed data acquisition...")

    try:
        # Download deleted PMIDs file first
        with FTP(PUBMED_FTP_SERVER) as ftp:
            ftp.login()
            download_single_file(ftp, PUBMED_ROOT_PATH, DELETED_PMIDS_GZ, BASE_DATA_DIR)

        if debug_mode:
            # Download only limited baseline files, skip updatefiles
            download_pubmed_directory(BASELINE_FTP_PATH, BASELINE_DIR, limit=debug_limit)
            log(f"\nDEBUG MODE: Skipping updatefiles directory")
        else:
            # Full download with automatic reconnection
            download_pubmed_directory(BASELINE_FTP_PATH, BASELINE_DIR)
            download_pubmed_directory(UPDATE_FTP_PATH, UPDATE_DIR)

    except Exception as e:
        error_msg = str(e) if str(e) else f"{type(e).__name__}"
        log(f"FATAL ERROR during FTP process: {error_msg}")
        sys.exit(1)

    sort_deleted_pmids(BASE_DATA_DIR)

    if debug_mode:
        log("\n" + "=" * 70)
        log("DEBUG download complete!")
        log(f"Downloaded {debug_limit} files to: {BASELINE_DIR}")
        log("=" * 70)
    else:
        log("\nAll PubMed data acquisition tasks complete.")

