import pytest
from app.normalization.team_normalizer import normalize_team_name


class TestTeamNormalization:
    def test_basic_normalization(self):
        assert normalize_team_name("spain") == "Spain"
        assert normalize_team_name("SPAIN") == "Spain"
        assert normalize_team_name("sPaIn") == "Spain"
    
    def test_whitespace_handling(self):
        assert normalize_team_name("  Spain  ") == "Spain"
        assert normalize_team_name("Spain   France") == "Spain France"
        assert normalize_team_name("  multiple   spaces  ") == "Multiple Spaces"
    
    def test_empty_input(self):
        assert normalize_team_name("") == ""
        assert normalize_team_name(None) == ""
    
    def test_special_characters_preserved(self):
        assert normalize_team_name("Cote D'Ivoire") == "Cote D'Ivoire"
        assert normalize_team_name("Burkina Faso") == "Burkina Faso"
    
    def test_deterministic_output(self):
        """Same input always produces same output."""
        name = "turkiye"
        result1 = normalize_team_name(name)
        result2 = normalize_team_name(name)
        assert result1 == result2
    
    def test_real_team_names(self):
        """Test with actual team names from the API."""
        assert normalize_team_name("Turkiye") == "Turkiye"
        assert normalize_team_name("Senegal") == "Senegal"
        assert normalize_team_name("Morocco") == "Morocco"
        assert normalize_team_name("Algeria") == "Algeria"
        assert normalize_team_name("Czechia") == "Czechia"

    def test_acronyms_preserved(self):
        """Acronyms like USA, DR, IR should remain uppercase."""
        assert normalize_team_name("USA") == "USA"
        assert normalize_team_name("usa") == "USA"
        assert normalize_team_name("USA") == "USA"
        assert normalize_team_name("Ir Iran") == "IR Iran"
        assert normalize_team_name("ir iran") == "IR Iran"
        assert normalize_team_name("Congo Dr") == "Congo DR"
        assert normalize_team_name("congo dr") == "Congo DR"

    def test_cote_divoire_casing(self):
        """Cote D'Ivoire should preserve the apostrophe-separated casing."""
        assert normalize_team_name("Cote d'Ivoire") == "Cote D'Ivoire"
        assert normalize_team_name("cote d'ivoire") == "Cote D'Ivoire"
        assert normalize_team_name("COTE D'IVOIRE") == "Cote D'Ivoire"
