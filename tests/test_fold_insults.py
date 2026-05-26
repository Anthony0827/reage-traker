"""
Unit tests for _fold_insults_into_rage function.

Tests the rage folding logic that adds insult counts to angry_count
and recalculates percentages.
"""

import pytest
from src.session_runner import _fold_insults_into_rage, RAGE_PER_INSULT


class TestFoldInsultsIntoRage:
    """Test cases for _fold_insults_into_rage() function."""
    
    def test_fold_zero_insults_returns_unchanged(self):
        """Test that zero insults returns summary unchanged."""
        summary = {
            "happy_count": 10,
            "angry_count": 5,
            "neutral_count": 5,
            "peak_rage_count": 10,
        }
        result = _fold_insults_into_rage(summary)
        assert result == summary
    
    def test_fold_zero_weight_returns_unchanged(self):
        """Test that zero weight returns summary unchanged."""
        summary = {
            "happy_count": 10,
            "angry_count": 5,
            "neutral_count": 5,
            "peak_rage_count": 10,
            "insult_count": 5,
        }
        result = _fold_insults_into_rage(summary, weight=0)
        assert result == summary
    
    def test_fold_one_insult_adds_to_angry(self):
        """Test that 1 insult adds 0 (rounded) to angry_count."""
        summary = {
            "happy_count": 10,
            "angry_count": 5,
            "neutral_count": 5,
            "peak_rage_count": 10,
            "insult_count": 1,
        }
        result = _fold_insults_into_rage(summary)
        assert result["angry_count"] == 5  # 1 * 0.3 = 0.3 -> rounded to 0
        assert result["peak_rage_count"] == 10
    
    def test_fold_three_insults_adds_one(self):
        """Test that 3 insults add 1 to angry_count (0.3 * 3 = 0.9 -> 1)."""
        summary = {
            "happy_count": 10,
            "angry_count": 5,
            "neutral_count": 5,
            "peak_rage_count": 10,
            "insult_count": 3,
        }
        result = _fold_insults_into_rage(summary)
        assert result["angry_count"] == 6  # 5 + 1 = 6
        assert result["peak_rage_count"] == 11  # 10 + 1 = 11
    
    def test_fold_ten_insults_adds_three(self):
        """Test that 10 insults add 3 to angry_count (0.3 * 10 = 3)."""
        summary = {
            "happy_count": 10,
            "angry_count": 5,
            "neutral_count": 5,
            "peak_rage_count": 10,
            "insult_count": 10,
        }
        result = _fold_insults_into_rage(summary)
        assert result["angry_count"] == 8  # 5 + 3 = 8
        assert result["peak_rage_count"] == 13  # 10 + 3 = 13
    
    def test_fold_updates_percentages(self):
        """Test that percentages are recalculated after folding."""
        summary = {
            "happy_count": 10,
            "angry_count": 10,
            "neutral_count": 10,
            "peak_rage_count": 10,
            "insult_count": 10,  # adds 3 to angry
        }
        result = _fold_insults_into_rage(summary)
        
        # Total: 10 + 13 + 10 = 33
        # happy: 10/33 = 30.3%
        # angry: 13/33 = 39.4%
        # neutral: 10/33 = 30.3%
        assert result["happy_percentage"] == pytest.approx(30.3, abs=0.1)
        assert result["angry_percentage"] == pytest.approx(39.4, abs=0.1)
        assert result["neutral_percentage"] == pytest.approx(30.3, abs=0.1)
    
    def test_fold_updates_trend_to_rage(self):
        """Test that trend changes to 'rage' when angry_percentage >= 50."""
        summary = {
            "happy_count": 1,
            "angry_count": 1,
            "neutral_count": 0,
            "peak_rage_count": 1,
            "insult_count": 10,  # adds 3 -> angry becomes 4
        }
        result = _fold_insults_into_rage(summary)
        
        # Total: 1 + 4 + 0 = 5
        # angry_percentage = 4/5 = 80% >= 50%
        assert result["emotional_trend"] == "rage"
    
    def test_fold_does_not_change_trend_if_below_50(self):
        """Test that trend stays 'neutral' when angry_percentage < 50."""
        summary = {
            "happy_count": 10,
            "angry_count": 5,
            "neutral_count": 10,
            "peak_rage_count": 10,
            "insult_count": 5,  # adds 1 -> angry becomes 6
        }
        result = _fold_insults_into_rage(summary)
        
        # Total: 10 + 6 + 10 = 26
        # angry_percentage = 6/26 = 23% < 50%
        assert result["emotional_trend"] == "neutral"
    
    def test_fold_custom_weight(self):
        """Test that custom weight parameter works correctly."""
        summary = {
            "happy_count": 10,
            "angry_count": 5,
            "neutral_count": 5,
            "peak_rage_count": 10,
            "insult_count": 10,
        }
        result = _fold_insults_into_rage(summary, weight=1.0)
        
        # 10 insults * 1.0 = 10 added to angry
        assert result["angry_count"] == 15  # 5 + 10 = 15
        assert result["peak_rage_count"] == 20  # 10 + 10 = 20
    
    def test_fold_returns_new_dict_not_same(self):
        """Test that function returns a new dict, not the same object."""
        summary = {
            "happy_count": 10,
            "angry_count": 5,
            "neutral_count": 5,
            "peak_rage_count": 10,
            "insult_count": 10,
        }
        result = _fold_insults_into_rage(summary)
        assert result is not summary
