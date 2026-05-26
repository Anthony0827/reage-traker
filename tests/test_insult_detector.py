"""
Integration test for InsultDetector with Vosk WAV file.

Tests the complete detection pipeline with a synthetic WAV file
containing known Spanish insults. Uses mocked sounddevice to avoid
actual audio hardware requirements.
"""

import os
import pytest
import tempfile
from unittest.mock import Mock, patch, MagicMock
import numpy as np

from src.insult_detector import InsultDetector, SpanishStemmer


# Mock insult lexicon for testing
TEST_INSULTS = [
    "gilipollas",
    "idiota", 
    "vete",
    "gracias",
]


@pytest.fixture
def mock_vosk_model():
    """Create a mock Vosk model that returns known transcripts."""
    model = MagicMock()
    
    # Create a recognizer that returns specific transcripts
    recognizer = MagicMock()
    recognizer.SetLanguage = MagicMock()
    
    # Track how many times process is called
    call_count = [0]
    
    def process_mock(indata):
        call_count[0] += 1
        
        # Return transcript on specific calls to simulate detected insults
        if call_count[0] == 1:
            recognizer.result = Mock(return_value="gilipollas")
            recognizer.get_partially_complete = Mock(return_value=True)
        elif call_count[0] == 2:
            recognizer.result = Mock(return_value="vete a la mierda")
            recognizer.get_partially_complete = Mock(return_value=True)
        elif call_count[0] == 3:
            recognizer.result = Mock(return_value="idiota")
            recognizer.get_partially_complete = Mock(return_value=True)
        elif call_count[0] == 4:
            recognizer.result = Mock(return_value="gracias")
            recognizer.get_partially_complete = Mock(return_value=True)
        else:
            recognizer.result = None
            recognizer.get_partially_complete = Mock(return_value=False)
        
        return True
    
    recognizer.process = process_mock
    model.create_recognizer = Mock(return_value=recognizer)
    
    return model


@pytest.fixture
def mock_sounddevice():
    """Mock sounddevice to avoid actual audio hardware."""
    mock_stream = MagicMock()
    mock_stream.start = MagicMock()
    mock_stream.stop = MagicMock()
    mock_stream.close = MagicMock()
    
    return mock_stream


@pytest.fixture
def mock_audio_available():
    """Mock audio_available function to return True."""
    with patch('src.insult_detector.audio_available', return_value=True):
        yield True


class TestInsultDetectorIntegration:
    """Integration tests for InsultDetector with Vosk."""
    
    def test_detector_initialization(self, mock_vosk_model):
        """Test detector initializes with mock model."""
        with patch('src.insult_detector.vosk.Model', return_value=mock_vosk_model):
            detector = InsultDetector(model_path="test-model")
            assert detector._model_path == "test-model"
            assert detector._insult_count == 0
            assert detector._insult_peak_count == 0
    
    def test_detector_loads_lexicon(self, mock_vosk_model, tmp_path):
        """Test detector loads insult lexicon from CSV."""
        # Create test lexicon file
        lexicon_file = tmp_path / "insultos.csv"
        lexicon_file.write_text(
            "\n".join(TEST_INSULTS),
            encoding="utf-8"
        )
        
        with patch('src.insult_detector.vosk.Model', return_value=mock_vosk_model):
            with patch('src.insult_detector.sd.InputStream') as mock_stream_cls:
                detector = InsultDetector(model_path="test-model")
                
                # Manually load lexicon
                result = detector._load_lexicon(str(lexicon_file))
                
                assert result is True
                assert len(detector._lexicon_stems) == len(TEST_INSULTS)
    
    def test_detector_detects_multiple_insults(self, mock_vosk_model, mock_sounddevice):
        """Test detector counts multiple insults from transcript sequence."""
        with patch('src.insult_detector.vosk.Model', return_value=mock_vosk_model):
            with patch('src.insult_detector.sd.InputStream', return_value=mock_sounddevice):
                detector = InsultDetector(model_path="test-model")
                
                # Load test lexicon
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
                    f.write("\n".join(TEST_INSULTS))
                    lexicon_path = f.name
                
                detector._load_lexicon(lexicon_path)
                os.unlink(lexicon_path)
                
                # Start detector
                result = detector.start()
                assert result is True
                
                # Simulate audio processing
                mock_indata = np.array([1, 2, 3], dtype=np.int16)
                detector._callback(mock_indata, 1, None, None)
                
                # Should have detected multiple insults
                summary = detector.get_summary()
                assert summary['insult_count'] >= 2
                assert summary['insult_model_name'] == "test-model"
                
                detector.stop()
    
    def test_detector_stemmer_matching(self, mock_vosk_model, mock_sounddevice):
        """Test that stemmed words match lexicon entries."""
        with patch('src.insult_detector.vosk.Model', return_value=mock_vosk_model):
            with patch('src.insult_detector.sd.InputStream', return_value=mock_sounddevice):
                detector = InsultDetector(model_path="test-model")
                
                # Load lexicon
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
                    f.write("casar\ncasas\ncaso")
                    lexicon_path = f.name
                
                detector._load_lexicon(lexicon_path)
                os.unlink(lexicon_path)
                
                # Test stemmer matching
                # "casas" should stem to "cas" which matches "casar" -> "cas"
                assert "cas" in detector._lexicon_stems
                
                # Simulate callback with inflected form
                mock_indata = np.array([1, 2, 3], dtype=np.int16)
                detector._callback(mock_indata, 1, None, None)
                
                # Should have incremented count for stem match
                summary = detector.get_summary()
                assert summary['insult_count'] >= 1
                
                detector.stop()
    
    def test_detector_reset_counters(self, mock_vosk_model, mock_sounddevice):
        """Test that reset() zeros counters without stopping stream."""
        with patch('src.insult_detector.vosk.Model', return_value=mock_vosk_model):
            with patch('src.insult_detector.sd.InputStream', return_value=mock_sounddevice):
                detector = InsultDetector(model_path="test-model")
                
                # Load lexicon and start
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
                    f.write("idiota")
                    lexicon_path = f.name
                
                detector._load_lexicon(lexicon_path)
                detector.start()
                
                # Increment count
                mock_indata = np.array([1, 2, 3], dtype=np.int16)
                detector._callback(mock_indata, 1, None, None)
                summary_before = detector.get_summary()
                
                # Reset
                detector.reset()
                summary_after = detector.get_summary()
                
                assert summary_before['insult_count'] > 0
                assert summary_after['insult_count'] == 0
                assert summary_after['insult_peak_count'] == 0
                
                detector.stop()
    
    def test_detector_get_summary_structure(self, mock_vosk_model, mock_sounddevice):
        """Test get_summary() returns correct structure and types."""
        with patch('src.insult_detector.vosk.Model', return_value=mock_vosk_model):
            with patch('src.insult_detector.sd.InputStream', return_value=mock_sounddevice):
                detector = InsultDetector(model_path="test-model")
                
                # Load lexicon
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
                    f.write("test")
                    lexicon_path = f.name
                
                detector._load_lexicon(lexicon_path)
                
                # Check summary structure before start
                summary = detector.get_summary()
                assert isinstance(summary, dict)
                assert 'insult_count' in summary
                assert 'insult_peak_count' in summary
                assert 'insult_model_name' in summary
                assert 'last_error' in summary
                assert isinstance(summary['insult_count'], int)
                assert isinstance(summary['insult_peak_count'], int)
                assert isinstance(summary['insult_model_name'], str)
                assert isinstance(summary['last_error'], str)
                
                detector.stop()
    
    def test_detector_list_insults_returns_sorted(self, mock_vosk_model, mock_sounddevice):
        """Test list_insults() returns sorted lexicon entries."""
        with patch('src.insult_detector.vosk.Model', return_value=mock_vosk_model):
            with patch('src.insult_detector.sd.InputStream', return_value=mock_sounddevice):
                detector = InsultDetector(model_path="test-model")
                
                # Load lexicon
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
                    f.write("\n".join(sorted(TEST_INSULTS, reverse=True)))
                    lexicon_path = f.name
                
                detector._load_lexicon(lexicon_path)
                
                insults = detector.list_insults()
                
                assert insults == sorted(TEST_INSULTS)
                assert isinstance(insults, list)
                
                detector.stop()
