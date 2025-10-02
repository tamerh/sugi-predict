import os
import gzip
import shutil
from ftplib import FTP
from tqdm import tqdm
from config_loader import get_config

# --- Configuration ---
config = get_config()
BASE_DATA_DIR = str(config.get_path('BASE_DATA_DIR'))
BASELINE_DIR = os.path.join(BASE_DATA_DIR, 'baseline')
UPDATE_DIR = os.path.join(BASE_DATA_DIR, 'updatefiles')

# Ensure directories exist
os.makedirs(BASE_DATA_DIR, exist_ok=True)
os.makedirs(BASELINE_DIR, exist_ok=True)
os.makedirs(UPDATE_DIR, exist_ok=True)

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
    """
    total_size = 0
    print(f"Preparing to download {remote_path} to {local_path}...")
    base_name = os.path.basename(local_path)
    try:
        # Attempt to get the file size. This may fail on some servers/modes.
        total_size = ftp.size(remote_path)
    except Exception as e:
        print(f"Warning: Could not determine file size for {base_name}. Progress bar may not show total. Error: {e}")

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
        print(f"Successfully downloaded {base_name}")
    except Exception as e:
        print(f"Error during download of {remote_path}: {e}")
        # Clean up partially downloaded file
        if os.path.exists(local_path):
            os.remove(local_path)


def download_pubmed_directory(ftp, ftp_path, local_dir, limit=None):
    """Downloads all .xml.gz files from a directory.

    Args:
        ftp: FTP connection object
        ftp_path: Remote FTP path
        local_dir: Local directory to save files
        limit: Optional limit on number of files to download (for debug mode)
    """
    os.makedirs(local_dir, exist_ok=True)
    print(f"\n--- Checking directory: {ftp_path} ---")
    ftp.cwd(ftp_path)
    filenames = ftp.nlst()
    target_files = [f for f in filenames if f.endswith('.xml.gz')]
    target_files = sorted(target_files)  # Sort for consistent ordering

    if limit is not None:
        print(f"DEBUG MODE: Limiting download to first {limit} files")
        target_files = target_files[:limit]

    print(f"Found {len(target_files)} files to download.")
    for filename in target_files:
        local_path = os.path.join(local_dir, filename)
        remote_path = f"{ftp_path.rstrip('/')}/{filename}"
        if os.path.exists(local_path):
            print(f"Skipping {filename}, already exists.")
            continue
        print(f"Starting download for {filename}...")
        download_ftp_file_with_progress(ftp, remote_path, local_path)

def download_single_file(ftp, ftp_path, filename, local_dir):
    """Downloads a single specific file."""
    os.makedirs(local_dir, exist_ok=True)
    print(f"\n--- Checking for single file: {filename} ---")
    ftp.cwd(ftp_path)
    local_path = os.path.join(local_dir, filename)
    remote_path = f"{ftp_path.rstrip('/')}/{filename}"
    if os.path.exists(local_path):
        print(f"Skipping {filename}, already exists.")
        return True
    print(f"Starting download for {filename}...")
    download_ftp_file_with_progress(ftp, remote_path, local_path)
    return True

# --- Post-Download Processing ---
def sort_deleted_pmids(base_dir):
    """Extracts, sorts, and re-compresses the deleted PMIDs file."""
    gz_path = os.path.join(base_dir, DELETED_PMIDS_GZ)
    sorted_gz_path = os.path.join(base_dir, DELETED_PMIDS_SORTED_GZ)
    
    if not os.path.exists(gz_path):
        print(f"Error: {DELETED_PMIDS_GZ} not found. Cannot sort.")
        return

    if os.path.exists(sorted_gz_path):
        print(f"{DELETED_PMIDS_SORTED_GZ} already exists. Skipping sort.")
        return

    print(f"Processing {gz_path} to create a sorted version...")
    try:
        with gzip.open(gz_path, 'rt') as f_in:
            pmids = [line.strip() for line in f_in]
        
        pmids.sort(key=int)
        
        with gzip.open(sorted_gz_path, 'wt') as f_out:
            for pmid in pmids:
                f_out.write(pmid + '\n')
        print(f"Successfully created sorted file: {sorted_gz_path}")

    except Exception as e:
        print(f"An error occurred while sorting PMIDs: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    import sys

    # Check for debug mode argument
    debug_mode = False
    debug_limit = 3
    if len(sys.argv) > 1 and sys.argv[1] == '--debug':
        debug_mode = True
        if len(sys.argv) > 2:
            try:
                debug_limit = int(sys.argv[2])
            except ValueError:
                print(f"Invalid debug limit, using default: {debug_limit}")
        print("=" * 70)
        print(f"DEBUG MODE: Limited download ({debug_limit} files)")
        print("=" * 70)
    else:
        print("Starting comprehensive PubMed data acquisition...")

    try:
        with FTP(PUBMED_FTP_SERVER) as ftp:
            ftp.login()
            download_single_file(ftp, PUBMED_ROOT_PATH, DELETED_PMIDS_GZ, BASE_DATA_DIR)

            if debug_mode:
                # Download only limited baseline files, skip updatefiles
                download_pubmed_directory(ftp, BASELINE_FTP_PATH, BASELINE_DIR, limit=debug_limit)
                print(f"\nDEBUG MODE: Skipping updatefiles directory")
            else:
                # Full download
                download_pubmed_directory(ftp, BASELINE_FTP_PATH, BASELINE_DIR)
                download_pubmed_directory(ftp, UPDATE_FTP_PATH, UPDATE_DIR)

    except Exception as e:
        print(f"An error occurred during the main FTP process: {e}")

    sort_deleted_pmids(BASE_DATA_DIR)

    if debug_mode:
        print("\n" + "=" * 70)
        print("DEBUG download complete!")
        print(f"Downloaded {debug_limit} files to: {BASELINE_DIR}")
        print("=" * 70)
    else:
        print("\nAll PubMed data acquisition tasks complete.")

