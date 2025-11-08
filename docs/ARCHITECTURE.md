# Facial Recognition Photo Organizer - Architecture Documentation

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Backend Components](#backend-components)
4. [Frontend Components](#frontend-components)
5. [Data Flow](#data-flow)
6. [Performance Analysis](#performance-analysis)
7. [Optimization Recommendations](#optimization-recommendations)

---

## Executive Summary

The **Facial Recognition Photo Organizer** is a sophisticated offline desktop application that automatically groups photos by facial recognition using:

- **InsightFace** (buffalo_l model) - 99.8% accuracy face recognition
- **PyTorch** - GPU-accelerated deep learning
- **SQLite + LMDB** - Efficient dual-database architecture
- **PyWebView** - Modern web-based UI in a desktop wrapper
- **Chinese Whispers** - Density-based clustering algorithm

### Key Statistics
- **Handles**: 100,000+ photos efficiently
- **Scanning**: ~0.05-0.2s per image (GPU), 2-4 hours for 90k photos
- **Clustering**: 2-10 min on GPU, 30-60 min on CPU for 100k faces
- **Memory**: ~2.7GB for typical large library (90k photos)
- **Storage**: SQLite (100MB) + LMDB (200MB) + Thumbnails (1.8GB)

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Web UI)                         │
│  ┌──────────────┬──────────────┬──────────────────────────┐ │
│  │  ui.html     │ ui_js_script │     style.css            │ │
│  │  (Structure) │  (Logic)     │     (Dark theme)         │ │
│  └──────────────┴──────────────┴──────────────────────────┘ │
└────────────────┬───────────────────────────────────────────┘
                 │ PyWebView Bridge (JS ↔ Python)
┌────────────────┴───────────────────────────────────────────┐
│                    BACKEND (Python)                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              API Layer (api.py)                       │  │
│  │  - User interactions                                 │  │
│  │  - Settings management                               │  │
│  │  - Thumbnail generation                              │  │
│  └───────┬───────────────────────────────────────────────┘  │
│  ┌───────┴──────────────────────────────────────────────┐   │
│  │        Worker Threads (workers.py)                   │   │
│  │  - ScanWorker: Photo scanning & face detection      │   │
│  │  - ClusterWorker: Face clustering                   │   │
│  └───────┬──────────────────────────────────────────────┘   │
│  ┌───────┴────────────────────────────────────────────────┐ │
│  │        Database Layer (database.py)                    │ │
│  │  - SQLite: Metadata, relationships, clustering       │ │
│  │  - LMDB: Face embeddings (high-performance)          │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Face Recognition | InsightFace (buffalo_l) | Detect & embed faces with 99.8% accuracy |
| Deep Learning | PyTorch (CUDA/CPU) | GPU acceleration for embeddings |
| Metadata Storage | SQLite3 (WAL mode) | Photos, faces, clusters, tags |
| Embedding Storage | LMDB (10GB map) | 512-dim vectors, memory-mapped |
| UI Framework | PyWebView | Desktop wrapper for HTML/CSS/JS |
| Image Processing | Pillow + OpenCV | Load, crop, resize, color conversion |
| Clustering | Custom Chinese Whispers | Density-based, no K needed |
| System Integration | pystray | System tray support |

---

## Backend Components

### 1. Entry Point: `face_recognition.py` (62 lines)

**Purpose**: Bootstrap and initialize the application

**Key Responsibilities**:
```python
1. Detect GPU (PyTorch CUDA check)
2. Load settings from AppData
3. Initialize API layer
4. Create PyWebView window
5. Start event loop
```

**Performance**: One-time initialization, ~5-10s on first run

---

### 2. API Layer: `api.py` (886 lines)

**Purpose**: Bridge between frontend JavaScript and backend Python

#### Core Methods

**People Management**:
```python
get_people() → List[dict]
  - Retrieves all persons from active clustering
  - Filters: hidden, unnamed, minimum photos
  - Returns: id, name, photo_count, thumbnail (base64)

rename_person(clustering_id, person_id, new_name)
  - Tags all faces in person with new name
  - Handles name conflicts with suggestions

hide_person() / unhide_person()
  - Visibility control
```

**Photo Operations**:
```python
get_photos(clustering_id, person_id, page, page_size)
  - Paginated photo retrieval (100 per page)
  - Returns: thumbnails, bounding boxes, face tags

get_full_size_preview(image_path)
  - Full-resolution image for lightbox

create_thumbnail(image_path, size, bbox, face_id)
  - On-demand thumbnail generation with caching
```

**Worker Management**:
```python
start_scanning()
  - Spawns ScanWorker thread
  - Non-blocking background operation

start_clustering()
  - Spawns ClusterWorker thread
  - Triggered after scanning completes
```

**Settings**:
```python
get/set_threshold() → int (%)
get/set_include_folders() → List[str]
get/set_exclude_folders() → List[str]
get/set_wildcard_exclusions() → str
```

#### Key Design Patterns

**Name Conflict Resolution**:
```python
# If "John" exists, suggests "John 2", "John 3", etc.
check_name_conflict(clustering_id, person_id, new_name)
  → {'has_conflict': bool, 'suggested_name': str}
```

**Status Updates** (Python → JavaScript):
```python
# Real-time UI feedback via evaluate_js()
update_status("Scanning photo 500/1000")
update_progress(500, 1000)  # Updates progress bar
scan_complete()  # Triggers UI refresh
```

---

### 3. Database Layer: `database.py` (800+ lines)

**Purpose**: Persistent storage with optimized access patterns

#### Dual-Database Architecture

**SQLite** (`metadata.db`):
```sql
-- Core tables
photos              (file_path UNIQUE, hash, scan_status)
faces               (photo_id, bbox_x, bbox_y, bbox_w, bbox_h)
clusterings         (threshold, created_at, is_active)
cluster_assignments (face_id, clustering_id, person_id, confidence)
face_tags           (face_id, tag_name, is_manual)
hidden_persons      (clustering_id, person_id)
hidden_photos       (face_id)

-- 11 indexes for optimized queries
```

**LMDB** (`encodings.lmdb`):
```python
# Key-value store for face embeddings
Key: face_id (int)
Value: embedding (512-dim float32 array, pickled)

# Configuration
map_size: 10GB (pre-allocated)
readahead: True (sequential read optimization)
sync: False (async writes for speed)
```

**Why LMDB for embeddings?**
- Memory-mapped I/O (faster than SQLite BLOB)
- Scales to 100k+ faces
- Better concurrency for read-heavy workloads

#### SQLite Optimizations

```python
PRAGMA journal_mode = WAL;        # Write-Ahead Logging
PRAGMA synchronous = NORMAL;      # Async writes (safe)
PRAGMA cache_size = -64000;       # 64MB in-memory cache
PRAGMA temp_store = MEMORY;       # RAM temp tables
PRAGMA mmap_size = 268435456;     # 256MB memory-mapped
PRAGMA page_size = 4096;          # SSD-optimal
```

#### Critical Methods

**Photo Management**:
```python
add_photo(file_path, file_hash) → photo_id
get_all_scanned_paths() → Set[str]
remove_deleted_photos(existing_paths) → int
update_photo_status(photo_id, 'completed')
```

**Face Operations**:
```python
add_face(photo_id, embedding, bbox) → face_id
  # Stores bbox in SQLite, embedding in LMDB

get_face_embedding(face_id) → np.ndarray
  # Retrieves from LMDB, unpickles

get_all_embeddings() → (face_ids, embeddings_matrix)
  # Batch load for clustering (efficient)
```

**Clustering**:
```python
create_clustering(threshold) → clustering_id
save_cluster_assignments(clustering_id, assignments)
get_active_clustering() → dict  # Cached 5 seconds
```

**Tagging**:
```python
tag_faces(face_ids, tag_name, is_manual=False)
  # Batch insert with chunking (500 at a time)
  # Handles SQLite parameter limit (~999)

get_face_tags(face_ids) → Dict[face_id → tag_name]
```

---

### 4. Worker Threads: `workers.py` (600+ lines)

**Purpose**: Background processing (non-blocking UI)

#### A. ScanWorker Thread

**Flow**:
```
1. Initialize InsightFace model (buffalo_l)
2. Discover photos (recursive walk + filters)
3. Clean up deleted photos from database
4. Process in batches (25 photos at a time):
   - Load image (PIL + EXIF transpose)
   - Convert RGB → BGR (OpenCV format)
   - Run face detection (InsightFace)
   - Extract embeddings (512-dim, L2 normalized)
   - Extract bounding boxes
5. Commit batch to database
6. Update progress bar
7. Trigger clustering when done
```

**Key Features**:
```python
# Batch processing
batch_size = 25  # Memory vs. commit frequency

# Dynamic throttling
if dynamic_resources and window_backgrounded:
    time.sleep(0.5)  # Yield CPU

# Image loading pipeline
PIL.Image.open(path)
→ ImageOps.exif_transpose()  # Auto-rotate
→ np.array(RGB)
→ cv2.cvtColor(RGB2BGR)  # For InsightFace
```

**Performance**:
- Model load: ~5-10s (first time)
- Per image: 0.05-0.2s (depends on face count)
- 90k photos: 2-4 hours CPU, 30-60 min GPU

#### B. ClusterWorker Thread

**Flow**:
```
1. Load all embeddings from LMDB
2. Preserve hidden persons (track face_ids)
3. Chinese Whispers clustering:
   - Normalize embeddings (L2)
   - Build similarity graph (PyTorch batch matmul)
   - Filter edges < threshold
   - Iterative label propagation (max 25 iterations)
   - Validate clusters (centroid filtering)
4. Merge clusters by existing tags
5. Create new clustering in database
6. Auto-tag untagged faces
7. Restore hidden persons
8. Trigger UI refresh
```

**Chinese Whispers Algorithm**:
```python
# Why Chinese Whispers?
# - Density-based (not k-means)
# - No need to specify K (number of people)
# - Handles outliers naturally
# - Scales well with GPU

1. Initialize: each face = own cluster
2. For iteration in range(25):
   3. For each node (shuffled):
      4. neighbors = get_neighbors_above_threshold()
      5. label_weights = sum similarity by label
      6. node.label = label_with_max_weight
   7. If converged (<0.1% changes): break
8. Filter: remove low-confidence faces from clusters
```

**GPU Acceleration**:
```python
# PyTorch batch similarity
embeddings_tensor = torch.tensor(embeddings).to('cuda')
similarities = torch.mm(batch, embeddings_tensor.T)
# 100x faster than row-by-row on GPU
```

**Performance**:
- Graph building: O(n² / batch_size) with GPU
- Clustering: O(iterations × n × avg_neighbors)
- 100k faces: 2-10 min GPU, 30-60 min CPU

---

### 5. Utilities: `utils.py` (57 lines)

```python
get_resource_path(relative_path)
  # Returns bundled resource path (PyInstaller compatible)

get_appdata_path()
  # Returns: %APPDATA%/facial_recognition/face_data/

get_insightface_root()
  # Model directory (bundled or ~/.insightface)

create_tray_icon()
  # Loads icon.ico or generates procedural icon
```

---

### 6. Settings: `settings.py` (65 lines)

**Purpose**: JSON-based configuration with defaults

```python
Settings class:
  file: %APPDATA%/facial_recognition/settings.json

  get(key, default)
  set(key, value)  # Saves immediately
```

**Default Settings**:
```json
{
  "threshold": 50,
  "close_to_tray": true,
  "dynamic_resources": true,
  "show_unmatched": false,
  "grid_size": 180,
  "window_width": 1200,
  "window_height": 800,
  "include_folders": [],
  "exclude_folders": [],
  "wildcard_exclusions": "",
  "view_mode": "entire_photo",
  "scan_frequency": "restart_1_day"
}
```

---

### 7. Thumbnail System: `thumbnail_cache.py` (138 lines)

**Purpose**: Cache thumbnails to disk

**Cache Strategy**:
```python
# Cache key
face_{face_id}_{mode}_{size}.jpg
# Example: face_123_zoom_180.jpg

# Storage
%APPDATA%/facial_recognition/thumbnail_cache/

# Invalidation
- Source image modified (mtime check)
- Manual cache clear
- Different size/mode (new cache key)
```

**Generation Pipeline**:
```python
1. Check cache (file exists + mtime match)
2. If miss:
   - PIL.Image.open() + EXIF transpose
   - Crop if bbox provided (face region + 20px padding)
   - Resize to (size, size) with LANCZOS
   - Convert to RGB
   - Compress JPEG (quality=85)
3. Save to cache
4. Return base64 data URL
```

**Memory**: No in-memory cache, only disk

---

## Frontend Components

### 1. HTML Structure: `ui.html` (400+ lines)

**Layout**:
```
title-bar (32px, draggable)
├─ Window controls (minimize, maximize, close)

app-container
├─ main-content
│  ├─ sidebar (240px)
│  │  ├─ People list
│  │  └─ Filter/sort buttons
│  └─ content-area
│     ├─ Header (name + controls)
│     └─ Photo grid (paginated)
├─ bottom-bar
│  ├─ Settings button
│  ├─ Progress bar
│  └─ Status bar (PyTorch info, GPU, Help)
└─ Overlays (modals for settings, rename, etc.)
```

**Key Features**:
- Frameless window (custom title bar)
- Dark theme (AMOLED-friendly)
- Custom scrollbars
- SVG icons for buttons

---

### 2. JavaScript Logic: `ui_js_script.js` (2000+ lines)

**Global State**:
```javascript
let people = [];              // All persons
let currentPerson = null;     // Selected person
let currentPage = 1;          // Pagination
const PAGE_SIZE = 100;        // Photos per page
```

**Key Functions**:

**People List**:
```javascript
loadPeople()
  // Calls: pywebview.api.get_people()
  // Filters: hidden, unnamed, min photos
  // Renders: person cards with thumbnails

renderPeopleList()
  // Creates DOM elements
  // Adds click handlers
  // Shows context menus
```

**Photo Grid**:
```javascript
loadPhotosForPerson(person_id, page=1)
  // Calls: pywebview.api.get_photos(...)
  // Handles: pagination, infinite scroll
  // Displays: thumbnails with face overlays
```

**Rename Workflow**:
```javascript
showRenameDialog(person_id, currentName)
  ↓
checkNameConflict(new_name)
  ↓
[If conflict] → Show suggestion dialog
[Else] → proceedWithRename(new_name)
  ↓
loadPeople() + reloadCurrentPhotos()
```

**Lightbox**:
```javascript
showLightbox(photos, startIndex)
  // Full-size image viewer
  // Face overlay with tags
  // Keyboard navigation (←, →, Esc)
```

**Settings Panel**:
```
Three tabs:
1. General (threshold, toggles, filters)
2. Folders (include/exclude paths)
3. View Log (status messages)
```

---

### 3. Styling: `style.css` (600+ lines)

**Features**:
- Dark theme (#1a1a1a background)
- Smooth transitions (0.2s ease)
- Custom scrollbars
- Flexbox layouts
- CSS Grid for photo grid
- Hover effects

```css
.photo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}
```

---

## Data Flow

### Scan & Cluster Workflow

```
User clicks "Scan" or app auto-starts
  ↓
start_scanning()
  ↓
ScanWorker thread:
  1. Load InsightFace model
  2. Discover photos (recursive walk)
  3. Clean up deleted photos
  4. For each batch (25 photos):
     - Load image → detect faces → extract embeddings
     - Commit to database (SQLite + LMDB)
     - Update progress bar
  ↓
scan_complete()
  ↓
start_clustering()
  ↓
ClusterWorker thread:
  1. Load embeddings from LMDB
  2. Build similarity graph (PyTorch GPU)
  3. Chinese Whispers clustering
  4. Validate clusters (centroid filtering)
  5. Merge by tags
  6. Save to database
  7. Auto-tag faces
  ↓
cluster_complete()
  ↓
loadPeople() → UI updates
```

### User Interaction: Rename Person

```
User clicks rename → Modal appears
  ↓
User enters name → Press Enter
  ↓
checkNameConflict(new_name)
  ↓
API call: check_name_conflict()
  ↓
Database query: SELECT faces with tag = new_name
  ↓
[If conflict]
  Show suggestion: "John 2", "John 3", etc.
  User chooses → proceedWithRename()
[Else]
  proceedWithRename(new_name)
  ↓
API call: rename_person()
  ↓
Database: tag_faces(face_ids, new_name)
  ↓
UI update: loadPeople() + reloadCurrentPhotos()
```

---

## Performance Analysis

### Bottlenecks

| Component | Bottleneck | Speed | Mitigation |
|-----------|-----------|-------|-----------|
| **Face Detection** | InsightFace inference | 0.05-0.2s/image | GPU, batching |
| **Clustering** | Similarity matrix (O(n²)) | 2-10 min (100k faces) | PyTorch GPU, sparse graph |
| **Database** | Complex JOINs | 1-5ms/query | Indexing, caching |
| **Thumbnails** | Image decode + JPEG encode | 10-50ms | Disk caching |
| **UI Rendering** | DOM updates | Lag on 1000+ items | Pagination, virtual scroll |

### Memory Usage (90k photos)

| Component | Size | Notes |
|-----------|------|-------|
| LMDB Embeddings | 200MB | 90k × 512 × 4 bytes |
| SQLite Database | 100MB | Metadata + indexes |
| Thumbnail Cache | 1.8GB | 90k × 20KB JPEG |
| Python Process | 500MB | Model + app state |
| **Total** | **~2.7GB** | Typical large library |

### Scaling Limits

- **LMDB**: 10GB map (5M+ faces theoretical)
- **SQLite**: WAL mode, handles 1M+ rows efficiently
- **RAM**: 16GB recommended for smooth operation
- **Disk**: 2-3GB for cache + database

---

## Optimization Recommendations

### High Priority (Easy + High Impact)

#### 1. **Enable ThumbnailWorker** ⭐⭐⭐
**Problem**: Thumbnails generated on-demand (blocks UI)
**Solution**: Queue thumbnails for background generation
**Impact**: Faster UI load, smoother scrolling
**Effort**: Low (code exists, just enable)

#### 2. **Implement Virtual Scrolling** ⭐⭐⭐
**Problem**: 1000+ DOM nodes slow rendering
**Solution**: Render only visible items (~20) + buffer
**Impact**: 50x faster rendering, smooth scrolling
**Effort**: Medium (frontend refactor)

#### 3. **Precompute Person Stats** ⭐⭐⭐
**Problem**: `get_person_photo_count_fast()` uses expensive JOINs
**Solution**: Add `photo_count` column, update on clustering
**Impact**: 10x faster `get_people()` call
**Effort**: Low (database denormalization)

#### 4. **Cache Clustering Results** ⭐⭐
**Problem**: Re-clustering on startup even if no new photos
**Solution**: Serialize clustering to JSON, reuse if threshold unchanged
**Impact**: Skip 2-10 min clustering on restart
**Effort**: Low (JSON caching)

---

### Medium Priority (Moderate effort, good impact)

#### 5. **Incremental Clustering** ⭐⭐
**Problem**: Full re-clustering on every scan
**Solution**: Cluster only new faces + 1-hop neighbors, merge results
**Impact**: 50-70% faster re-clustering
**Effort**: High (complex algorithm)

#### 6. **Approximate Nearest Neighbors (FAISS/Annoy)** ⭐⭐
**Problem**: O(n²) similarity for 100k+ faces
**Solution**: Use FAISS index for O(n log n) search
**Impact**: 10-50x faster clustering for very large libraries
**Effort**: High (new dependency + integration)

#### 7. **Parallel Image Loading** ⭐
**Problem**: CPU idle while waiting for I/O
**Solution**: Load next batch while processing current
**Impact**: Better GPU utilization, 20-30% faster scanning
**Effort**: Medium (threading complexity)

---

### Lower Priority (High effort, niche impact)

#### 8. **WebP Thumbnails**
**Problem**: JPEG thumbnails ~20KB each
**Solution**: Use WebP (20-30% smaller)
**Impact**: 500MB savings on 90k photos
**Effort**: Medium (browser compatibility check)

#### 9. **Distributed Clustering**
**Problem**: Single machine limited by RAM/GPU
**Solution**: Split across multiple machines
**Impact**: Only useful for 500k+ faces
**Effort**: Very High (networking, coordination)

---

## Quick Reference

### File Structure
```
app/
├── face_recognition.py     # Entry point (62 lines)
├── api.py                  # API layer (886 lines)
├── database.py             # Database (800+ lines)
├── workers.py              # Scanning/clustering (600+ lines)
├── settings.py             # Settings (65 lines)
├── utils.py                # Utilities (57 lines)
├── thumbnail_cache.py      # Thumbnail cache (138 lines)
├── thumbnail_worker.py     # Background worker (unused)
├── ui.html                 # Frontend HTML (400+ lines)
├── ui_js_script.js         # Frontend JS (2000+ lines)
├── style.css               # Styling (600+ lines)
└── icon.ico                # App icon
```

### Key Algorithms

**Chinese Whispers Clustering**:
```
Input: Embeddings (n × 512), Threshold
1. Normalize embeddings
2. Build similarity graph (threshold filter)
3. Initialize: each node = own label
4. For 25 iterations:
   - For each node: assign to best-neighbor label
   - Count changes
   - If < 0.1% changed: break
5. Filter low-confidence faces
Output: face_id → person_id assignments
```

**Centroid Validation**:
```
For each cluster:
  1. Compute centroid (mean embedding)
  2. Calculate similarity to centroid for all faces
  3. Keep faces with similarity > threshold
  4. Move others to unmatched (person_id=0)
```

---

## Common Operations

### Adding New Features

**Backend**:
1. Add method to `api.py`
2. Expose via `pywebview.api`
3. Update `database.py` if needed

**Frontend**:
1. Add UI elements to `ui.html`
2. Add logic to `ui_js_script.js`
3. Call `pywebview.api.your_method()`
4. Style with `style.css`

### Database Queries

**Get person's photos**:
```sql
SELECT p.file_path, f.bbox_x, f.bbox_y, f.bbox_w, f.bbox_h
FROM photos p
JOIN faces f ON f.photo_id = p.id
JOIN cluster_assignments ca ON ca.face_id = f.id
WHERE ca.clustering_id = ? AND ca.person_id = ?
LIMIT ? OFFSET ?
```

**Get person count**:
```sql
SELECT COUNT(DISTINCT f.photo_id)
FROM faces f
JOIN cluster_assignments ca ON ca.face_id = f.id
WHERE ca.clustering_id = ? AND ca.person_id = ?
```

---

## Troubleshooting

### Performance Issues

**Slow scanning**:
- Check GPU availability: "CUDA available: True/False"
- Enable dynamic resources (Settings)
- Exclude unnecessary folders

**Slow clustering**:
- Lower threshold (fewer edges in graph)
- Use GPU (install PyTorch with CUDA)
- Clear old clusterings (database bloat)

**UI lag**:
- Enable pagination (default: 100 photos/page)
- Clear thumbnail cache (Settings)
- Reduce grid size (Settings)

### Memory Issues

**High RAM usage**:
- Close other applications
- Reduce batch size in `workers.py` (line 29)
- Clear thumbnail cache

**Disk space**:
- Clear thumbnail cache: ~1.8GB for 90k photos
- Check database size: %APPDATA%/facial_recognition/

---

## Conclusion

This architecture successfully balances:
- **Performance** (GPU acceleration, caching)
- **Privacy** (completely offline)
- **Usability** (simple UI, smart defaults)
- **Scalability** (handles 100k+ photos)

The dual-database design (SQLite + LMDB) is particularly elegant, separating structured metadata from high-dimensional embeddings for optimal access patterns.

For optimization efforts, focus on:
1. Virtual scrolling (frontend)
2. Precomputed stats (database)
3. Thumbnail worker (backend)
4. Incremental clustering (algorithm)
