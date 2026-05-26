"""
Unit tests for CSV migration functionality.

Tests that the migration of sessions.csv is non-destructive and
properly handles legacy schemas by adding new columns with defaults.
"""

import csv
import os
import tempfile
import pytest
from pathlib import Path
from src.data_manager import DataManager, SESSION_FIELDS, _FIELD_DEFAULTS


class TestCSVMigration:
    """Test cases for CSV migration functionality."""
    
    def test_migration_adds_missing_columns(self, tmp_path):
        """Test that migration adds missing columns with defaults."""
        sessions_file = tmp_path / "sessions.csv"
        
        # Create legacy CSV without insult columns
        with open(sessions_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "game", "date", "duration_seconds",
                "happy_count", "angry_count", "neutral_count",
                "happy_percentage", "angry_percentage", "neutral_percentage",
                "peak_rage_count", "happiness_streaks", "emotional_trend",
                "total_frames",
                "scream_count", "scream_peak_db", "scream_total_seconds", "mic_device_name"
            ])
            writer.writerow([
                "Game1", "2024-01-01 12:00:00", "300",
                "10", "5", "5",
                "50.0", "25.0", "25.0",
                "10", "3", "neutral",
                "1000"
            ])
        
        # Create DataManager pointing to temp directory
        dm = DataManager(str(tmp_path))
        
        # Force migration by checking if sessions file exists
        assert os.path.exists(sessions_file)
        
        # Reload to trigger migration
        dm2 = DataManager(str(tmp_path))
        
        # Read migrated file
        with open(sessions_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # Should have insult columns added
        assert "insult_count" in rows[0]
        assert "insult_peak_count" in rows[0]
        assert "insult_model_name" in rows[0]
        
        # Should have default values
        assert rows[0]["insult_count"] == "0"
        assert rows[0]["insult_peak_count"] == "0"
        assert rows[0]["insult_model_name"] == ""
    
    def test_migration_preserves_existing_data(self, tmp_path):
        """Test that migration preserves all existing data."""
        sessions_file = tmp_path / "sessions.csv"
        
        # Create legacy CSV with data
        legacy_data = [
            {
                "game": "Game1",
                "date": "2024-01-01 12:00:00",
                "duration_seconds": "300",
                "happy_count": "10",
                "angry_count": "5",
                "neutral_count": "5",
                "happy_percentage": "50.0",
                "angry_percentage": "25.0",
                "neutral_percentage": "25.0",
                "peak_rage_count": "10",
                "happiness_streaks": "3",
                "emotional_trend": "neutral",
                "total_frames": "1000"
            },
            {
                "game": "Game2",
                "date": "2024-01-02 13:00:00",
                "duration_seconds": "600",
                "happy_count": "20",
                "angry_count": "10",
                "neutral_count": "10",
                "happy_percentage": "50.0",
                "angry_percentage": "25.0",
                "neutral_percentage": "25.0",
                "peak_rage_count": "20",
                "happiness_streaks": "5",
                "emotional_trend": "neutral",
                "total_frames": "2000"
            }
        ]
        
        with open(sessions_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=legacy_data[0].keys())
            writer.writeheader()
            writer.writerows(legacy_data)
        
        # Create DataManager
        dm = DataManager(str(tmp_path))
        
        # Read migrated file
        with open(sessions_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # Verify all original data preserved
        assert len(rows) == 2
        assert rows[0]["game"] == "Game1"
        assert rows[0]["duration_seconds"] == "300"
        assert rows[1]["game"] == "Game2"
        assert rows[1]["duration_seconds"] == "600"
    
    def test_migration_idempotent(self, tmp_path):
        """Test that running migration multiple times is safe."""
        sessions_file = tmp_path / "sessions.csv"
        
        # Create CSV without insult columns
        with open(sessions_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "game", "date", "duration_seconds",
                "happy_count", "angry_count", "neutral_count",
                "happy_percentage", "angry_percentage", "neutral_percentage",
                "peak_rage_count", "happiness_streaks", "emotional_trend",
                "total_frames",
                "scream_count", "scream_peak_db", "scream_total_seconds", "mic_device_name"
            ])
            writer.writerow(["Game1", "2024-01-01", "300", "10", "5", "5", "50.0", "25.0", "25.0", "10", "3", "neutral", "1000"])
        
        # Create DataManager and trigger migration
        dm = DataManager(str(tmp_path))
        
        # Read file after first migration
        with open(sessions_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            first_rows = list(reader)
        
        # Create another DataManager (should be idempotent)
        dm2 = DataManager(str(tmp_path))
        
        # Read file after second migration
        with open(sessions_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            second_rows = list(reader)
        
        # Should be identical
        assert len(first_rows) == len(second_rows)
        assert first_rows[0]["game"] == second_rows[0]["game"]
    
    def test_migration_handles_empty_file(self, tmp_path):
        """Test migration handles CSV with only header."""
        sessions_file = tmp_path / "sessions.csv"
        
        with open(sessions_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "game", "date", "duration_seconds",
                "happy_count", "angry_count", "neutral_count",
                "happy_percentage", "angry_percentage", "neutral_percentage",
                "peak_rage_count", "happiness_streaks", "emotional_trend",
                "total_frames",
                "scream_count", "scream_peak_db", "scream_total_seconds", "mic_device_name"
            ])
        
        dm = DataManager(str(tmp_path))
        
        with open(sessions_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        assert len(rows) == 0
    
    def test_migration_handles_corrupt_file(self, tmp_path):
        """Test migration handles corrupt/binary file gracefully."""
        sessions_file = tmp_path / "sessions.csv"
        sessions_file.write_bytes(b"\x00\x01\x02\x03")
        
        # Should not crash, just skip migration
        dm = DataManager(str(tmp_path))
    
    def test_migration_adds_all_insult_fields(self, tmp_path):
        """Test that all insult fields are added with correct defaults."""
        sessions_file = tmp_path / "sessions.csv"
        
        with open(sessions_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "game", "date", "duration_seconds",
                "happy_count", "angry_count", "neutral_count",
                "happy_percentage", "angry_percentage", "neutral_percentage",
                "peak_rage_count", "happiness_streaks", "emotional_trend",
                "total_frames",
                "scream_count", "scream_peak_db", "scream_total_seconds", "mic_device_name"
            ])
            writer.writerow(["Game1", "2024-01-01", "300", "10", "5", "5", "50.0", "25.0", "25.0", "10", "3", "neutral", "1000"])
        
        dm = DataManager(str(tmp_path))
        
        with open(sessions_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # Verify all insult fields present
        assert "insult_count" in rows[0]
        assert "insult_peak_count" in rows[0]
        assert "insult_model_name" in rows[0]
        
        # Verify defaults match _FIELD_DEFAULTS
        assert rows[0]["insult_count"] == str(_FIELD_DEFAULTS["insult_count"])
        assert rows[0]["insult_peak_count"] == str(_FIELD_DEFAULTS["insult_peak_count"])
        assert rows[0]["insult_model_name"] == _FIELD_DEFAULTS["insult_model_name"]
