"""
End-to-end test for Clinical Trials pipeline

This test actually RUNS the full pipeline in test mode and validates output.
Uses test_out/ directory for all outputs (easy to inspect and debug).

With test config (100 trials limit): Should take ~5-10 minutes.

Usage:
    ./run_tests.sh clinical_trials  (includes E2E)
    pytest tests/integration/test_clinical_trials_e2e.py -m e2e -v
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
        'run', 'clinical_trials',
        '--config', str(test_config_path),
        '--local',
        '--cores', '2'
    ]

    print(f"\n{'='*80}")
    print(f"Running E2E Pipeline: {' '.join(cmd)}")
    print(f"Output directory: {output_dir}")
    print(f"Config: test_mode={config['clinical_trials'].get('test_mode')}, "
          f"test_trials_limit={config['clinical_trials'].get('test_trials_limit')}")
    print(f"{'='*80}\n")

    result = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=1800  # 30 minute timeout (should be enough for 100 trials)
    )

    return {
        'returncode': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'config': config,
        'output_dir': output_dir,
        'project_root': project_root
    }


class TestClinicalTrialsEndToEnd:
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
    def test_downloads_data(self, run_pipeline_e2e):
        """Test that clinical trials data was downloaded"""
        output_dir = run_pipeline_e2e['output_dir']

        raw_dir = output_dir / 'raw_data' / 'clinical_trials'
        assert raw_dir.exists(), "Raw data directory not created"

        # Check for extracted data directory (AACT extracts to CSV files)
        extracted_dir = raw_dir / 'extracted'
        assert extracted_dir.exists(), "Extracted data directory not created"

        # Check for extraction_info.json
        extraction_info = extracted_dir / 'extraction_info.json'
        assert extraction_info.exists(), "Extraction info not found"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_processes_with_limit(self, run_pipeline_e2e):
        """Test that test mode processes limited trials"""
        output_dir = run_pipeline_e2e['output_dir']
        config = run_pipeline_e2e['config']

        final_dir = output_dir / 'data' / 'final' / 'clinical_trials'
        assert final_dir.exists(), "Final directory not created"

        index_file = final_dir / 'clinical_trials.index'
        assert index_file.exists(), "Index file not created"

        # Check vector counts
        if config['clinical_trials'].get('test_mode'):
            limit = config['clinical_trials'].get('test_trials_limit', 100)

            index = faiss.read_index(str(index_file))
            # Each trial can have multiple chunks, so allow some variance
            # With 100 trials and ~3-5 chunks per trial, expect ~300-500 vectors
            assert index.ntotal > 0, "Index is empty"
            assert index.ntotal <= limit * 10, \
                f"Index has {index.ntotal} vectors, expected <={limit * 10} for {limit} trials"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_final_index_valid(self, run_pipeline_e2e):
        """Test that final index is a valid FAISS index"""
        output_dir = run_pipeline_e2e['output_dir']
        final_dir = output_dir / 'data' / 'final' / 'clinical_trials'

        index_file = final_dir / 'clinical_trials.index'
        assert index_file.exists(), "Index file not found"

        # Validate index
        index = faiss.read_index(str(index_file))
        assert index.ntotal > 0, "Index is empty"
        assert index.d == 768, f"Index has wrong dimension: {index.d}"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_metadata_created(self, run_pipeline_e2e):
        """Test that metadata file is created with correct structure"""
        output_dir = run_pipeline_e2e['output_dir']
        final_dir = output_dir / 'data' / 'final' / 'clinical_trials'

        metadata_file = final_dir / 'clinical_trials.json'
        assert metadata_file.exists(), "Metadata file not created"

        # Load and validate metadata
        with open(metadata_file) as f:
            metadata = json.load(f)

        assert len(metadata) > 0, "Metadata is empty"

        # Check structure of first entry
        first_entry = next(iter(metadata.values()))
        assert 'nct_id' in first_entry, "Missing nct_id in metadata"
        assert 'text' in first_entry, "Missing text in metadata"
        assert 'chunk_type' in first_entry, "Missing chunk_type in metadata"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_pipeline_creates_logs(self, run_pipeline_e2e):
        """Test that pipeline creates log files"""
        output_dir = run_pipeline_e2e['output_dir']
        log_dir = output_dir / 'logs' / 'clinical_trials'

        assert log_dir.exists(), "Log directory not created"

        download_log = log_dir / 'download.log'
        assert download_log.exists(), "Download log not created"

        # Check log has content
        assert download_log.stat().st_size > 0, "Download log is empty"

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_trial_metadata_structure(self, run_pipeline_e2e):
        """Test that trials have correct metadata fields"""
        output_dir = run_pipeline_e2e['output_dir']
        final_dir = output_dir / 'data' / 'final' / 'clinical_trials'

        metadata_file = final_dir / 'clinical_trials.json'

        with open(metadata_file) as f:
            metadata = json.load(f)

        # Check all entries have required fields
        for entry in metadata.values():
            assert entry['nct_id'].startswith('NCT'), \
                f"Invalid NCT ID: {entry.get('nct_id')}"
            assert len(entry['text']) > 0, "Empty text in metadata"
            # Valid chunk types from clinical trials processing
            valid_chunk_types = ['title', 'summary', 'description', 'eligibility', 'interventions', 'outcomes']
            assert entry['chunk_type'] in valid_chunk_types, \
                f"Invalid chunk_type: {entry.get('chunk_type')}"
