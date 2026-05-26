"""
Unit tests for SpanishStemmer class.

Tests the suffix-stripping algorithm with fixture pairs covering:
- Regular nouns/verbs with common suffixes
- Irregular forms that should return unchanged
- Edge cases (empty strings, single chars)
"""

import pytest
from src.insult_detector import SpanishStemmer


class TestSpanishStemmer:
    """Test cases for SpanishStemmer.stem() method."""
    
    def test_stem_gilipollas(self):
        """Test stem removal from 'gilipollas' -> 'gilipoll'."""
        result = SpanishStemmer.stem("gilipollas")
        assert result == "gilipoll"
    
    def test_stem_idiota(self):
        """Test stem removal from 'idiota' -> 'idiot'."""
        result = SpanishStemmer.stem("idiota")
        assert result == "idiot"
    
    def test_stem_gracias(self):
        """Test stem removal from 'gracias' -> 'graci'."""
        result = SpanishStemmer.stem("gracias")
        assert result == "graci"
    
    def test_stem_casar_inflection(self):
        """Test verb inflection 'casamos' -> 'cas'."""
        result = SpanishStemmer.stem("casamos")
        assert result == "cas"
    
    def test_stem_casas_inflection(self):
        """Test noun inflection 'casas' -> 'cas'."""
        result = SpanishStemmer.stem("casas")
        assert result == "cas"
    
    def test_stem_caso_inflection(self):
        """Test noun inflection 'caso' -> 'cas'."""
        result = SpanishStemmer.stem("caso")
        assert result == "cas"
    
    def test_stem_casa_inflection(self):
        """Test noun inflection 'casa' -> 'cas'."""
        result = SpanishStemmer.stem("casa")
        assert result == "cas"
    
    def test_stem_already_stemmed(self):
        """Test word already in base form returns unchanged."""
        result = SpanishStemmer.stem("idiot")
        assert result == "idiot"
    
    def test_stem_empty_string(self):
        """Test empty string returns empty string."""
        result = SpanishStemmer.stem("")
        assert result == ""
    
    def test_stem_single_char(self):
        """Test single character returns unchanged."""
        result = SpanishStemmer.stem("a")
        assert result == "a"
    
    def test_stem_whitespace(self):
        """Test whitespace is stripped."""
        result = SpanishStemmer.stem("  gilipollas  ")
        assert result == "gilipoll"
    
    def test_stem_uppercase(self):
        """Test uppercase is converted to lowercase."""
        result = SpanishStemmer.stem("GILIPOLLAS")
        assert result == "gilipoll"
    
    def test_stem_mixed_case(self):
        """Test mixed case is converted to lowercase."""
        result = SpanishStemmer.stem("GilIpOlLaS")
        assert result == "gilipoll"
    
    def test_stem_suffix_ando(self):
        """Test gerund form '-ando' removal."""
        result = SpanishStemmer.stem("comiendo")
        assert result == "comi"
    
    def test_stem_suffix_iendo(self):
        """Test gerund form '-iendo' removal."""
        result = SpanishStemmer.stem("leyendo")
        assert result == "ley"
    
    def test_stem_suffix_plural_os(self):
        """Test masculine plural '-os' removal."""
        result = SpanishStemmer.stem("ratones")
        assert result == "raton"
    
    def test_stem_suffix_plural_as(self):
        """Test feminine plural '-as' removal."""
        result = SpanishStemmer.stem("ratas")
        assert result == "rat"
    
    def test_stem_suffix_third_person_plural_an(self):
        """Test verb form '-an' removal."""
        result = SpanishStemmer.stem("hablan")
        assert result == "habl"
    
    def test_stem_suffix_third_person_plural_en(self):
        """Test verb form '-en' removal."""
        result = SpanishStemmer.stem("viven")
        assert result == "viv"
    
    def test_stem_suffix_ir(self):
        """Test verb infinitive '-ir' removal."""
        result = SpanishStemmer.stem("vivir")
        assert result == "viv"
    
    def test_stem_suffix_er(self):
        """Test verb infinitive '-er' removal."""
        result = SpanishStemmer.stem("comer")
        assert result == "com"
    
    def test_stem_suffix_ar(self):
        """Test verb infinitive '-ar' removal."""
        result = SpanishStemmer.stem("hablar")
        assert result == "habl"
