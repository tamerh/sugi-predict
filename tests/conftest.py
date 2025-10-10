"""
Pytest configuration and shared fixtures for BioYoda tests
"""
import pytest
import tempfile
import shutil
import json
import faiss
import numpy as np
import sys
from pathlib import Path

# Add modules to Python path so tests can import them
PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = Path(__file__).parent / 'fixtures'
sys.path.insert(0, str(PROJECT_ROOT / 'modules' / 'pubmed' / 'scripts'))
sys.path.insert(0, str(PROJECT_ROOT / 'modules' / 'clinical_trials' / 'scripts'))
sys.path.insert(0, str(PROJECT_ROOT / 'modules' / 'qdrant' / 'scripts'))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs"""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path)


@pytest.fixture
def sample_faiss_index():
    """Create a sample FAISS index with known vectors"""
    dimension = 768
    n_vectors = 100

    index = faiss.IndexFlatL2(dimension)
    vectors = np.random.random((n_vectors, dimension)).astype('float32')
    index.add(vectors)

    return index, vectors


@pytest.fixture
def sample_metadata():
    """Create sample metadata matching sample index"""
    metadata = {}
    for i in range(100):
        metadata[i] = {
            'pmid': f'PMID{10000000 + i}',
            'chunk_text': f'Title: Test Article {i}\nAbstract: This is test abstract {i}'
        }
    return metadata


@pytest.fixture
def sample_index_files(temp_dir, sample_faiss_index, sample_metadata):
    """Create multiple sample index files for merge testing"""
    index, vectors = sample_faiss_index

    # Create 3 index files
    index_files = []
    metadata_files = []

    for i in range(3):
        # Create partial index (33 vectors each)
        start_idx = i * 33
        end_idx = min((i + 1) * 33, 100)

        partial_index = faiss.IndexFlatL2(768)
        partial_vectors = vectors[start_idx:end_idx]
        partial_index.add(partial_vectors)

        # Save partial index
        index_path = temp_dir / f'part_{i}.index'
        faiss.write_index(partial_index, str(index_path))
        index_files.append(index_path)

        # Create partial metadata
        partial_metadata = {}
        for j, idx in enumerate(range(start_idx, end_idx)):
            partial_metadata[j] = sample_metadata[idx]

        # Save partial metadata
        metadata_path = temp_dir / f'part_{i}.json'
        with open(metadata_path, 'w') as f:
            json.dump(partial_metadata, f)
        metadata_files.append(metadata_path)

    return {
        'index_files': index_files,
        'metadata_files': metadata_files,
        'total_vectors': 99,  # 33 + 33 + 33
        'dimension': 768
    }


@pytest.fixture
def sample_pubmed_xml(temp_dir):
    """Create a minimal sample PubMed XML file for testing"""
    xml_content = """<?xml version="1.0"?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2019//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_190101.dtd">
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">12345678</PMID>
      <Article>
        <ArticleTitle>Test Article Title</ArticleTitle>
        <Abstract>
          <AbstractText>This is a test abstract for PubMed article processing.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">87654321</PMID>
      <Article>
        <ArticleTitle>Another Test Article</ArticleTitle>
        <Abstract>
          <AbstractText>This is another test abstract with different content.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""

    import gzip
    xml_path = temp_dir / 'test_pubmed.xml.gz'
    with gzip.open(xml_path, 'wt') as f:
        f.write(xml_content)

    return xml_path


@pytest.fixture
def sample_deleted_pmids(temp_dir):
    """Create a sample deleted PMIDs file"""
    import gzip

    deleted_pmids = ['87654321', '99999999']  # One matches our sample XML

    pmids_path = temp_dir / 'deleted.pmids.gz'
    with gzip.open(pmids_path, 'wt') as f:
        for pmid in deleted_pmids:
            f.write(f"{pmid}\n")

    return pmids_path


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    return {
        'base_dir': '/tmp/test_bioyoda',
        'pubmed': {
            'model_name': 'sentence-transformers/all-MiniLM-L6-v2',
            'vector_dimension': 384,
            'batch_size': 32,
            'process_memory_mb': 4096
        },
        'clinical_trials': {
            'model_name': 'sentence-transformers/all-MiniLM-L6-v2',
            'vector_dimension': 384,
            'test_mode': True,
            'test_trials_limit': 10
        }
    }


@pytest.fixture
def real_clinical_trials():
    """Load real clinical trials data from fixtures"""
    fixtures_path = FIXTURES_DIR / 'clinical_trials' / 'sample_trials.json'

    if not fixtures_path.exists():
        pytest.skip(f"Real clinical trials fixture not found: {fixtures_path}")

    with open(fixtures_path) as f:
        trials = json.load(f)

    return trials


@pytest.fixture
def real_trial_sample(real_clinical_trials):
    """Get a single real clinical trial for testing"""
    return real_clinical_trials[0]
