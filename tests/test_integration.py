"""
Integration tests
Tests complete workflows and component interactions
"""
import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))


class TestDatabaseWorkflow:
    """Test complete database workflows"""

    def test_full_photo_workflow(self, test_db, sample_embeddings):
        """Test complete workflow: add photo → add faces → cluster → tag"""
        # 1. Add photos
        photo_id = test_db.add_photo('/test/photo.jpg', 'hash123')

        # 2. Add faces with embeddings
        face_ids = []
        for i in range(3):
            face_id = test_db.add_face(
                photo_id,
                sample_embeddings[i],
                [i*100, i*100, i*100+100, i*100+100]
            )
            face_ids.append(face_id)

        # 3. Create clustering
        clustering_id = test_db.create_clustering(threshold=50)

        # 4. Save cluster assignments
        person_ids = [1, 1, 2]  # 2 persons
        confidences = [0.95, 0.93, 0.90]

        test_db.save_cluster_assignments(
            clustering_id,
            face_ids,
            person_ids,
            confidences
        )

        # 5. Tag faces
        test_db.tag_faces(face_ids[:2], "Alice")
        test_db.tag_faces([face_ids[2]], "Bob")

        # 6. Verify complete state
        persons = test_db.get_persons_in_clustering(clustering_id)
        assert len(persons) == 2

        tags = test_db.get_face_tags(face_ids)
        assert tags[face_ids[0]] == "Alice"
        assert tags[face_ids[2]] == "Bob"


class TestClusteringWorkflow:
    """Test clustering workflow"""

    def test_clustering_with_tags(self, populated_db):
        """Test clustering preserves and applies tags"""
        # Create initial clustering
        clustering_id = populated_db.create_clustering(threshold=50)

        # Assign faces to persons
        face_ids = populated_db.face_ids[:6]
        person_ids = [1, 1, 2, 2, 3, 3]
        confidences = [0.95] * 6

        populated_db.save_cluster_assignments(
            clustering_id,
            face_ids,
            person_ids,
            confidences
        )

        # Tag some faces
        populated_db.tag_faces(face_ids[:2], "Person A")
        populated_db.tag_faces(face_ids[2:4], "Person B")

        # Verify tags persist
        tags = populated_db.get_face_tags(face_ids[:4])
        assert len(tags) == 4
        assert all(tag in ["Person A", "Person B"] for tag in tags.values())


class TestRenameWorkflow:
    """Test person renaming workflow"""

    def test_rename_and_merge(self, populated_db):
        """Test renaming person and potential merging"""
        clustering_id = populated_db.create_clustering(threshold=50)

        # Create 2 persons
        face_ids = populated_db.face_ids[:4]
        person_ids = [1, 1, 2, 2]
        confidences = [0.95] * 4

        populated_db.save_cluster_assignments(
            clustering_id,
            face_ids,
            person_ids,
            confidences
        )

        # Tag person 1
        populated_db.tag_faces(face_ids[:2], "Alice")

        # Later tag person 2 with same name (potential merge scenario)
        populated_db.tag_faces(face_ids[2:4], "Alice")

        # Verify all faces tagged as Alice
        tags = populated_db.get_face_tags(face_ids)
        assert all(tag == "Alice" for tag in tags.values())


class TestHideAndUnhide:
    """Test hiding and unhiding workflow"""

    def test_hide_unhide_workflow(self, populated_db):
        """Test complete hide/unhide workflow"""
        clustering_id = populated_db.create_clustering(threshold=50)
        person_id = 1

        # Hide person
        populated_db.hide_person(clustering_id, person_id)
        hidden = populated_db.get_hidden_persons(clustering_id)
        assert person_id in hidden

        # Unhide person
        populated_db.unhide_person(clustering_id, person_id)
        hidden = populated_db.get_hidden_persons(clustering_id)
        assert person_id not in hidden

    def test_hide_photo_workflow(self, populated_db):
        """Test photo hiding workflow"""
        face_id = populated_db.face_ids[0]

        # Hide photo
        populated_db.hide_photo(face_id)
        hidden = populated_db.get_hidden_photos()
        assert face_id in hidden

        # Unhide photo
        populated_db.unhide_photo(face_id)
        hidden = populated_db.get_hidden_photos()
        assert face_id not in hidden


class TestSettingsIntegration:
    """Test settings integration with other components"""

    def test_settings_affect_behavior(self, test_settings):
        """Test that settings are properly loaded and applied"""
        # Set various settings
        test_settings.set('threshold', 60)
        test_settings.set('include_folders', ['/test/photos', '/test/more'])
        test_settings.set('show_hidden', True)

        # Verify persistence
        assert test_settings.get('threshold') == 60
        assert len(test_settings.get('include_folders')) == 2
        assert test_settings.get('show_hidden') is True


class TestCachingBehavior:
    """Test caching behavior across components"""

    def test_database_cache_invalidation(self, populated_db):
        """Test database cache invalidation"""
        # Get active clustering (populates cache)
        clustering1 = populated_db.get_active_clustering()

        # Create new clustering
        new_id = populated_db.create_clustering(threshold=60)

        # Cache should return new clustering after invalidation
        populated_db.invalidate_cache()
        clustering2 = populated_db.get_active_clustering()

        assert clustering2['clustering_id'] == new_id
        assert clustering2['threshold'] == 60


class TestErrorHandling:
    """Test error handling in integrated scenarios"""

    def test_invalid_face_id(self, test_db):
        """Test handling of invalid face ID"""
        result = test_db.get_face_embedding(999999)

        assert result is None

    def test_empty_database_operations(self, test_db):
        """Test operations on empty database"""
        # Should not crash
        persons = test_db.get_persons_in_clustering(1)
        assert persons == []

        paths = test_db.get_all_scanned_paths()
        assert len(paths) == 0

    def test_invalid_clustering_id(self, test_db):
        """Test operations with invalid clustering ID"""
        # Should handle gracefully
        persons = test_db.get_persons_in_clustering(999999)
        assert persons == []


class TestPerformance:
    """Basic performance tests"""

    def test_large_batch_performance(self, test_db):
        """Test performance with larger dataset"""
        # Add 100 photos
        photo_ids = []
        for i in range(100):
            photo_id = test_db.add_photo(f'/test/photo_{i}.jpg', f'hash_{i}')
            photo_ids.append(photo_id)

        # Add 2 faces per photo
        face_ids = []
        for photo_id in photo_ids:
            for j in range(2):
                emb = np.random.randn(512).astype(np.float32)
                emb = emb / np.linalg.norm(emb)

                face_id = test_db.add_face(
                    photo_id,
                    emb,
                    [0, 0, 100, 100]
                )
                face_ids.append(face_id)

        # Batch operations should complete
        assert len(face_ids) == 200

    @pytest.mark.timeout(5)
    def test_query_performance(self, populated_db):
        """Test query performance (should complete within timeout)"""
        # Multiple queries should complete quickly
        for _ in range(10):
            populated_db.get_all_scanned_paths()
            populated_db.get_all_embeddings()
