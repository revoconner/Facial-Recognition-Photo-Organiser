"""Photo metadata capture for Felicity (F2).

Reads filesystem stats (os.stat) and EXIF tags (exifread) for a photo, with no face
detection. Returns two dicts:
  - hot: values for the indexed columns on the photos table (the facets we filter and
    sort on constantly).
  - eav: long-tail values for the photo_metadata table (advanced tags, hidden by default).

Missing values are simply absent from the dicts and stored as NULL - the app never
substitutes or infers a value it doesn't have.
"""

import os
import logging
from pathlib import Path
from datetime import datetime

import exifread

from logger import get_logger

log = get_logger("metadata")

# exifread emits "File format not recognized." (and similar) at WARNING for files
# without parseable EXIF - PNG/BMP/GIF/ICO etc. During a full-library backfill that
# would flood the console/log, so raise its threshold to ERROR.
logging.getLogger('exifread').setLevel(logging.ERROR)


def _parse_exif_datetime(value):
    """EXIF stores 'YYYY:MM:DD HH:MM:SS'. Return a unix-epoch float for easy SQL
    sorting/grouping, or None if absent/unparseable."""
    if not value:
        return None
    try:
        dt = datetime.strptime(str(value).strip(), "%Y:%m:%d %H:%M:%S")
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def read_photo_metadata(file_path, width=None, height=None):
    """Return (hot, eav) metadata dicts for file_path. width/height may be supplied by
    the caller (e.g. from the image already loaded for detection) to avoid a re-decode."""
    hot = {}
    eav = {}

    # Filesystem facets - always available, cheap.
    try:
        st = os.stat(file_path)
        hot['file_size'] = st.st_size
        hot['date_modified'] = st.st_mtime
        # st_birthtime is the real creation time; available on Windows in Python 3.12+.
        # Fall back to st_ctime where birthtime isn't present.
        hot['date_created'] = getattr(st, 'st_birthtime', None) or st.st_ctime
    except OSError as e:
        log.debug("stat failed for %s: %s", file_path, e)

    hot['file_ext'] = Path(file_path).suffix.lower().lstrip('.')

    if width:
        hot['width'] = width
    if height:
        hot['height'] = height

    # EXIF facets - may be absent (stripped by messaging apps, screenshots, etc.).
    # details=False skips makernotes/thumbnails, which we don't use and which slow the
    # read down considerably.
    tags = {}
    try:
        with open(file_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
    except Exception as e:
        log.debug("exifread failed for %s: %s", file_path, e)

    def tag(name):
        value = tags.get(name)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    date_taken = _parse_exif_datetime(tag('EXIF DateTimeOriginal') or tag('Image DateTime'))
    if date_taken is not None:
        hot['date_taken'] = date_taken

    make = tag('Image Make')
    if make:
        hot['camera_make'] = make
    model = tag('Image Model')
    if model:
        hot['camera_model'] = model

    if 'width' not in hot:
        w = tag('EXIF ExifImageWidth')
        if w and w.isdigit():
            hot['width'] = int(w)
    if 'height' not in hot:
        h = tag('EXIF ExifImageLength')
        if h and h.isdigit():
            hot['height'] = int(h)

    # Advanced tags -> long-tail EAV (hidden by default in the UI).
    iso = tag('EXIF ISOSpeedRatings')
    if iso:
        eav['iso'] = iso
    focal = tag('EXIF FocalLength')
    if focal:
        eav['focal_length'] = focal
    lens = tag('EXIF LensModel')
    if lens:
        eav['lens'] = lens

    return hot, eav
