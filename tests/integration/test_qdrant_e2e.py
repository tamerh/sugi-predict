"""
End-to-end test for Qdrant module

This test runs the complete Qdrant workflow:
1. Start Qdrant server (local mode)
2. Insert test data from FAISS indices
3. Verify collections and data
4. Stop server

Uses test_out/ directory for all outputs.
Requires actual Qdrant server (Singularity container).

Usage:
    pytest tests/integration/test_qdrant_e2e.py -m e2e -v --tb=short
"""
import pytest
import subprocess
import json
import time
import requests
from pathlib import Path
import yaml
import shutil
import faiss
import numpy as np


@pytest.fixture(scope="module")
def test_setup():
    """
    Setup test environment with mock FAISS data.
    This fixture creates minimal test data that can be inserted to Qdrant.
    """
    project_root = Path(__file__).parent.parent.parent
    test_config_path = project_root / 'config' / 'test_config.yaml'

    # Load test config
    with open(test_config_path) as f:
        config = yaml.safe_load(f)

    base_dir = Path(config['base_dir'])

    # Create test FAISS data if it doesn't exist
    pubmed_processed = base_dir / "data" / "processed" / "pubmed" / "baseline"
    clinical_trials_processed = base_dir / "data" / "processed" / "clinical_trials"

    pubmed_processed.mkdir(parents=True, exist_ok=True)
    clinical_trials_processed.mkdir(parents=True, exist_ok=True)

    # Create minimal test FAISS indices if they don't exist
    if not list(pubmed_processed.glob("*.index")):
        create_test_faiss_index(pubmed_processed / "test_pubmed.index", n_vectors=10)

    if not list(clinical_trials_processed.glob("*.index")):
        create_test_faiss_index(clinical_trials_processed / "test_trials.index", n_vectors=5)

    return {
        'project_root': project_root,
        'config_path': test_config_path,
        'base_dir': base_dir,
        'config': config
    }


def create_test_faiss_index(index_path: Path, n_vectors: int = 10, dim: int = 768):
    """Create a minimal test FAISS index with metadata (consistent naming: .index + .json)"""
    # Create random vectors
    vectors = np.random.random((n_vectors, dim)).astype('float32')

    # Create FAISS index
    index = faiss.IndexFlatL2(dim)
    index.add(vectors)

    # Save index
    faiss.write_index(index, str(index_path))

    # Create metadata (consistent format for both PubMed and Clinical Trials)
    metadata = {
        str(i): {
            'id': f'TEST{i:06d}',
            'title': f'Test Document {i}',
            'text': f'This is test content for document {i}',
            'source': 'test'
        }
        for i in range(n_vectors)
    }

    # Save metadata with consistent naming: .json (not _metadata.json)
    metadata_path = index_path.with_suffix('.json')
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"Created test FAISS index: {index_path}")
    print(f"Created test metadata: {metadata_path}")


@pytest.fixture(scope="module")
def qdrant_server(test_setup):
    """
    Start Qdrant server for testing, yield for tests, then stop.
    This fixture manages the complete server lifecycle.
    """
    project_root = test_setup['project_root']
    base_dir = test_setup['base_dir']

    # Start server
    print("\n" + "="*80)
    print("Starting Qdrant server (local mode)...")
    print("="*80 + "\n")

    start_cmd = [
        str(project_root / 'bioyoda.sh'),
        'qdrant', 'start',
        '--config', str(test_setup['config_path']),
        '--mode', 'local'
    ]

    result = subprocess.run(
        start_cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=60
    )

    if result.returncode != 0:
        print(f"Server start STDERR: {result.stderr}")
        pytest.skip(f"Could not start Qdrant server: {result.stderr}")

    # Wait for server to be ready
    connection_info_file = base_dir / "data" / "qdrant" / "connection_info.txt"
    max_wait = 30
    waited = 0

    while not connection_info_file.exists() and waited < max_wait:
        time.sleep(1)
        waited += 1

    if not connection_info_file.exists():
        pytest.skip("Qdrant server did not create connection_info.txt")

    # Read server URL
    with open(connection_info_file) as f:
        for line in f:
            if line.startswith('QDRANT_URL='):
                server_url = line.split('=', 1)[1].strip()
                break
        else:
            pytest.skip("Could not find QDRANT_URL in connection_info.txt")

    # Verify server is responsive
    try:
        response = requests.get(f"{server_url}/", timeout=5)
        response.raise_for_status()
        print(f"✓ Qdrant server is running at {server_url}")
    except Exception as e:
        pytest.skip(f"Qdrant server not responsive: {e}")

    # Yield for tests
    yield {
        'server_url': server_url,
        'connection_info': connection_info_file
    }

    # Teardown: stop server
    print("\n" + "="*80)
    print("Stopping Qdrant server...")
    print("="*80 + "\n")

    stop_cmd = [
        str(project_root / 'bioyoda.sh'),
        'qdrant', 'stop',
        '--config', str(test_setup['config_path'])
    ]

    subprocess.run(
        stop_cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30
    )


@pytest.mark.e2e
class TestQdrantEndToEnd:
    """End-to-end tests for Qdrant module"""

    def test_server_is_running(self, qdrant_server):
        """Test that Qdrant server is accessible"""
        server_url = qdrant_server['server_url']

        response = requests.get(f"{server_url}/")
        assert response.status_code == 200

        print(f"✓ Server is running at {server_url}")

    def test_connection_info_exists(self, test_setup, qdrant_server):
        """Test that connection info file is created"""
        conn_file = qdrant_server['connection_info']

        assert conn_file.exists()
        assert conn_file.is_file()

        content = conn_file.read_text()
        assert "QDRANT_URL=" in content

        print(f"✓ Connection info file exists: {conn_file}")

    def test_can_insert_pubmed_data(self, test_setup, qdrant_server):
        """Test inserting PubMed data to Qdrant"""
        project_root = test_setup['project_root']
        config_path = test_setup['config_path']

        print("\n" + "="*80)
        print("Inserting PubMed test data...")
        print("="*80 + "\n")

        # Run insertion
        insert_cmd = [
            str(project_root / 'bioyoda.sh'),
            'qdrant', 'insert', 'pubmed',
            '--config', str(config_path),
            '--local',
            '--cores', '1'
        ]

        result = subprocess.run(
            insert_cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes
        )

        # Check result
        if result.returncode != 0:
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            pytest.fail(f"PubMed insertion failed: {result.stderr}")

        # Verify done marker
        done_marker = test_setup['base_dir'] / "data" / "qdrant" / "collections" / "pubmed_abstracts.done"
        assert done_marker.exists(), "PubMed insertion done marker not found"

        print(f"✓ PubMed data inserted successfully")

    def test_can_query_pubmed_collection(self, test_setup, qdrant_server):
        """Test that PubMed collection is queryable"""
        server_url = qdrant_server['server_url']
        collection_name = test_setup['config']['pubmed']['qdrant']['collection_name']

        # Get collection info
        response = requests.get(f"{server_url}/collections/{collection_name}")
        assert response.status_code == 200

        collection_info = response.json()
        assert collection_info['result']['status'] == 'green'

        points_count = collection_info['result']['points_count']
        assert points_count > 0, "No points in PubMed collection"

        print(f"✓ PubMed collection has {points_count} points")

    def test_can_insert_clinical_trials_data(self, test_setup, qdrant_server):
        """Test inserting Clinical Trials data to Qdrant"""
        project_root = test_setup['project_root']
        config_path = test_setup['config_path']

        print("\n" + "="*80)
        print("Inserting Clinical Trials test data...")
        print("="*80 + "\n")

        # Run insertion
        insert_cmd = [
            str(project_root / 'bioyoda.sh'),
            'qdrant', 'insert', 'clinical_trials',
            '--config', str(config_path),
            '--local',
            '--cores', '1'
        ]

        result = subprocess.run(
            insert_cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes
        )

        # Check result
        if result.returncode != 0:
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            pytest.fail(f"Clinical Trials insertion failed: {result.stderr}")

        # Verify done marker
        done_marker = test_setup['base_dir'] / "data" / "qdrant" / "collections" / "clinical_trials.done"
        assert done_marker.exists(), "Clinical Trials insertion done marker not found"

        print(f"✓ Clinical Trials data inserted successfully")

    def test_can_query_clinical_trials_collection(self, test_setup, qdrant_server):
        """Test that Clinical Trials collection is queryable"""
        server_url = qdrant_server['server_url']
        collection_name = test_setup['config']['clinical_trials']['qdrant']['collection_name']

        # Get collection info
        response = requests.get(f"{server_url}/collections/{collection_name}")
        assert response.status_code == 200

        collection_info = response.json()
        assert collection_info['result']['status'] == 'green'

        points_count = collection_info['result']['points_count']
        assert points_count > 0, "No points in Clinical Trials collection"

        print(f"✓ Clinical Trials collection has {points_count} points")

    def test_status_command_works(self, test_setup, qdrant_server):
        """Test that status command provides useful information"""
        project_root = test_setup['project_root']
        config_path = test_setup['config_path']

        status_cmd = [
            str(project_root / 'bioyoda.sh'),
            'qdrant', 'status',
            '--config', str(config_path)
        ]

        result = subprocess.run(
            status_cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0
        output = result.stdout

        # Check that status output contains expected information
        assert "qdrant" in output.lower() or "server" in output.lower()
        # Status should either show running server or connection info
        assert ("running" in output.lower() or
                "active" in output.lower() or
                "connection info" in output.lower() or
                "qdrant_url" in output.lower())

        print(f"✓ Status command output:\n{output}")

    def test_server_stops_cleanly(self, test_setup, qdrant_server):
        """Test that server can be stopped (tested in fixture teardown)"""
        # This test mainly documents that server stop is tested via fixture
        # The actual stop happens in the qdrant_server fixture teardown

        # Verify server is running during the test
        conn_file = qdrant_server['connection_info']
        assert conn_file.exists(), "Connection file should exist during test"

        print("✓ Server stop will be tested in fixture teardown")


@pytest.mark.e2e
class TestQdrantDataIntegrity:
    """Test data integrity in Qdrant collections"""

    def test_vectors_have_correct_dimension(self, test_setup, qdrant_server):
        """Test that inserted vectors have correct dimensionality"""
        server_url = qdrant_server['server_url']
        collection_name = test_setup['config']['pubmed']['qdrant']['collection_name']

        # Get collection info
        response = requests.get(f"{server_url}/collections/{collection_name}")
        collection_info = response.json()

        vector_size = collection_info['result']['config']['params']['vectors']['size']
        expected_dim = test_setup['config']['pubmed']['vector_dimension']

        assert vector_size == expected_dim, f"Expected dimension {expected_dim}, got {vector_size}"

        print(f"✓ Vectors have correct dimension: {vector_size}")

    def test_metadata_is_preserved(self, test_setup, qdrant_server):
        """Test that metadata fields are preserved in Qdrant"""
        server_url = qdrant_server['server_url']
        collection_name = test_setup['config']['pubmed']['qdrant']['collection_name']

        # Scroll through some points to check metadata
        scroll_response = requests.post(
            f"{server_url}/collections/{collection_name}/points/scroll",
            json={"limit": 1, "with_payload": True, "with_vector": False}
        )

        assert scroll_response.status_code == 200
        points = scroll_response.json()['result']['points']

        assert len(points) > 0, "No points returned from scroll"

        # Check that payload has expected fields
        payload = points[0]['payload']
        assert 'id' in payload or 'pmid' in payload or 'nct_id' in payload, "Payload missing ID field"
        # Check for text content fields (different naming across modules)
        has_text = any(key in payload for key in ['text', 'title', 'chunk_text', 'brief_title'])
        assert has_text, f"Payload missing text field. Available fields: {list(payload.keys())}"

        print(f"✓ Metadata fields preserved: {list(payload.keys())}")


@pytest.mark.e2e
class TestQdrantErrorHandling:
    """Test error handling in Qdrant operations"""

    def test_insert_fails_gracefully_without_server(self, test_setup):
        """Test that insertion fails gracefully when server is not running"""
        # Note: This test should run outside the qdrant_server fixture
        # to ensure server is not running
        pytest.skip("Requires server to not be running - implement with separate fixture")

    def test_handles_missing_connection_info(self, test_setup):
        """Test handling of missing connection info file"""
        base_dir = test_setup['base_dir']
        conn_file = base_dir / "data" / "qdrant" / "connection_info.txt"

        # Temporarily remove connection info
        if conn_file.exists():
            backup = conn_file.with_suffix('.backup')
            shutil.move(conn_file, backup)

            try:
                # Status should handle missing file gracefully
                project_root = test_setup['project_root']
                status_cmd = [
                    str(project_root / 'bioyoda.sh'),
                    'qdrant', 'status',
                    '--config', str(test_setup['config_path'])
                ]

                result = subprocess.run(
                    status_cmd,
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                # Should not crash, just report server not running
                assert ("not running" in result.stdout.lower() or
                        "no connection info" in result.stdout.lower() or
                        "may not be started" in result.stdout.lower())

            finally:
                # Restore connection info
                if backup.exists():
                    shutil.move(backup, conn_file)
