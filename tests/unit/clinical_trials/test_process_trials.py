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

    def test_process_trial_creates_chunks(self, real_trial_sample):
        """Test that trial is processed into chunks"""
        processor = TrialTextProcessor(max_chunk_length=500)

        chunks = processor.process_trial_to_chunks(real_trial_sample)

        assert len(chunks) > 0
        assert all('nct_id' in chunk for chunk in chunks)
        assert all('text' in chunk for chunk in chunks)
        assert all('chunk_type' in chunk for chunk in chunks)

    def test_chunks_contain_nct_id(self, real_trial_sample):
        """Test that all chunks contain NCT ID"""
        processor = TrialTextProcessor()

        chunks = processor.process_trial_to_chunks(real_trial_sample)

        for chunk in chunks:
            assert chunk['nct_id'] == real_trial_sample['nct_id']

    def test_chunks_have_per_type_ids(self, real_trial_sample):
        """Test that chunk_ids are sequential within each chunk_type"""
        processor = TrialTextProcessor()

        chunks = processor.process_trial_to_chunks(real_trial_sample)

        # Group chunks by type
        from collections import defaultdict
        chunks_by_type = defaultdict(list)
        for chunk in chunks:
            chunks_by_type[chunk['chunk_type']].append(chunk.get('chunk_id', -1))

        # Verify chunk_ids are sequential within each type
        for chunk_type, ids in chunks_by_type.items():
            assert ids == list(range(len(ids))), \
                f"Chunk IDs for type '{chunk_type}' should be sequential: expected {list(range(len(ids)))}, got {ids}"

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
    def sample_trials_json(self, temp_dir, real_clinical_trials):
        """Create sample trials JSON file using real clinical trials data"""
        # Use first 2 real trials for testing
        trials = real_clinical_trials[:2]

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
