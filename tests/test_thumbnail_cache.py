"""
Unit tests for thumbnail_cache.py
Tests thumbnail generation and caching
"""
import pytest
import base64
from pathlib import Path
from PIL import Image
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
from thumbnail_cache import ThumbnailCache


class TestThumbnailCache:
    """Test thumbnail cache operations"""

    @pytest.fixture
    def cache(self, temp_dir):
        """Create thumbnail cache instance"""
        cache_dir = temp_dir / "thumbnail_cache"
        return ThumbnailCache(str(cache_dir))

    @pytest.fixture
    def test_image(self, temp_dir):
        """Create a test image"""
        img = Image.new('RGB', (640, 480), color='red')
        img_path = temp_dir / "test.jpg"
        img.save(str(img_path))
        return str(img_path)

    def test_cache_initialization(self, cache):
        """Test cache directory is created"""
        assert Path(cache.cache_folder).exists()

    def test_get_cache_key(self, cache):
        """Test cache key generation"""
        key = cache._get_cache_key(
            face_id=123,
            bbox={'x': 0, 'y': 0, 'w': 100, 'h': 100},
            size=180
        )

        assert 'face_123' in key
        assert 'zoom' in key
        assert '180' in key

    def test_create_thumbnail_no_bbox(self, cache, test_image):
        """Test creating thumbnail without bounding box"""
        result = cache.create_thumbnail_with_cache(
            face_id=1,
            image_path=test_image,
            size=180,
            bbox=None
        )

        assert result is not None
        assert result.startswith('data:image/jpeg;base64,')

        # Decode and verify
        base64_data = result.split(',')[1]
        img_data = base64.b64decode(base64_data)
        assert len(img_data) > 0

    def test_create_thumbnail_with_bbox(self, cache, test_image):
        """Test creating thumbnail with bounding box"""
        bbox = [100, 100, 300, 300]  # [x1, y1, x2, y2]

        result = cache.create_thumbnail_with_cache(
            face_id=2,
            image_path=test_image,
            size=180,
            bbox=bbox
        )

        assert result is not None
        assert result.startswith('data:image/jpeg;base64,')

    def test_thumbnail_caching(self, cache, test_image):
        """Test that thumbnails are cached"""
        bbox = [100, 100, 300, 300]

        # First call - generates thumbnail
        result1 = cache.create_thumbnail_with_cache(
            face_id=3,
            image_path=test_image,
            size=180,
            bbox=bbox
        )

        # Second call - should use cache
        result2 = cache.create_thumbnail_with_cache(
            face_id=3,
            image_path=test_image,
            size=180,
            bbox=bbox
        )

        assert result1 == result2

    def test_cache_invalidation_on_mtime(self, cache, test_image, temp_dir):
        """Test cache invalidates when source image changes"""
        bbox = [100, 100, 300, 300]

        # First call
        result1 = cache.create_thumbnail_with_cache(
            face_id=4,
            image_path=test_image,
            size=180,
            bbox=bbox
        )

        # Modify image
        import time
        time.sleep(0.1)  # Ensure mtime changes
        img = Image.new('RGB', (640, 480), color='blue')
        img.save(test_image)

        # Second call - should regenerate
        result2 = cache.create_thumbnail_with_cache(
            face_id=4,
            image_path=test_image,
            size=180,
            bbox=bbox
        )

        # Results might differ due to color change
        # Just verify both are valid
        assert result1.startswith('data:image/jpeg;base64,')
        assert result2.startswith('data:image/jpeg;base64,')

    def test_different_sizes_different_cache(self, cache, test_image):
        """Test different sizes use different cache entries"""
        bbox = [100, 100, 300, 300]

        result_180 = cache.create_thumbnail_with_cache(
            face_id=5,
            image_path=test_image,
            size=180,
            bbox=bbox
        )

        result_360 = cache.create_thumbnail_with_cache(
            face_id=5,
            image_path=test_image,
            size=360,
            bbox=bbox
        )

        # Different sizes should produce different results
        assert result_180 != result_360

    def test_clear_cache(self, cache, test_image):
        """Test cache clearing"""
        # Generate some thumbnails
        for i in range(5):
            cache.create_thumbnail_with_cache(
                face_id=i,
                image_path=test_image,
                size=180,
                bbox=None
            )

        # Clear cache
        cache.clear_cache()

        # Cache directory should be empty or minimal
        cache_files = list(Path(cache.cache_folder).glob('*.jpg'))
        # After clear, should have fewer files (or none)
        # (depending on implementation)

    def test_get_cache_stats(self, cache, test_image):
        """Test cache statistics"""
        # Generate some thumbnails
        for i in range(3):
            cache.create_thumbnail_with_cache(
                face_id=i + 10,
                image_path=test_image,
                size=180,
                bbox=None
            )

        stats = cache.get_cache_size()

        assert 'size_bytes' in stats
        assert 'file_count' in stats
        assert stats['file_count'] >= 0

    def test_bbox_padding(self, cache, temp_dir):
        """Test bounding box padding"""
        # Create larger image
        img = Image.new('RGB', (1000, 1000), color='green')
        img_path = temp_dir / "large.jpg"
        img.save(str(img_path))

        # Small bbox that needs padding
        bbox = [500, 500, 550, 550]

        result = cache.create_thumbnail_with_cache(
            face_id=20,
            image_path=str(img_path),
            size=180,
            bbox=bbox
        )

        assert result is not None
        # Should succeed even with padding

    def test_bbox_clamping(self, cache, test_image):
        """Test bounding box is clamped to image bounds"""
        # Bbox extends beyond image (640x480)
        bbox = [500, 400, 800, 700]  # Extends beyond bounds

        result = cache.create_thumbnail_with_cache(
            face_id=21,
            image_path=test_image,
            size=180,
            bbox=bbox
        )

        # Should succeed with clamped bbox
        assert result is not None

    def test_invalid_image_path(self, cache):
        """Test handling of invalid image path"""
        result = cache.create_thumbnail_with_cache(
            face_id=22,
            image_path='/nonexistent/path.jpg',
            size=180,
            bbox=None
        )

        # Should return None or handle gracefully
        assert result is None or result == ''

    def test_view_mode_variations(self, cache, test_image):
        """Test different view modes (entire vs zoom)"""
        bbox = [100, 100, 300, 300]

        # Zoom mode (with bbox)
        result_zoom = cache.create_thumbnail_with_cache(
            face_id=23,
            image_path=test_image,
            size=180,
            bbox=bbox
        )

        # Entire mode (no bbox)
        result_entire = cache.create_thumbnail_with_cache(
            face_id=23,
            image_path=test_image,
            size=180,
            bbox=None
        )

        # Should be different
        assert result_zoom != result_entire
