"""
End-to-end test for PubMed pipeline

This test actually RUNS the full pipeline in test mode and validates output.
Uses test_out/ directory for all outputs (easy to inspect and debug).

With test config (2 files, 100 abstracts): Should take ~10-15 minutes.

Usage:
    ./run_tests.sh pubmed  (includes E2E)
    pytest tests/integration/test_pubmed_e2e.py -m e2e -v
"""
import pytest
import subprocess
import json
import faiss
import shutil
from pathlib import Path
import yaml


@pytest.fixture(scope="module")
def run_pipeline_e2e():
    """Actually run the pipeline using test_out/ directory"""
    project_root = Path(__file__).parent.parent.parent
    test_config_path = project_root / 'config' / 'test_config.yaml'

    # Load test config (already points to test_out/)
    with open(test_config_path) as f:
        config = yaml.safe_load(f)

    output_dir = Path(config['base_dir'])

    # Clean test_out/ if it exists (fresh start for each test run)
    if output_dir.exists():
        print(f"\n{'='*80}")
        print(f"Cleaning previous test output: {output_dir}")
        print(f"{'='*80}\n")
        shutil.rmtree(output_dir)

    # Run pipeline
    cmd = [
        str(project_root / 'bioyoda.sh'),
        'run', 'pubmed',
        '--config', str(test_config_path),
        '--local',
        '--cores', '2'
    ]

    print(f"\n{'='*80}")
    print(f"Running E2E Pipeline: {' '.join(cmd)}")
    print(f"Output directory: {output_dir}")
    print(f"Config: debug_mode={config['pubmed'].get('debug_mode')}, "
          f"debug_sample_size={config['pubmed'].get('debug_sample_size')}, "
          f"test_abstracts_limit={config['pubmed'].get('test_abstracts_limit')}")
    print(f"{'='*80}\n")

    result = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=1800  # 30 minute timeout (should be enough for 2 files)
    )

    return {
        'returncode': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'config': config,
        'output_dir': output_dir,
        'project_root': project_root
    }


class TestPubMedEndToEnd:
    """End-to-end tests that actually run the pipeline"""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_pipeline_runs_successfully(self, run_pipeline_e2e):
        """Test that pipeline completes without errors"""
        result = run_pipeline_e2e

        if result['returncode'] != 0:
            print(f"\n{'='*80}")
            print("PIPELINE FAILED")
            print(f"{'='*80}")
            print("\nSTDOUT:")
            print(result['stdout'])
            print("\nSTDERR:")
            print(result['stderr'])
            print(f"{'='*80}\n")

        assert result['returncode'] == 0, \
            f"Pipeline failed with return code {result['returncode']}"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_downloads_test_data(self, run_pipeline_e2e):
        """Test that test mode downloaded limited files"""
        output_dir = run_pipeline_e2e['output_dir']
        config = run_pipeline_e2e['config']

        raw_dir = output_dir / 'raw_data' / 'pubmed' / 'baseline'
        assert raw_dir.exists(), "Raw data directory not created"

        xml_files = list(raw_dir.glob('*.xml.gz'))

        # In test mode with debug_sample_size=2, should have 2 files
        if config['pubmed'].get('debug_mode'):
            expected_files = config['pubmed'].get('debug_sample_size', 2)
            assert len(xml_files) == expected_files, \
                f"Expected {expected_files} files in test mode, got {len(xml_files)}"
        else:
            assert len(xml_files) > 0, "No XML files downloaded"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_processes_with_limit(self, run_pipeline_e2e):
        """Test that test mode processes limited abstracts per file"""
        output_dir = run_pipeline_e2e['output_dir']
        config = run_pipeline_e2e['config']

        processed_dir = output_dir / 'data' / 'processed' / 'pubmed' / 'baseline'
        assert processed_dir.exists(), "Processed directory not created"

        index_files = list(processed_dir.glob('*.index'))
        assert len(index_files) > 0, "No index files created"

        # Check vector counts
        if config['pubmed'].get('test_mode'):
            limit = config['pubmed'].get('test_abstracts_limit', 100)

            for index_file in index_files:
                index = faiss.read_index(str(index_file))
                # Allow some variance for deleted PMIDs filtering
                assert 50 <= index.ntotal <= limit + 50, \
                    f"{index_file.name} has {index.ntotal} vectors, expected ~{limit}"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_processed_indices_valid(self, run_pipeline_e2e):
        """Test that processed indices are valid FAISS indices"""
        output_dir = run_pipeline_e2e['output_dir']
        processed_dir = output_dir / 'data' / 'processed' / 'pubmed' / 'baseline'

        index_files = list(processed_dir.glob('*.index'))
        assert len(index_files) > 0, "No processed index files found"

        # Validate each index
        for index_file in index_files:
            index = faiss.read_index(str(index_file))
            assert index.ntotal > 0, f"{index_file.name} is empty"
            assert index.d == 768, f"{index_file.name} has wrong dimension"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_deleted_pmids_filtered_e2e(self, run_pipeline_e2e):
        """Test that deleted PMIDs are excluded from processed metadata"""
        output_dir = run_pipeline_e2e['output_dir']

        # Load deleted PMIDs
        import gzip
        deleted_file = output_dir / 'raw_data' / 'pubmed' / 'deleted.pmids.sorted.gz'

        if not deleted_file.exists():
            pytest.skip("Deleted PMIDs file not found")

        with gzip.open(deleted_file, 'rt') as f:
            deleted_pmids = {line.strip() for line in f}

        # Check processed metadata files (not master, since merge is optional)
        processed_dir = output_dir / 'data' / 'processed' / 'pubmed' / 'baseline'
        metadata_files = list(processed_dir.glob('*.json'))

        for metadata_file in metadata_files:
            with open(metadata_file) as f:
                metadata = json.load(f)

            for entry in metadata.values():
                pmid = entry.get('pmid', '')
                assert pmid not in deleted_pmids, \
                    f"Deleted PMID {pmid} found in {metadata_file.name}"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_pipeline_creates_logs(self, run_pipeline_e2e):
        """Test that pipeline creates log files"""
        output_dir = run_pipeline_e2e['output_dir']
        log_dir = output_dir / 'logs' / 'pubmed'

        assert log_dir.exists(), "Log directory not created"

        download_log = log_dir / 'download.log'
        assert download_log.exists(), "Download log not created"

        # Check log has content
        assert download_log.stat().st_size > 0, "Download log is empty"
