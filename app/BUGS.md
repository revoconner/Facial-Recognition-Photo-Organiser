# Known Bugs - Felicity PySide6 Migration

This file tracks known bugs discovered during and after the PySide6 migration from pywebview.

## Current Bugs

### 1. Size Slider Causes Photos to Disappear

**Severity**: Medium
**Component**: PhotoGridWidget
**File**: main_window.py:282-287

**Description**:
After lazy loading implementation, when the size slider is adjusted, photos disappear from the grid. The photos only reappear when the user either:
- Clicks on the person again in the people list, or
- Changes the view mode dropdown (zoom to faces / show entire photo)

**Expected Behavior**:
Photos should remain visible and resize smoothly when the slider is adjusted.

**Current Behavior**:
- Photos disappear from grid when slider is moved
- Grid appears empty
- Size setting is correctly applied (verified to work)
- Photos reappear only after triggering a reload action

**Root Cause**:
The `set_grid_size()` method in PhotoGridWidget calls `render_initial_batch()` which clears and reloads the entire grid. This reload operation may be failing or not properly repopulating the grid.

**Affected Code**:
```python
def set_grid_size(self, size):
    """Update grid thumbnail size"""
    self.grid_size = size
    # Reload with new size
    if self.photos:
        self.render_initial_batch()
```

**Reproduction Steps**:
1. Select any person from the people list
2. Wait for photos to load
3. Adjust the size slider
4. Observe photos disappear

---

### 2. Circle Thumbnails Don't Show Faces Properly

**Severity**: Low
**Component**: PersonListItem
**File**: main_window.py:118-150

**Description**:
The circular thumbnail photos displayed next to each person's name in the people list don't properly center on faces. Instead, they show arbitrary cropped portions of the photos.

**Expected Behavior**:
- Thumbnails should be centered on the person's face
- Should use the face bounding box to crop appropriately
- Should zoom to show the face prominently

**Current Behavior**:
- Thumbnails show random portions of photos
- Faces may be partially cut off or not visible at all
- No intelligent cropping based on face location

**Possible Solution**:
The thumbnail generation should:
1. Use the face bounding box coordinates
2. Add padding around the face
3. Center the crop on the face region
4. Scale appropriately for the 60x60 circular display

**Affected Code**:
```python
def set_thumbnail(self, base64_data):
    # Current implementation doesn't use face bbox
    scaled_pixmap = pixmap.scaled(60, 60, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    # Just centers the scaled image without considering face location
```

---

### 3. Named People's Faces Appearing in Wrong Person Clusters

**Severity**: High
**Component**: Face Clustering / Database
**File**: N/A (backend clustering logic)

**Description**:
Random faces that belong to named/identified people are incorrectly appearing in other people's clusters.

**Expected Behavior**:
- Once a person is named, all their faces should remain in that person's cluster
- Faces should not leak between different named persons
- Recalibration should preserve manual tag assignments

**Current Behavior**:
- Faces of identified Person A appear in Person B's photo gallery
- This suggests clustering algorithm is not respecting manual tags
- Or tag preservation during recalibration is failing

**Impact**:
- **Critical for user trust** - users expect named people to stay correctly organized
- Undermines the core value proposition of the application
- May indicate issues with:
  - Manual tag persistence (`is_manual` flag not being respected)
  - Tag restoration after recalibration
  - Clustering algorithm overriding manual assignments

**Possible Root Causes**:
1. **Recalibration Issue**: ClusterWorker may not be properly restoring manual tags
2. **Database Issue**: face_tags table manual assignments not being queried correctly
3. **UI Issue**: Displaying wrong clustering_id or person_id mapping
4. **API Issue**: get_photos() returning incorrect face assignments

**Investigation Needed**:
- Check if manual tags are being properly set with `is_manual=1`
- Verify ClusterWorker restoration logic
- Confirm API queries are using correct clustering_id
- Test tag persistence across recalibration cycles

**Related Code**:
- workers.py: ClusterWorker tag restoration
- database.py: face_tags table operations
- api_qt.py: get_photos() query logic

---

## Testing Notes

All bugs should be tested with:
- Small dataset (~100 photos, ~10 people)
- Medium dataset (~1,000 photos, ~50 people)
- Large dataset (~10,000+ photos, ~100+ people)

Test after:
- Fresh scan
- Recalibration with different thresholds
- Manual tagging operations
- Hide/unhide operations

---

## Priority

1. **Bug #3** - High priority (core functionality)
2. **Bug #1** - Medium priority (usability)
3. **Bug #2** - Low priority (cosmetic)
