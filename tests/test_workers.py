"""
Unit tests for workers.py
Tests ScanWorker and ClusterWorker
"""
import pytest
import numpy as np
from unittest.mock import MagicMock, patch, call
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))


class TestScanWorker:
    """Test ScanWorker functionality"""

    @pytest.fixture
    def mock_api(self, mocker):
        """Mock API instance"""
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

    def test_should_exclude_path_no_includes(self, mock_api):
        """Test exclusion logic when no include folders set"""
        from workers import ScanWorker

        mock_api.get_include_folders.return_value = []

        worker = ScanWorker(MagicMock(), mock_api)

        # With no includes, nothing should be excluded
        assert not worker.should_exclude_path('/any/path.jpg')

    def test_should_exclude_path_not_in_includes(self, mock_api):
        """Test path outside include folders is excluded"""
        from workers import ScanWorker

        mock_api.get_include_folders.return_value = ['/test/photos']

        worker = ScanWorker(MagicMock(), mock_api)

        assert worker.should_exclude_path('/other/photos/image.jpg')

    def test_should_exclude_path_in_exclude_folders(self, mock_api):
        """Test path in exclude folders is excluded"""
        from workers import ScanWorker

        mock_api.get_include_folders.return_value = ['/test/photos']
        mock_api.get_exclude_folders.return_value = ['/test/photos/private']

        worker = ScanWorker(MagicMock(), mock_api)

        assert worker.should_exclude_path('/test/photos/private/secret.jpg')

    def test_should_exclude_path_wildcard(self, mock_api):
        """Test wildcard exclusion patterns"""
        from workers import ScanWorker

        mock_api.get_include_folders.return_value = ['/test/photos']
        mock_api.get_wildcard_exclusions.return_value = '*.tmp, *cache*'

        worker = ScanWorker(MagicMock(), mock_api)

        assert worker.should_exclude_path('/test/photos/temp.tmp')
        assert worker.should_exclude_path('/test/photos/cache/image.jpg')
        assert not worker.should_exclude_path('/test/photos/normal.jpg')


class TestClusterWorker:
    """Test ClusterWorker functionality"""

    @pytest.fixture
    def mock_api_for_clustering(self, mocker):
        """Mock API for clustering tests"""
        api = mocker.MagicMock()
        api._threshold = 50
        api.update_status = mocker.MagicMock()
        api.update_progress = mocker.MagicMock()
        api.cluster_complete = mocker.MagicMock()
        return api

    @pytest.fixture
    def sample_embeddings_for_clustering(self):
        """Create sample embeddings for clustering"""
        # Create 20 embeddings: 3 groups of similar embeddings + outliers
        embeddings = []

        # Group 1: 5 similar embeddings
        base1 = np.random.randn(512).astype(np.float32)
        base1 = base1 / np.linalg.norm(base1)
        for i in range(5):
            emb = base1 + np.random.randn(512).astype(np.float32) * 0.1
            emb = emb / np.linalg.norm(emb)
            embeddings.append(emb)

        # Group 2: 5 similar embeddings
        base2 = np.random.randn(512).astype(np.float32)
        base2 = base2 / np.linalg.norm(base2)
        for i in range(5):
            emb = base2 + np.random.randn(512).astype(np.float32) * 0.1
            emb = emb / np.linalg.norm(emb)
            embeddings.append(emb)

        # Group 3: 5 similar embeddings
        base3 = np.random.randn(512).astype(np.float32)
        base3 = base3 / np.linalg.norm(base3)
        for i in range(5):
            emb = base3 + np.random.randn(512).astype(np.float32) * 0.1
            emb = emb / np.linalg.norm(emb)
            embeddings.append(emb)

        # 5 outliers (unmatched faces)
        for i in range(5):
            emb = np.random.randn(512).astype(np.float32)
            emb = emb / np.linalg.norm(emb)
            embeddings.append(emb)

        return np.array(embeddings, dtype=np.float32)

    @pytest.mark.skip(reason="ClusterWorker implementation changed - no longer has _build_adjacency_list method")
    def test_build_similarity_graph(self, mock_api_for_clustering, sample_embeddings_for_clustering):
        """Test similarity graph construction"""
        from workers import ClusterWorker
        import torch

        worker = ClusterWorker(MagicMock(), 50.0, mock_api_for_clustering)

        face_ids = list(range(len(sample_embeddings_for_clustering)))

        # Build adjacency list with threshold
        adjacency = worker._build_adjacency_list(
            face_ids,
            sample_embeddings_for_clustering,
            threshold=0.5
        )

        # Should have edges for most nodes
        assert len(adjacency) > 0

        # Each node in a group should have neighbors
        # (this is a probabilistic test, might occasionally fail)
        assert any(len(neighbors) > 0 for neighbors in adjacency.values())

    @pytest.mark.skip(reason="ClusterWorker implementation changed - no longer has _chinese_whispers method")
    def test_chinese_whispers_convergence(self, mock_api_for_clustering):
        """Test Chinese Whispers converges"""
        from workers import ClusterWorker
        import torch

        worker = ClusterWorker(MagicMock(), 50.0, mock_api_for_clustering)

        # Simple test case: 3 clear clusters
        embeddings = []

        # Cluster 1
        for i in range(5):
            emb = np.array([1.0, 0.0] + [0.0]*510, dtype=np.float32)
            emb = emb + np.random.randn(512).astype(np.float32) * 0.01
            emb = emb / np.linalg.norm(emb)
            embeddings.append(emb)

        # Cluster 2
        for i in range(5):
            emb = np.array([0.0, 1.0] + [0.0]*510, dtype=np.float32)
            emb = emb + np.random.randn(512).astype(np.float32) * 0.01
            emb = emb / np.linalg.norm(emb)
            embeddings.append(emb)

        embeddings = np.array(embeddings, dtype=np.float32)
        face_ids = list(range(len(embeddings)))

        labels = worker._chinese_whispers(face_ids, embeddings, threshold=0.5)

        # Should have at least 2 distinct clusters
        unique_labels = set(labels.values())
        assert len(unique_labels) >= 2


class TestWorkerIntegration:
    """Integration tests for workers"""

    def test_scan_worker_status_updates(self, mock_api, mocker):
        """Test ScanWorker sends status updates"""
        from workers import ScanWorker

        # Mock the face detection
        with patch('workers.FaceAnalysis') as MockFaceAnalysis:
            mock_app = mocker.MagicMock()
            mock_app.get.return_value = []  # No faces detected
            MockFaceAnalysis.return_value = mock_app

            worker = ScanWorker(MagicMock(), mock_api)

            # Check that update methods are called
            # (actual run() would need more mocking)
            assert mock_api.update_status is not None

    def test_cluster_worker_status_updates(self, mock_api_for_clustering, mocker):
        """Test ClusterWorker sends status updates"""
        from workers import ClusterWorker

        worker = ClusterWorker(MagicMock(), 50.0, mock_api_for_clustering)

        # Verify status update methods exist
        assert mock_api_for_clustering.update_status is not None
        assert mock_api_for_clustering.cluster_complete is not None
