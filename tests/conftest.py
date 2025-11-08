"""
Pytest configuration and shared fixtures
"""
import pytest
import tempfile
import shutil
import numpy as np
from pathlib import Path
import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database import FaceDatabase
from settings import Settings


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests"""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def test_db(temp_dir):
    """Create a test database instance"""
    db = FaceDatabase(str(temp_dir / "test_db"))
    yield db
    db.close()


@pytest.fixture
def test_settings(temp_dir):
    """Create a test settings instance"""
    settings_dir = temp_dir / "settings"
    settings_dir.mkdir(exist_ok=True)
    settings = Settings(str(settings_dir))
    yield settings


@pytest.fixture
def sample_embedding():
    """Generate a sample face embedding (512-dim normalized vector)"""
    embedding = np.random.randn(512).astype(np.float32)
    # L2 normalize
    embedding = embedding / np.linalg.norm(embedding)
    return embedding


@pytest.fixture
def sample_embeddings(sample_embedding):
    """Generate multiple sample embeddings"""
    embeddings = []
    for _ in range(10):
        emb = np.random.randn(512).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        embeddings.append(emb)
    return embeddings


@pytest.fixture
def sample_bbox():
    """Sample bounding box coordinates [x1, y1, x2, y2]"""
    return [100, 100, 300, 300]


@pytest.fixture
def sample_photo_data():
    """Sample photo metadata"""
    return {
        'file_path': '/test/photos/image1.jpg',
        'file_hash': 'abc123def456'
    }


@pytest.fixture
def populated_db(test_db, sample_embeddings, sample_bbox):
    """Database with sample data"""
    # Add photos
    photo_ids = []
    for i in range(5):
        photo_id = test_db.add_photo(
            f'/test/photos/image{i}.jpg',
            f'hash_{i}'
        )
        # Mark photos as completed so they appear in get_all_scanned_paths
        test_db.update_photo_status(photo_id, 'completed')
        photo_ids.append(photo_id)

    # Add faces with embeddings
    face_ids = []
    for i, photo_id in enumerate(photo_ids):
        # Add 2 faces per photo
        for j in range(2):
            face_id = test_db.add_face(
                photo_id,
                sample_embeddings[i * 2 + j],
                sample_bbox
            )
            face_ids.append(face_id)

    test_db.face_ids = face_ids
    test_db.photo_ids = photo_ids

    return test_db


@pytest.fixture
def mock_insightface_app(mocker):
    """Mock InsightFace app for testing"""
    mock_app = mocker.MagicMock()

    # Mock face detection result
    mock_face = mocker.MagicMock()
    mock_face.bbox = [100, 100, 300, 300]
    mock_face.embedding = np.random.randn(512).astype(np.float32)

    mock_app.get.return_value = [mock_face]

    return mock_app


@pytest.fixture
def sample_image_path(temp_dir):
    """Create a sample test image"""
    from PIL import Image

    # Create a simple test image
    img = Image.new('RGB', (640, 480), color='blue')
    img_path = temp_dir / "test_image.jpg"
    img.save(str(img_path))

    return str(img_path)


@pytest.fixture
def mock_api(mocker):
    """Mock API instance for worker tests"""
    api = mocker.MagicMock()
    api.get_include_folders.return_value = ['/test/photos']
    api.get_exclude_folders.return_value = []
    api.get_wildcard_exclusions.return_value = ''
    api.get_dynamic_resources.return_value = False
    api.is_window_foreground.return_value = True
    api.update_status = mocker.MagicMock()
    api.update_progress = mocker.MagicMock()
    api.scan_complete = mocker.MagicMock()
    return api


@pytest.fixture
def mock_api_for_clustering(mocker):
    """Mock API for clustering tests"""
    api = mocker.MagicMock()
    api._threshold = 50
    api.update_status = mocker.MagicMock()
    api.cluster_complete = mocker.MagicMock()
    return api
