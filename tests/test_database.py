"""
Unit tests for database.py
Tests SQLite + LMDB dual-database operations
"""
import pytest
import numpy as np
from pathlib import Path


class TestPhotoOperations:
    """Test photo-related database operations"""

    def test_add_photo(self, test_db, sample_photo_data):
        """Test adding a photo"""
        photo_id = test_db.add_photo(
            sample_photo_data['file_path'],
            sample_photo_data['file_hash']
        )

        assert photo_id is not None
        assert photo_id > 0

    def test_add_duplicate_photo(self, test_db, sample_photo_data):
        """Test adding the same photo twice returns same ID"""
        photo_id1 = test_db.add_photo(
            sample_photo_data['file_path'],
            sample_photo_data['file_hash']
        )
        photo_id2 = test_db.add_photo(
            sample_photo_data['file_path'],
            sample_photo_data['file_hash']
        )

        assert photo_id1 == photo_id2

    def test_get_all_scanned_paths(self, populated_db):
        """Test retrieving all scanned photo paths"""
        paths = populated_db.get_all_scanned_paths()

        assert len(paths) == 5
        assert '/test/photos/image0.jpg' in paths

    def test_remove_deleted_photos(self, populated_db):
        """Test removing photos that no longer exist on disk"""
        # Keep only 2 photos
        existing_paths = {'/test/photos/image0.jpg', '/test/photos/image1.jpg'}

        removed_count = populated_db.remove_deleted_photos(existing_paths)

        assert removed_count == 3  # 5 - 2 = 3 removed

    def test_update_photo_status(self, test_db, sample_photo_data):
        """Test updating photo scan status"""
        photo_id = test_db.add_photo(
            sample_photo_data['file_path'],
            sample_photo_data['file_hash']
        )

        test_db.update_photo_status(photo_id, 'completed')

        # Verify status updated
        conn = test_db._get_connection()
        cursor = conn.execute(
            "SELECT scan_status FROM photos WHERE photo_id = ?",
            (photo_id,)
        )
        status = cursor.fetchone()[0]

        assert status == 'completed'


class TestFaceOperations:
    """Test face-related database operations"""

    def test_add_face(self, test_db, sample_photo_data, sample_embedding, sample_bbox):
        """Test adding a face with embedding"""
        photo_id = test_db.add_photo(
            sample_photo_data['file_path'],
            sample_photo_data['file_hash']
        )

        face_id = test_db.add_face(photo_id, sample_embedding, sample_bbox)

        assert face_id is not None
        assert face_id > 0

    def test_get_face_embedding(self, test_db, sample_photo_data, sample_embedding, sample_bbox):
        """Test retrieving face embedding from LMDB"""
        photo_id = test_db.add_photo(
            sample_photo_data['file_path'],
            sample_photo_data['file_hash']
        )
        face_id = test_db.add_face(photo_id, sample_embedding, sample_bbox)

        retrieved_embedding = test_db.get_face_embedding(face_id)

        assert retrieved_embedding is not None
        assert len(retrieved_embedding) == 512
        # Check similarity (should be very close due to float precision)
        similarity = np.dot(sample_embedding, retrieved_embedding)
        assert similarity > 0.99

    def test_get_all_embeddings(self, populated_db):
        """Test batch retrieval of all embeddings"""
        face_ids, embeddings = populated_db.get_all_embeddings()

        assert len(face_ids) == 10  # 5 photos × 2 faces
        assert embeddings.shape == (10, 512)
        assert embeddings.dtype == np.float32

    def test_get_face_data(self, populated_db):
        """Test retrieving face metadata"""
        face_id = populated_db.face_ids[0]

        face_data = populated_db.get_face_data(face_id)

        assert face_data is not None
        assert 'file_path' in face_data
        assert 'bbox_x1' in face_data
        assert 'bbox_y1' in face_data


class TestClusteringOperations:
    """Test clustering-related database operations"""

    def test_create_clustering(self, test_db):
        """Test creating a new clustering"""
        clustering_id = test_db.create_clustering(threshold=50)

        assert clustering_id is not None
        assert clustering_id > 0

    def test_get_active_clustering(self, test_db):
        """Test retrieving active clustering"""
        clustering_id = test_db.create_clustering(threshold=50)

        active = test_db.get_active_clustering()

        assert active is not None
        assert active['clustering_id'] == clustering_id
        assert active['threshold'] == 50

    def test_save_cluster_assignments(self, populated_db):
        """Test saving cluster assignments"""
        clustering_id = populated_db.create_clustering(threshold=50)

        face_ids = populated_db.face_ids[:5]
        person_ids = [1, 1, 2, 2, 3]  # 3 persons
        confidences = [0.95, 0.93, 0.90, 0.88, 0.85]

        populated_db.save_cluster_assignments(
            clustering_id,
            face_ids,
            person_ids,
            confidences
        )

        # Verify assignments saved
        conn = populated_db._get_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM cluster_assignments WHERE clustering_id = ?",
            (clustering_id,)
        )
        count = cursor.fetchone()[0]

        assert count == 5

    def test_get_persons_in_clustering(self, populated_db):
        """Test retrieving all persons in a clustering"""
        clustering_id = populated_db.create_clustering(threshold=50)

        # Create assignments: 3 persons
        face_ids = populated_db.face_ids
        person_ids = [1, 1, 1, 2, 2, 2, 3, 3, 0, 0]  # Person 0 = unmatched
        confidences = [0.95] * 10

        populated_db.save_cluster_assignments(
            clustering_id,
            face_ids,
            person_ids,
            confidences
        )

        persons = populated_db.get_persons_in_clustering(clustering_id)

        assert len(persons) == 4  # 3 persons + unmatched (0)

    def test_invalidate_cache(self, populated_db):
        """Test cache invalidation"""
        clustering_id = populated_db.create_clustering(threshold=50)

        # First call - populates cache
        active1 = populated_db.get_active_clustering()

        # Invalidate
        populated_db.invalidate_cache()

        # Second call - should fetch fresh data
        active2 = populated_db.get_active_clustering()

        assert active1['clustering_id'] == active2['clustering_id']


class TestTaggingOperations:
    """Test face tagging operations"""

    def test_tag_faces(self, populated_db):
        """Test tagging faces with a name"""
        face_ids = populated_db.face_ids[:3]

        populated_db.tag_faces(face_ids, "John Doe", is_manual=True)

        # Verify tags
        tags = populated_db.get_face_tags(face_ids)

        assert len(tags) == 3
        for face_id in face_ids:
            assert tags[face_id] == "John Doe"

    def test_untag_faces(self, populated_db):
        """Test removing tags from faces"""
        face_ids = populated_db.face_ids[:3]

        # Tag first
        populated_db.tag_faces(face_ids, "John Doe")

        # Then untag
        populated_db.untag_faces(face_ids)

        # Verify tags removed
        tags = populated_db.get_face_tags(face_ids)

        assert len(tags) == 0

    def test_get_face_tags(self, populated_db):
        """Test retrieving face tags"""
        face_ids = populated_db.face_ids[:5]

        # Tag some faces
        populated_db.tag_faces(face_ids[:2], "Alice")
        populated_db.tag_faces(face_ids[2:4], "Bob")
        # face_ids[4] remains untagged

        tags = populated_db.get_face_tags(face_ids)

        assert len(tags) == 4  # 4 tagged, 1 untagged
        assert tags[face_ids[0]] == "Alice"
        assert tags[face_ids[2]] == "Bob"
        assert face_ids[4] not in tags

    def test_set_primary_photo(self, populated_db):
        """Test setting primary photo for a tag"""
        face_id = populated_db.face_ids[0]

        populated_db.tag_faces([face_id], "Alice")
        populated_db.set_primary_photo_for_tag("Alice", face_id)

        # Verify primary photo set
        conn = populated_db._get_connection()
        cursor = conn.execute(
            "SELECT face_id FROM tag_primary_photos WHERE tag_name = ?",
            ("Alice",)
        )
        result = cursor.fetchone()

        assert result is not None
        assert result[0] == face_id


class TestHiddenOperations:
    """Test hiding persons and photos"""

    def test_hide_person(self, populated_db):
        """Test hiding a person"""
        clustering_id = populated_db.create_clustering(threshold=50)
        person_id = 1

        populated_db.hide_person(clustering_id, person_id)

        # Verify hidden
        hidden_persons = populated_db.get_hidden_persons(clustering_id)

        assert person_id in hidden_persons

    def test_unhide_person(self, populated_db):
        """Test unhiding a person"""
        clustering_id = populated_db.create_clustering(threshold=50)
        person_id = 1

        # Hide first
        populated_db.hide_person(clustering_id, person_id)

        # Then unhide
        populated_db.unhide_person(clustering_id, person_id)

        # Verify not hidden
        hidden_persons = populated_db.get_hidden_persons(clustering_id)

        assert person_id not in hidden_persons

    def test_hide_photo(self, populated_db):
        """Test hiding a photo"""
        face_id = populated_db.face_ids[0]

        populated_db.hide_photo(face_id)

        # Verify hidden
        hidden_photos = populated_db.get_hidden_photos()

        assert face_id in hidden_photos

    def test_unhide_photo(self, populated_db):
        """Test unhiding a photo"""
        face_id = populated_db.face_ids[0]

        # Hide first
        populated_db.hide_photo(face_id)

        # Then unhide
        populated_db.unhide_photo(face_id)

        # Verify not hidden
        hidden_photos = populated_db.get_hidden_photos()

        assert face_id not in hidden_photos


class TestBatchOperations:
    """Test batch processing and parameter limits"""

    def test_large_batch_tag_faces(self, populated_db):
        """Test tagging large batch of faces (>500)"""
        # Create 600 faces
        photo_id = populated_db.add_photo('/test/large_batch.jpg', 'hash_large')

        face_ids = []
        for i in range(600):
            emb = np.random.randn(512).astype(np.float32)
            emb = emb / np.linalg.norm(emb)
            face_id = populated_db.add_face(
                photo_id,
                emb,
                [0, 0, 100, 100]
            )
            face_ids.append(face_id)

        # Tag all at once (should batch internally)
        populated_db.tag_faces(face_ids, "Large Batch Test")

        # Verify all tagged
        tags = populated_db.get_face_tags(face_ids)

        assert len(tags) == 600


class TestDatabaseIntegrity:
    """Test database integrity and error handling"""

    def test_concurrent_reads(self, populated_db):
        """Test that multiple read operations don't conflict"""
        # SQLite WAL mode should allow concurrent reads
        result1 = populated_db.get_all_scanned_paths()
        result2 = populated_db.get_all_embeddings()

        assert len(result1) > 0
        assert len(result2[0]) > 0

    def test_close_database(self, test_db):
        """Test database cleanup on close"""
        test_db.close()

        # After close, LMDB env should be None
        assert test_db.env is None
