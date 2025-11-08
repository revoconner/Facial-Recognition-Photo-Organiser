"""
Unit tests for settings.py
Tests JSON-based settings management
"""
import pytest
import json
from pathlib import Path


class TestSettingsBasics:
    """Test basic settings operations"""

    def test_settings_initialization(self, test_settings):
        """Test settings initializes with defaults"""
        assert test_settings.get('threshold') == 50
        assert test_settings.get('close_to_tray') is True
        assert test_settings.get('grid_size') == 180

    def test_set_and_get(self, test_settings):
        """Test setting and getting values"""
        test_settings.set('threshold', 65)

        assert test_settings.get('threshold') == 65

    def test_get_with_default(self, test_settings):
        """Test getting non-existent key with default"""
        value = test_settings.get('non_existent_key', 'default_value')

        assert value == 'default_value'

    def test_persistence(self, test_settings, temp_dir):
        """Test settings persist to disk"""
        test_settings.set('threshold', 75)

        # Create new settings instance with same path
        new_settings = type(test_settings)(str(test_settings.settings_path))

        assert new_settings.get('threshold') == 75


class TestSettingsValidation:
    """Test settings validation and constraints"""

    def test_threshold_range(self, test_settings):
        """Test threshold is stored correctly"""
        test_settings.set('threshold', 30)
        assert test_settings.get('threshold') == 30

        test_settings.set('threshold', 70)
        assert test_settings.get('threshold') == 70

    def test_boolean_settings(self, test_settings):
        """Test boolean settings"""
        test_settings.set('close_to_tray', False)
        assert test_settings.get('close_to_tray') is False

        test_settings.set('dynamic_resources', True)
        assert test_settings.get('dynamic_resources') is True

    def test_list_settings(self, test_settings):
        """Test list-based settings"""
        folders = ['/path/to/folder1', '/path/to/folder2']
        test_settings.set('include_folders', folders)

        assert test_settings.get('include_folders') == folders

    def test_string_settings(self, test_settings):
        """Test string settings"""
        test_settings.set('wildcard_exclusions', '*.tmp, *.cache')

        assert test_settings.get('wildcard_exclusions') == '*.tmp, *.cache'


class TestSettingsFileOperations:
    """Test file I/O operations"""

    def test_settings_file_creation(self, temp_dir):
        """Test settings file is created on first save"""
        from settings import Settings

        settings_dir = temp_dir / "new_settings"
        settings_dir.mkdir()

        settings = Settings(str(settings_dir))
        settings.set('threshold', 60)

        settings_file = settings_dir / "settings.json"
        assert settings_file.exists()

    def test_settings_file_format(self, test_settings):
        """Test settings file is valid JSON"""
        test_settings.set('threshold', 55)

        with open(test_settings.settings_file, 'r') as f:
            data = json.load(f)

        assert isinstance(data, dict)
        assert data['threshold'] == 55

    def test_corrupted_settings_file(self, test_settings):
        """Test recovery from corrupted settings file"""
        # Corrupt the settings file
        with open(test_settings.settings_file, 'w') as f:
            f.write("invalid json {{{")

        # Should fall back to defaults
        from settings import Settings
        new_settings = Settings(str(test_settings.settings_path))

        assert new_settings.get('threshold') == 50  # Default value


class TestDefaultSettings:
    """Test default settings values"""

    def test_all_defaults_present(self, test_settings):
        """Test all default settings are present"""
        required_keys = [
            'threshold', 'close_to_tray', 'dynamic_resources',
            'show_unmatched', 'show_hidden', 'show_hidden_photos',
            'show_dev_options', 'min_photos_enabled', 'min_photos_count',
            'grid_size', 'window_width', 'window_height',
            'include_folders', 'exclude_folders', 'wildcard_exclusions',
            'view_mode', 'sort_mode', 'hide_unnamed_persons',
            'scan_frequency'
        ]

        for key in required_keys:
            assert test_settings.get(key) is not None

    def test_default_values(self, test_settings):
        """Test specific default values"""
        assert test_settings.get('threshold') == 50
        assert test_settings.get('grid_size') == 180
        assert test_settings.get('window_width') == 1200
        assert test_settings.get('window_height') == 800
        assert test_settings.get('view_mode') == 'entire_photo'
        assert test_settings.get('sort_mode') == 'names_asc'
        assert test_settings.get('scan_frequency') == 'restart_1_day'
