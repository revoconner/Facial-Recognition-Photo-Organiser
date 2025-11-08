# Testing Guide

This document describes the testing infrastructure for the Facial Recognition Photo Organizer application.

## Table of Contents
1. [Quick Start](#quick-start)
2. [Test Structure](#test-structure)
3. [Running Tests](#running-tests)
4. [Writing Tests](#writing-tests)
5. [Test Coverage](#test-coverage)
6. [Continuous Integration](#continuous-integration)

---

## Quick Start

### Install Test Dependencies

```bash
pip install pytest pytest-cov pytest-mock pytest-timeout
```

### Run All Tests

**Windows:**
```bash
run_tests.bat
```

**Linux/Mac:**
```bash
chmod +x run_tests.sh
./run_tests.sh
```

**Or directly:**
```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/test_database.py
```

### Run Specific Test Class

```bash
pytest tests/test_database.py::TestPhotoOperations
```

### Run Specific Test

```bash
pytest tests/test_database.py::TestPhotoOperations::test_add_photo
```

---

## Test Structure

```
tests/
├── __init__.py
├── conftest.py                  # Shared fixtures
├── test_database.py             # Database layer tests (100+ tests)
├── test_settings.py             # Settings management tests
├── test_utils.py                # Utility function tests
├── test_workers.py              # Worker thread tests
├── test_thumbnail_cache.py      # Thumbnail cache tests
└── test_integration.py          # Integration tests
```

### Test Categories

#### Unit Tests
- `test_database.py` - Database operations (SQLite + LMDB)
- `test_settings.py` - JSON settings management
- `test_utils.py` - Utility functions
- `test_thumbnail_cache.py` - Thumbnail generation and caching

#### Component Tests
- `test_workers.py` - ScanWorker and ClusterWorker

#### Integration Tests
- `test_integration.py` - Complete workflows and component interactions

---

## Running Tests

### Run All Tests with Coverage

```bash
pytest --cov=app --cov-report=html
```

### Run Only Fast Tests

```bash
pytest -m "not slow"
```

### Run Only Integration Tests

```bash
pytest -m integration
```

### Run with Verbose Output

```bash
pytest -v
```

### Run with Very Verbose Output

```bash
pytest -vv
```

### Stop on First Failure

```bash
pytest -x
```

### Run Last Failed Tests

```bash
pytest --lf
```

### Run Tests in Parallel (requires pytest-xdist)

```bash
pip install pytest-xdist
pytest -n auto
```

---

## Test Coverage

### View Coverage Report

After running tests with coverage:

```bash
# Open HTML report
start htmlcov/index.html  # Windows
open htmlcov/index.html   # Mac
xdg-open htmlcov/index.html  # Linux
```

### Coverage by Module

```bash
pytest --cov=app --cov-report=term-missing
```

### Current Coverage Targets

| Module | Target | Current |
|--------|--------|---------|
| database.py | 90% | TBD |
| settings.py | 95% | TBD |
| utils.py | 90% | TBD |
| workers.py | 75% | TBD |
| thumbnail_cache.py | 85% | TBD |
| api.py | 70% | TBD |

---

## Writing Tests

### Test Naming Convention

```python
class TestFeatureName:
    def test_specific_behavior(self):
        # Arrange
        # Act
        # Assert
```

### Using Fixtures

```python
def test_something(test_db, sample_embedding):
    """Test uses shared fixtures from conftest.py"""
    photo_id = test_db.add_photo('/test.jpg', 'hash')
    face_id = test_db.add_face(photo_id, sample_embedding, bbox)
    assert face_id > 0
```

### Available Fixtures

| Fixture | Description |
|---------|-------------|
| `temp_dir` | Temporary directory (auto-cleanup) |
| `test_db` | Clean database instance |
| `test_settings` | Settings instance with temp file |
| `sample_embedding` | Single 512-dim embedding |
| `sample_embeddings` | List of 10 embeddings |
| `sample_bbox` | Bounding box dict |
| `sample_photo_data` | Photo metadata dict |
| `populated_db` | Database with sample data |
| `mock_insightface_app` | Mocked InsightFace model |
| `sample_image_path` | Path to test image |

### Testing Database Operations

```python
def test_database_operation(test_db):
    # Add data
    photo_id = test_db.add_photo('/test/photo.jpg', 'abc123')

    # Verify
    paths = test_db.get_all_scanned_paths()
    assert '/test/photo.jpg' in paths
```

### Testing with Mocks

```python
def test_worker_with_mock(mocker):
    mock_api = mocker.MagicMock()
    mock_api.update_status = mocker.MagicMock()

    # Use mock in test
    worker = ScanWorker(db, mock_api)
    # ...
```

### Testing Error Handling

```python
def test_handles_invalid_input(test_db):
    result = test_db.get_face_embedding(999999)
    assert result is None  # Graceful failure
```

### Testing Async/Threading

```python
@pytest.mark.timeout(5)
def test_worker_completes(mock_api):
    worker = ClusterWorker(db, mock_api)
    # Test should complete within 5 seconds
```

---

## Test Organization

### Arrange-Act-Assert Pattern

```python
def test_example(test_db):
    # Arrange - Set up test data
    photo_id = test_db.add_photo('/test.jpg', 'hash')
    embedding = np.random.randn(512).astype(np.float32)

    # Act - Perform operation
    face_id = test_db.add_face(photo_id, embedding, bbox)

    # Assert - Verify results
    assert face_id > 0
    retrieved = test_db.get_face_embedding(face_id)
    assert retrieved is not None
```

### Testing Classes

Group related tests:

```python
class TestPhotoOperations:
    """All photo-related database operations"""

    def test_add_photo(self, test_db):
        pass

    def test_remove_photo(self, test_db):
        pass

    def test_update_photo_status(self, test_db):
        pass
```

---

## Markers

### Available Markers

```python
@pytest.mark.slow
def test_large_dataset():
    """Marks test as slow (skip in CI)"""
    pass

@pytest.mark.integration
def test_full_workflow():
    """Marks test as integration test"""
    pass

@pytest.mark.database
def test_db_operation():
    """Marks test as database-dependent"""
    pass
```

### Run Tests by Marker

```bash
# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"

# Run database tests only
pytest -m database
```

---

## Debugging Tests

### Run with Print Statements

```bash
pytest -s  # Don't capture stdout
```

### Run with Debugger

```python
def test_something():
    import pdb; pdb.set_trace()
    # Test code
```

### Run with PyCharm/VSCode

Both IDEs support pytest natively. Configure test runner in IDE settings.

---

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.13'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-mock pytest-timeout
      - name: Run tests
        run: pytest --cov=app --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

---

## Best Practices

### DO:
- Write tests before optimizing
- Test edge cases and error conditions
- Use descriptive test names
- Keep tests independent
- Mock external dependencies
- Test one thing per test
- Clean up resources (fixtures handle this)

### DON'T:
- Test implementation details
- Share state between tests
- Use hardcoded paths (use temp_dir)
- Skip cleanup
- Write tests that depend on test order
- Test third-party libraries

---

## Troubleshooting

### Tests Fail with Import Errors

```bash
# Ensure app directory is in path
export PYTHONPATH="${PYTHONPATH}:./app"
```

### Fixtures Not Found

Check `conftest.py` is in tests directory.

### Database Lock Errors

Ensure tests use `temp_dir` fixture for database location.

### Slow Tests

```bash
# Run with timeout to identify slow tests
pytest --durations=10
```

---

## Test Maintenance

### Adding New Tests

1. Create test file: `tests/test_newfeature.py`
2. Import modules: `from app.newfeature import FeatureClass`
3. Write test class: `class TestFeature:`
4. Add tests: `def test_specific_case(self):`
5. Run: `pytest tests/test_newfeature.py`

### Updating Tests After Changes

When modifying code:
1. Run affected tests: `pytest tests/test_module.py`
2. Update test expectations if behavior changed intentionally
3. Add new tests for new functionality
4. Ensure coverage doesn't decrease

### Refactoring Tests

Use shared fixtures for common setup:

```python
# conftest.py
@pytest.fixture
def common_setup(test_db):
    # Setup code used by many tests
    yield prepared_data
```

---

## Performance Testing

### Benchmark Example

```python
def test_performance(benchmark, test_db):
    def operation():
        test_db.get_all_embeddings()

    result = benchmark(operation)
```

### Load Testing

```python
@pytest.mark.slow
def test_large_scale(test_db):
    # Create 10,000 faces
    for i in range(10000):
        test_db.add_face(...)

    # Measure query time
    import time
    start = time.time()
    test_db.get_all_embeddings()
    duration = time.time() - start

    assert duration < 5.0  # Should complete in <5s
```

---

## Examples

### Example: Testing Database Workflow

```python
def test_complete_workflow(test_db, sample_embeddings):
    """Test: add photo → add faces → cluster → tag → query"""

    # Add photo
    photo_id = test_db.add_photo('/test/photo.jpg', 'hash')

    # Add 3 faces
    face_ids = []
    for emb in sample_embeddings[:3]:
        face_id = test_db.add_face(photo_id, emb, {'x':0,'y':0,'w':100,'h':100})
        face_ids.append(face_id)

    # Create clustering
    clustering_id = test_db.create_clustering(threshold=50)

    # Assign to persons
    test_db.save_cluster_assignments(
        clustering_id, face_ids, [1,1,2], [0.95,0.93,0.90]
    )

    # Tag faces
    test_db.tag_faces(face_ids[:2], "Alice")

    # Query
    persons = test_db.get_persons_in_clustering(clustering_id)
    assert len(persons) == 2
```

### Example: Testing Error Handling

```python
def test_handles_missing_file(cache, temp_dir):
    """Test thumbnail cache handles missing files gracefully"""
    result = cache.create_thumbnail_with_cache(
        face_id=1,
        image_path='/nonexistent/file.jpg',
        size=180,
        bbox=None
    )

    assert result is None or result == ''
```

---

## Summary

- **Total Test Files**: 7
- **Test Categories**: Unit, Component, Integration
- **Coverage Target**: 80%+ overall
- **Run Time**: <2 minutes for full suite

Run tests frequently during development to catch regressions early!
