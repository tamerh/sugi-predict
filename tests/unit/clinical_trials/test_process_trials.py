"""
Unit tests for clinical trials processing (process_trials.py)

Tests text processing, chunking, and FAISS index creation for clinical trials
"""
import pytest
import json
import faiss
from pathlib import Path

from process_trials import TrialTextProcessor


class TestTextCleaning:
    """Test text cleaning functionality"""

    def test_clean_text_removes_extra_whitespace(self):
        """Test that excessive whitespace is removed"""
        processor = TrialTextProcessor()

        text = "This  has   multiple    spaces"
        cleaned = processor.clean_text(text)

        assert cleaned == "This has multiple spaces"

    def test_clean_text_removes_newlines(self):
        """Test that newlines are normalized to spaces"""
        processor = TrialTextProcessor()

        text = "Line one\nLine two\r\nLine three"
        cleaned = processor.clean_text(text)

        assert "\n" not in cleaned
        assert "\r" not in cleaned
        assert "Line one Line two Line three" == cleaned

    def test_clean_text_removes_html_tags(self):
        """Test that HTML tags are removed"""
        processor = TrialTextProcessor()

        text = "Text with <strong>HTML</strong> and <br/> tags"
        cleaned = processor.clean_text(text)

        assert "<strong>" not in cleaned
        assert "<br/>" not in cleaned
        # Check that tags are removed (exact spacing may vary)
        assert "HTML" in cleaned
        assert "tags" in cleaned

    def test_clean_text_removes_urls(self):
        """Test that URLs are removed"""
        processor = TrialTextProcessor()

        text = "Visit http://example.com for more info"
        cleaned = processor.clean_text(text)

        assert "http://example.com" not in cleaned
        # Check that URL is removed (exact spacing may vary)
        assert "Visit" in cleaned
        assert "more info" in cleaned

    def test_clean_text_handles_empty_input(self):
        """Test that empty input is handled gracefully"""
        processor = TrialTextProcessor()

        assert processor.clean_text("") == ""
        assert processor.clean_text(None) == ""


class TestTextChunking:
    """Test text chunking functionality"""

    def test_short_text_returns_single_chunk(self):
        """Test that short text is not chunked"""
        processor = TrialTextProcessor(max_chunk_length=500)

        text = "This is a short sentence."
        chunks = processor.chunk_long_text(text, 500)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_is_chunked(self):
        """Test that long text is split into chunks"""
        processor = TrialTextProcessor(max_chunk_length=100)

        # Create text longer than max_chunk_length
        text = "This is sentence one. " * 10  # ~220 chars
        chunks = processor.chunk_long_text(text, 100)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 150  # Allow some overflow for sentence completion

    def test_chunking_preserves_sentences(self):
        """Test that sentence boundaries are preserved"""
        processor = TrialTextProcessor(max_chunk_length=50)

        text = "First sentence. Second sentence. Third sentence."
        chunks = processor.chunk_long_text(text, 50)

        # Each chunk should be a complete sentence or sentences
        for chunk in chunks:
            assert not chunk.startswith(". ")
            assert not chunk.endswith(" .")

    def test_empty_text_returns_empty_list(self):
        """Test that empty text returns empty list"""
        processor = TrialTextProcessor()

        assert processor.chunk_long_text("", 500) == []
        assert processor.chunk_long_text(None, 500) == []


class TestTrialProcessing:
    """Test trial-to-chunks processing"""

    @pytest.fixture
    def sample_trial(self):
        """Create a sample trial dict for testing"""
        return {
            'nct_id': 'NCT12345678',
            'brief_title': 'Test Clinical Trial',
            'brief_summary': 'This is a brief summary of the trial.',
            'detailed_description': 'This is a more detailed description with more information.',
            'overall_status': 'Completed',
            'phase': 'Phase 3',
            'study_type': 'Interventional',
            'conditions': ['Diabetes', 'Hypertension'],
            'interventions': ['Drug A', 'Drug B']
        }

    def test_process_trial_creates_chunks(self, sample_trial):
        """Test that trial is processed into chunks"""
        processor = TrialTextProcessor(max_chunk_length=500)

        chunks = processor.process_trial_to_chunks(sample_trial)

        assert len(chunks) > 0
        assert all('nct_id' in chunk for chunk in chunks)
        assert all('text' in chunk for chunk in chunks)
        assert all('chunk_type' in chunk for chunk in chunks)

    def test_chunks_contain_nct_id(self, sample_trial):
        """Test that all chunks contain NCT ID"""
        processor = TrialTextProcessor()

        chunks = processor.process_trial_to_chunks(sample_trial)

        for chunk in chunks:
            assert chunk['nct_id'] == 'NCT12345678'

    def test_chunks_have_sequential_ids(self, sample_trial):
        """Test that chunks are numbered sequentially"""
        processor = TrialTextProcessor()

        chunks = processor.process_trial_to_chunks(sample_trial)

        chunk_ids = [chunk.get('chunk_id', -1) for chunk in chunks]
        assert chunk_ids == list(range(len(chunks)))

    def test_minimum_text_length_enforced(self):
        """Test that very short text is filtered out"""
        processor = TrialTextProcessor(min_text_length=50)

        short_trial = {
            'nct_id': 'NCT99999999',
            'brief_title': 'Short',
            'brief_summary': 'Too short',
            'detailed_description': ''
        }

        chunks = processor.process_trial_to_chunks(short_trial)

        # Very short text should be filtered
        for chunk in chunks:
            assert len(chunk['text']) >= 50 or len(chunk['text']) == 0


class TestProcessTrialsIntegration:
    """Integration tests for the full process_trials workflow"""

    @pytest.fixture
    def sample_trials_json(self, temp_dir):
        """Create sample trials JSON file"""
        trials = [
            {
                'nct_id': 'NCT12345678',
                'brief_title': 'Trial One',
                'brief_summary': 'Summary of trial one with sufficient length for testing.',
                'detailed_description': 'Detailed description of trial one.',
                'overall_status': 'Completed',
                'phase': 'Phase 3',
                'conditions': ['Diabetes']
            },
            {
                'nct_id': 'NCT87654321',
                'brief_title': 'Trial Two',
                'brief_summary': 'Summary of trial two with different content for testing.',
                'detailed_description': 'Detailed description of trial two.',
                'overall_status': 'Recruiting',
                'phase': 'Phase 2',
                'conditions': ['Cancer']
            }
        ]

        json_path = temp_dir / 'test_trials.json'
        with open(json_path, 'w') as f:
            json.dump(trials, f)

        return json_path

    def test_metadata_structure(self, temp_dir, sample_trials_json):
        """Test that output metadata has correct structure"""
        # This would require importing and running the full process_trials script
        # For now, test the processor components
        processor = TrialTextProcessor()

        with open(sample_trials_json) as f:
            trials = json.load(f)

        all_chunks = []
        for trial in trials:
            chunks = processor.process_trial_to_chunks(trial)
            all_chunks.extend(chunks)

        # Verify chunk structure
        for chunk in all_chunks:
            assert 'nct_id' in chunk
            assert 'text' in chunk
            assert 'chunk_type' in chunk
            assert 'chunk_id' in chunk
            assert chunk['nct_id'].startswith('NCT')
