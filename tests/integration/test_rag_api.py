"""
Integration tests for RAG API endpoint

Tests the /ask endpoint with mocked LLM responses to avoid API costs.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os
from pathlib import Path

# Add project root to path to enable proper package imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import as a package
from modules.api.scripts.main import app


@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(app)


@pytest.fixture
def mock_rag_engine():
    """Mock RAG engine response"""
    return {
        "question": "What is CRISPR gene editing?",
        "answer": (
            "CRISPR-Cas9 is a revolutionary gene editing technology that allows precise "
            "modifications to DNA. According to PMID:12345678, it consists of two key components: "
            "the Cas9 enzyme that cuts DNA, and a guide RNA that directs Cas9 to the correct "
            "location in the genome.\n\nSources:\n- PMID:12345678"
        ),
        "sources": [
            {
                "id": "PMID:12345678",
                "score": 0.92,
                "collection": "pubmed_abstracts",
                "title": "CRISPR-Cas9 gene editing in human cells",
                "text_preview": "CRISPR-Cas9 is a revolutionary gene editing technology...",
                "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"
            }
        ],
        "metrics": {
            "search_time_ms": 234.56,
            "llm_time_ms": 1567.89,
            "total_time_ms": 1802.45,
            "num_sources": 1,
            "model_used": "claude-3-5-sonnet-20241022",
            "estimated_cost_usd": 0.0142
        },
        "validation": {
            "citation_coverage": 1.0,
            "cited_count": 1,
            "valid_citations": ["PMID:12345678"],
            "invalid_citations": [],
            "warning": None
        }
    }


class TestRAGEndpoint:
    """Test /ask endpoint functionality"""

    @patch('modules.api.scripts.main.rag_engine')
    def test_ask_basic_question(self, mock_engine, client, mock_rag_engine):
        """Test basic question-answering"""
        # Setup mock - must be async
        mock_engine.ask = AsyncMock(return_value=mock_rag_engine)

        response = client.post("/ask", json={
            "question": "What is CRISPR gene editing?",
            "top_k": 5
        })

        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "answer" in data
        assert "sources" in data
        assert "metrics" in data
        assert "validation" in data

        # Check answer contains citation
        assert "PMID:" in data["answer"]

        # Check sources
        assert len(data["sources"]) > 0
        assert data["sources"][0]["id"] == "PMID:12345678"

    @patch('modules.api.scripts.main.rag_engine')
    def test_ask_with_custom_params(self, mock_engine, client, mock_rag_engine):
        """Test with custom parameters"""
        mock_engine.ask = AsyncMock(return_value=mock_rag_engine)

        response = client.post("/ask", json={
            "question": "How does metformin work?",
            "collections": ["pubmed_abstracts"],
            "top_k": 10,
            "temperature": 0.2,
            "max_tokens": 1500
        })

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data

    @patch('modules.api.scripts.main.rag_engine')
    def test_ask_citation_validation(self, mock_engine, client, mock_rag_engine):
        """Test citation validation is present"""
        mock_engine.ask = AsyncMock(return_value=mock_rag_engine)

        response = client.post("/ask", json={
            "question": "What is gene therapy?"
        })

        data = response.json()

        # Check validation metrics
        assert "validation" in data
        assert "citation_coverage" in data["validation"]
        assert "valid_citations" in data["validation"]
        assert data["validation"]["citation_coverage"] >= 0.0

    def test_ask_invalid_question(self, client):
        """Test with invalid question (too short)"""
        response = client.post("/ask", json={
            "question": "a"  # Too short
        })

        assert response.status_code == 422  # Validation error

    def test_ask_empty_question(self, client):
        """Test with empty question"""
        response = client.post("/ask", json={
            "question": "   "  # Only whitespace
        })

        assert response.status_code == 422  # Validation error

    @patch('modules.api.scripts.main.rag_engine')
    def test_ask_performance_metrics(self, mock_engine, client, mock_rag_engine):
        """Test that performance metrics are returned"""
        mock_engine.ask = AsyncMock(return_value=mock_rag_engine)

        response = client.post("/ask", json={
            "question": "What is immunotherapy?"
        })

        data = response.json()
        metrics = data["metrics"]

        assert "search_time_ms" in metrics
        assert "llm_time_ms" in metrics
        assert "total_time_ms" in metrics
        assert "estimated_cost_usd" in metrics
        assert metrics["total_time_ms"] >= 0
        assert metrics["estimated_cost_usd"] >= 0

    @patch('modules.api.scripts.main.rag_engine')
    def test_ask_sources_format(self, mock_engine, client, mock_rag_engine):
        """Test that sources are properly formatted"""
        mock_engine.ask = AsyncMock(return_value=mock_rag_engine)

        response = client.post("/ask", json={
            "question": "What are clinical trials for cancer?"
        })

        data = response.json()
        sources = data["sources"]

        assert len(sources) > 0

        # Check source structure
        source = sources[0]
        assert "id" in source
        assert "score" in source
        assert "title" in source
        assert "collection" in source

        # Check PMID format
        if source["id"].startswith("PMID:"):
            assert "url" in source
            assert "pubmed.ncbi.nlm.nih.gov" in source["url"]

    @patch('modules.api.scripts.main.rag_engine', None)
    def test_ask_rag_not_enabled(self, client):
        """Test when RAG engine is not initialized"""
        response = client.post("/ask", json={
            "question": "What is CRISPR?"
        })

        assert response.status_code == 503  # Service unavailable
        assert "not initialized" in response.json()["message"].lower()


class TestRAGEdgeCases:
    """Test edge cases and error handling"""

    @patch('modules.api.scripts.main.rag_engine')
    def test_ask_no_search_results(self, mock_engine, client):
        """Test when no search results are found"""
        # Mock response with no results
        no_results_response = {
            "question": "asdfqwerzxcv",
            "answer": (
                "I apologize, but I couldn't find relevant information in the database "
                "to answer your question."
            ),
            "sources": [],
            "metrics": {
                "search_time_ms": 100.0,
                "llm_time_ms": 0.0,
                "total_time_ms": 100.0,
                "num_sources": 0,
                "model_used": "claude-3-5-sonnet-20241022",
                "estimated_cost_usd": 0.0
            },
            "validation": {
                "citation_coverage": 0.0,
                "cited_count": 0,
                "valid_citations": [],
                "invalid_citations": [],
                "warning": "No search results found"
            }
        }

        mock_engine.ask = AsyncMock(return_value=no_results_response)

        response = client.post("/ask", json={
            "question": "asdfqwerzxcv"  # Nonsense query
        })

        data = response.json()
        assert response.status_code == 200
        assert "couldn't find" in data["answer"].lower() or "no" in data["answer"].lower()
        assert len(data["sources"]) == 0

    @patch('modules.api.scripts.main.rag_engine')
    def test_ask_hallucinated_citations(self, mock_engine, client):
        """Test detection of hallucinated citations"""
        # Mock response with invalid citation
        hallucination_response = {
            "question": "What is CRISPR?",
            "answer": "CRISPR is a gene editing tool. According to PMID:99999999...",
            "sources": [
                {
                    "id": "PMID:12345678",
                    "score": 0.9,
                    "collection": "pubmed_abstracts",
                    "title": "CRISPR technology",
                    "text_preview": "...",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"
                }
            ],
            "metrics": {
                "search_time_ms": 200.0,
                "llm_time_ms": 1500.0,
                "total_time_ms": 1700.0,
                "num_sources": 1,
                "model_used": "claude-3-5-sonnet-20241022",
                "estimated_cost_usd": 0.015
            },
            "validation": {
                "citation_coverage": 0.0,
                "cited_count": 1,
                "valid_citations": [],
                "invalid_citations": ["PMID:99999999"],
                "warning": "⚠️  Hallucinated citations detected: PMID:99999999"
            }
        }

        mock_engine.ask = AsyncMock(return_value=hallucination_response)

        response = client.post("/ask", json={
            "question": "What is CRISPR?"
        })

        data = response.json()
        validation = data["validation"]

        # Should flag hallucination
        assert len(validation["invalid_citations"]) > 0
        assert validation["warning"] is not None


class TestRAGParameters:
    """Test different parameter combinations"""

    @patch('modules.api.scripts.main.rag_engine')
    def test_temperature_control(self, mock_engine, client, mock_rag_engine):
        """Test temperature parameter"""
        mock_engine.ask = AsyncMock(return_value=mock_rag_engine)

        # Low temperature (factual)
        response_low = client.post("/ask", json={
            "question": "What is CRISPR?",
            "temperature": 0.0
        })
        assert response_low.status_code == 200

        # Higher temperature (more creative)
        response_high = client.post("/ask", json={
            "question": "What is CRISPR?",
            "temperature": 0.5
        })
        assert response_high.status_code == 200

    @patch('modules.api.scripts.main.rag_engine')
    def test_top_k_limits(self, mock_engine, client, mock_rag_engine):
        """Test top_k parameter limits"""
        mock_engine.ask = AsyncMock(return_value=mock_rag_engine)

        # Valid top_k
        response = client.post("/ask", json={
            "question": "What is gene editing?",
            "top_k": 10
        })
        assert response.status_code == 200

        # Too high (should be rejected by validation)
        response = client.post("/ask", json={
            "question": "What is gene editing?",
            "top_k": 100
        })
        assert response.status_code == 422  # Validation error

    @patch('modules.api.scripts.main.rag_engine')
    def test_multi_collection_search(self, mock_engine, client, mock_rag_engine):
        """Test searching multiple collections"""
        mock_engine.ask = AsyncMock(return_value=mock_rag_engine)

        response = client.post("/ask", json={
            "question": "Are there clinical trials for CRISPR?",
            "collections": ["pubmed_abstracts", "clinical_trials"]
        })

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
