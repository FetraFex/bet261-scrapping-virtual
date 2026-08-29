import pytest
from app.utils.hashing import calculate_hash


class TestHashing:
    def test_basic_hash(self):
        """Test basic hashing works."""
        result = calculate_hash("hello")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest length
    
    def test_deterministic(self):
        """Same input produces same hash."""
        hash1 = calculate_hash("test data")
        hash2 = calculate_hash("test data")
        assert hash1 == hash2
    
    def test_different_inputs_different_hashes(self):
        """Different inputs produce different hashes."""
        hash1 = calculate_hash("data1")
        hash2 = calculate_hash("data2")
        assert hash1 != hash2
    
    def test_empty_string(self):
        """Empty string produces valid hash."""
        result = calculate_hash("")
        assert len(result) == 64
    
    def test_unicode_string(self):
        """Unicode strings are handled correctly."""
        result = calculate_hash("Équipe de France")
        assert len(result) == 64
    
    def test_json_hash(self):
        """Hashing JSON data works as expected."""
        import json
        data = {"key": "value", "number": 42}
        result = calculate_hash(json.dumps(data))
        assert len(result) == 64
