"""
Unit tests for utils.py
Tests utility functions
"""
import pytest
import sys
import os
from pathlib import Path
from PIL import Image


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
from utils import get_resource_path, get_appdata_path, get_insightface_root, create_tray_icon


class TestResourcePath:
    """Test resource path resolution"""

    def test_get_resource_path(self):
        """Test getting resource path"""
        path = get_resource_path('ui.html')

        assert path is not None
        assert isinstance(path, str)

    def test_get_resource_path_relative(self):
        """Test resource path handles relative paths"""
        path = get_resource_path('subdir/file.txt')

        assert 'subdir' in path or 'subdir' in path.replace('\\', '/')


class TestAppDataPath:
    """Test AppData path resolution"""

    def test_get_appdata_path(self):
        """Test getting AppData path"""
        path = get_appdata_path()

        assert path is not None
        assert isinstance(path, Path)

    def test_appdata_path_exists(self):
        """Test AppData path is created"""
        path = get_appdata_path()

        assert path.exists()
        assert path.is_dir()

    def test_appdata_path_structure(self):
        """Test AppData path contains correct structure"""
        path = get_appdata_path()

        # Should contain 'facial_recognition' and 'face_data'
        assert 'facial_recognition' in str(path)
        assert 'face_data' in str(path)


class TestInsightFaceRoot:
    """Test InsightFace model root path"""

    def test_get_insightface_root(self):
        """Test getting InsightFace root"""
        root = get_insightface_root()

        assert root is not None
        assert isinstance(root, str)


class TestTrayIcon:
    """Test tray icon creation"""

    def test_create_tray_icon(self):
        """Test creating tray icon"""
        icon = create_tray_icon()

        assert icon is not None
        assert isinstance(icon, Image.Image)

    def test_tray_icon_size(self):
        """Test tray icon has reasonable size"""
        icon = create_tray_icon()

        # Tray icons can be up to 512x512 for high DPI displays
        assert icon.width > 0
        assert icon.height > 0
        assert icon.width <= 512
        assert icon.height <= 512

    def test_tray_icon_mode(self):
        """Test tray icon is in RGB/RGBA mode"""
        icon = create_tray_icon()

        assert icon.mode in ['RGB', 'RGBA']
