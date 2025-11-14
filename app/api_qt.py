"""
Qt-based API Bridge
Adapts the existing API functionality to work with PySide6 signals
"""
import os
import sys
import time
from pathlib import Path
from typing import Optional, List
from io import BytesIO
from PIL import Image, ImageOps
import torch
from PySide6.QtCore import QObject, Signal

from utils import get_appdata_path
from database import FaceDatabase
from thumbnail_cache import ThumbnailCache
from settings import Settings
from workers import ScanWorker, ClusterWorker


class APIQt(QObject):
    """Qt-based API using signals instead of evaluate_js"""

    # Signals for UI updates
    status_updated = Signal(str)
    progress_updated = Signal(int, int, float)
    progress_hidden = Signal()
    people_loaded = Signal()
    photos_reloaded = Signal()

    def __init__(self, settings: Settings):
        super().__init__()
        self._settings = settings
        self._threshold = settings.get('threshold', 50)

        db_path = get_appdata_path()
        print(f"Database location: {db_path}")

        self._db = FaceDatabase(str(db_path))
        self._window = None
        self._tray = None
        self._scan_worker = None
        self._cluster_worker = None
        self._quit_flag = False
        self._dynamic_resources = settings.get('dynamic_resources', True)
        self._window_foreground = True

        cache_path = db_path.parent / "thumbnail_cache"
        self._thumbnail_cache = ThumbnailCache(str(cache_path))
        print(f"Thumbnail cache location: {cache_path}")

    def set_window(self, window):
        """Set reference to main window"""
        self._window = window

        # Connect signals to window methods
        self.status_updated.connect(window.update_status)
        self.progress_updated.connect(window.update_progress)
        self.progress_hidden.connect(window.hide_progress)
        self.people_loaded.connect(window.load_people)

    def set_tray(self, tray):
        """Set reference to system tray"""
        self._tray = tray

    def update_status(self, message: str):
        """Update status message"""
        self.status_updated.emit(message)

    def update_progress(self, current: int, total: int):
        """Update progress bar"""
        percent = (current / total) * 100 if total > 0 else 0
        self.progress_updated.emit(current, total, percent)

    def get_cache_stats(self):
        return self._thumbnail_cache.get_cache_size()

    def clear_thumbnail_cache(self):
        stats = self._thumbnail_cache.clear_cache()
        self.people_loaded.emit()
        return stats

    def scan_complete(self):
        total_faces = self._db.get_total_faces()
        total_photos = self._db.get_total_photos()
        pending_count = self._db.get_photos_needing_scan()

        self.update_status(f"Scan complete: {total_faces} faces in {total_photos} photos")

        if pending_count > 0:
            self.update_status(f"Warning: {pending_count} photos had errors and were skipped")

        self._settings.set('last_scan_time', time.time())

        active_clustering = self._db.get_active_clustering()
        has_existing_clustering = active_clustering is not None
        new_photos_found = getattr(self, '_new_photos_found', False)
        photos_deleted = getattr(self, '_photos_deleted', False)

        should_recalibrate = new_photos_found or photos_deleted or not has_existing_clustering

        if should_recalibrate:
            self.update_status("Database updated successfully")
            self.update_status("Starting automatic recalibration...")
            self.start_clustering()
        else:
            self.update_status("No new photos found, loading existing clustering")
            self.update_status(f"Using threshold: {active_clustering['threshold']}%")
            self.cluster_complete()

    def set_new_photos_found(self, found):
        self._new_photos_found = found

    def set_photos_deleted(self, deleted):
        self._photos_deleted = deleted

    def cluster_complete(self):
        self.progress_hidden.emit()
        self.people_loaded.emit()

    def get_system_info(self):
        GPU_AVAILABLE = torch.cuda.is_available()
        return {
            'pytorch_version': torch.__version__,
            'gpu_available': GPU_AVAILABLE,
            'cuda_version': torch.version.cuda if GPU_AVAILABLE else 'N/A',
            'gpu_name': torch.cuda.get_device_name(0) if GPU_AVAILABLE else 'N/A',
            'total_faces': self._db.get_total_faces()
        }

    def should_scan_on_startup(self) -> bool:
        scan_frequency = self._settings.get('scan_frequency', 'restart_1_day')

        if scan_frequency == 'manual':
            return False

        if scan_frequency == 'every_restart':
            return True

        last_scan_time = self._settings.get('last_scan_time')

        if last_scan_time is None:
            return True

        current_time = time.time()
        time_since_scan = current_time - last_scan_time

        if scan_frequency == 'restart_1_day':
            return time_since_scan >= 86400
        elif scan_frequency == 'restart_1_week':
            return time_since_scan >= 604800

        return True

    def start_scanning(self):
        if self._scan_worker is None or not self._scan_worker.is_alive():
            self._scan_worker = ScanWorker(self._db, self)
            self._scan_worker.start()

    def start_clustering(self):
        if self._cluster_worker is None or not self._cluster_worker.is_alive():
            threshold = self.get_threshold()
            self._cluster_worker = ClusterWorker(self._db, threshold, self)
            self._cluster_worker.start()

    def get_threshold(self):
        return self._threshold

    def set_threshold(self, value):
        self._threshold = value
        self._settings.set('threshold', value)

    def recalibrate(self, threshold):
        self._threshold = threshold
        self._settings.set('threshold', threshold)
        self.start_clustering()

    def get_people(self):
        clustering = self._db.get_active_clustering()
        if not clustering:
            return []

        clustering_id = clustering['clustering_id']
        persons = self._db.get_persons_in_clustering(clustering_id)
        hidden_persons = self._db.get_hidden_persons(clustering_id)
        show_hidden = self._settings.get('show_hidden', False)
        hide_unnamed = self._settings.get('hide_unnamed_persons', False)

        result = []

        for person in persons:
            person_id = person['person_id']
            is_hidden = person_id in hidden_persons

            if is_hidden and not show_hidden:
                continue

            name = self._db.get_person_name_fast(clustering_id, person_id)

            if hide_unnamed and name.startswith("Person "):
                continue

            if is_hidden:
                name += " (hidden)"

            tagged_count = self._db.get_person_tagged_count_fast(clustering_id, person_id)
            face_count = self._db.get_person_photo_count_fast(clustering_id, person_id)

            primary_face_id = None
            if not name.startswith("Person ") and name != "Unmatched Faces":
                clean_name = name.replace(" (hidden)", "")
                primary_face_id = self._db.get_primary_photo_for_tag(clean_name)

            if not primary_face_id and face_count > 0:
                first_photos, _ = self._db.get_photos_by_person_paginated(clustering_id, person_id, limit=1, offset=0)
                if first_photos:
                    primary_face_id = first_photos[0]['face_id']

            thumbnail = None
            if primary_face_id:
                face_data = self._db.get_face_data(primary_face_id)
                if face_data:
                    bbox = [face_data['bbox_x1'], face_data['bbox_y1'],
                        face_data['bbox_x2'], face_data['bbox_y2']]
                    thumbnail = self.create_thumbnail(face_data['file_path'], size=80, bbox=bbox, face_id=primary_face_id)

            result.append({
                'id': person_id,
                'name': name,
                'count': face_count,
                'tagged_count': tagged_count,
                'clustering_id': clustering_id,
                'is_hidden': is_hidden,
                'thumbnail': thumbnail
            })

        return result

    def transfer_face_to_person(self, clustering_id, face_id, target_name):
        try:
            self._db.transfer_face_to_person(clustering_id, face_id, target_name)
            self.people_loaded.emit()
            self.photos_reloaded.emit()
            return {'success': True, 'message': f'Face transferred to {target_name}'}
        except Exception as e:
            print(f"Error in transfer_face_to_person: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': str(e)}

    def remove_face_to_unmatched(self, clustering_id, face_id):
        try:
            self._db.move_face_to_unmatched(clustering_id, face_id)
            self.people_loaded.emit()
            self.photos_reloaded.emit()
            return {'success': True, 'message': 'Face moved to Unmatched Faces'}
        except Exception as e:
            print(f"Error in remove_face_to_unmatched: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': str(e)}

    def get_hide_unnamed_persons(self):
        return self._settings.get('hide_unnamed_persons', False)

    def set_hide_unnamed_persons(self, enabled):
        self._settings.set('hide_unnamed_persons', enabled)

    def hide_person(self, clustering_id, person_id):
        self._db.hide_person(clustering_id, person_id)
        self.people_loaded.emit()

    def unhide_person(self, clustering_id, person_id):
        self._db.unhide_person(clustering_id, person_id)
        self.people_loaded.emit()

    def hide_photo(self, face_id):
        self._db.hide_photo(face_id)
        self.photos_reloaded.emit()
        return {'success': True}

    def unhide_photo(self, face_id):
        self._db.unhide_photo(face_id)
        self.photos_reloaded.emit()
        return {'success': True}

    def check_name_conflict(self, clustering_id, person_id, new_name):
        if not new_name or not new_name.strip():
            return {'has_conflict': False}

        new_name = new_name.strip()

        current_name = self._db.get_person_name_fast(clustering_id, person_id)

        if new_name == current_name or new_name == current_name.replace(" (hidden)", ""):
            return {'has_conflict': False}

        cursor = self._db.conn.cursor()
        cursor.execute('''
            SELECT COUNT(DISTINCT ca.person_id)
            FROM cluster_assignments ca
            JOIN face_tags ft ON ca.face_id = ft.face_id
            WHERE ca.clustering_id = ? AND ft.tag_name = ? AND ca.person_id != ?
        ''', (clustering_id, new_name, person_id))

        count = cursor.fetchone()[0]

        if count > 0:
            base_name = new_name
            next_num = 2

            while True:
                test_name = f"{base_name} {next_num}"
                cursor.execute('''
                    SELECT COUNT(DISTINCT ca.person_id)
                    FROM cluster_assignments ca
                    JOIN face_tags ft ON ca.face_id = ft.face_id
                    WHERE ca.clustering_id = ? AND ft.tag_name = ?
                ''', (clustering_id, test_name))

                if cursor.fetchone()[0] == 0:
                    suggested_name = test_name
                    break

                next_num += 1
                if next_num > 100:
                    suggested_name = f"{base_name} {next_num}"
                    break

            return {
                'has_conflict': True,
                'existing_name': new_name,
                'suggested_name': suggested_name
            }

        return {'has_conflict': False}

    def rename_person(self, clustering_id, person_id, new_name):
        print(f"=== RENAME PERSON CALLED ===")
        print(f"clustering_id: {clustering_id}")
        print(f"person_id: {person_id}")
        print(f"new_name: {new_name}")

        if not new_name or not new_name.strip():
            print("ERROR: Name is empty")
            return {'success': False, 'message': 'Name cannot be empty'}

        new_name = new_name.strip()
        print(f"Trimmed name: {new_name}")

        face_ids = self._db.get_face_ids_for_person(clustering_id, person_id, limit=10000)
        print(f"Found {len(face_ids)} face IDs to tag")

        if not face_ids:
            print("ERROR: No faces found")
            return {'success': False, 'message': 'No faces found for this person'}

        print(f"Calling tag_faces with name: {new_name}")
        self._db.tag_faces(face_ids, new_name, is_manual=True)
        print("tag_faces completed")

        self.people_loaded.emit()

        print(f"Returning success with {len(face_ids)} faces tagged")
        return {'success': True, 'faces_tagged': len(face_ids)}

    def untag_person(self, clustering_id, person_id):
        face_ids = self._db.get_face_ids_for_person(clustering_id, person_id, limit=10000)

        if not face_ids:
            return {'success': False, 'message': 'No faces found for this person'}

        self._db.untag_faces(face_ids)
        self.people_loaded.emit()

        return {'success': True, 'faces_untagged': len(face_ids)}

    def set_primary_photo(self, tag_name, face_id):
        try:
            if not tag_name or tag_name.startswith('Person ') or tag_name == 'Unmatched Faces':
                return {'success': False, 'message': 'Please name this person before setting a primary photo'}

            self._db.set_primary_photo_for_tag(tag_name, face_id)
            self.people_loaded.emit()
            return {'success': True, 'message': 'Primary photo set successfully'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def get_photos(self, clustering_id, person_id, page=1, page_size=100):
        offset = (page - 1) * page_size

        photo_data, total_count = self._db.get_photos_by_person_paginated(
            clustering_id, person_id, limit=page_size, offset=offset
        )

        hidden_photos = self._db.get_hidden_photos()
        show_hidden_photos = self._settings.get('show_hidden_photos', False)
        photos = []

        view_mode = self._settings.get('view_mode', 'entire_photo')
        grid_size = self._settings.get('grid_size', 180)

        for data in photo_data:
            face_id = data['face_id']
            is_hidden = face_id in hidden_photos

            if is_hidden and not show_hidden_photos:
                continue

            path = data['file_path']
            bbox = None

            if view_mode == 'zoom_to_faces':
                bbox = [data['bbox_x1'], data['bbox_y1'], data['bbox_x2'], data['bbox_y2']]

            thumbnail = self.create_thumbnail(path, size=grid_size, bbox=bbox, face_id=face_id)
            if thumbnail:
                photos.append({
                    'path': path,
                    'thumbnail': thumbnail,
                    'name': os.path.basename(path),
                    'face_id': face_id,
                    'is_hidden': is_hidden
                })

        return {
            'photos': photos,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'has_more': offset + len(photos) < total_count
        }

    def get_full_size_preview(self, image_path: str) -> Optional[str]:
        try:
            img = Image.open(image_path)
            img = ImageOps.exif_transpose(img)

            max_size = 1200
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            img_rgb = img.convert('RGB')

            buffer = BytesIO()
            img_rgb.save(buffer, format='JPEG', quality=90)
            import base64
            img_base64 = base64.b64encode(buffer.getvalue()).decode()

            return f"data:image/jpeg;base64,{img_base64}"
        except Exception as e:
            print(f"Error creating full size preview: {e}")
            return None

    def create_thumbnail(self, image_path: str, size: int = 150, bbox: Optional[List[float]] = None, face_id: Optional[int] = None) -> Optional[str]:
        if face_id:
            return self._thumbnail_cache.create_thumbnail_with_cache(face_id, image_path, size, bbox)

        try:
            img = Image.open(image_path)
            img = ImageOps.exif_transpose(img)

            if bbox is not None:
                x1, y1, x2, y2 = bbox
                padding = 20

                x1 = max(0, x1 - padding)
                y1 = max(0, y1 - padding)
                x2 = min(img.width, x2 + padding)
                y2 = min(img.height, y2 + padding)

                img = img.crop((int(x1), int(y1), int(x2), int(y2)))

            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            img_rgb = img.convert('RGB')

            buffer = BytesIO()
            img_rgb.save(buffer, format='JPEG', quality=85)
            import base64
            img_base64 = base64.b64encode(buffer.getvalue()).decode()

            return f"data:image/jpeg;base64,{img_base64}"
        except Exception as e:
            return None

    def open_photo(self, path):
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as e:
            print(f"Error opening photo: {e}")

    def check_initial_state(self):
        total_faces = self._db.get_total_faces()
        total_photos = self._db.get_total_photos()

        self.update_status(f"Database status: {total_photos} photos scanned, {total_faces} faces detected")

        if self.should_scan_on_startup():
            scan_frequency = self._settings.get('scan_frequency', 'restart_1_day')

            if scan_frequency == 'manual':
                self.update_status("Automatic scanning disabled - use manual rescan from settings")
            else:
                self.update_status("Checking filesystem for changes...")
                self.start_scanning()
                return {'needs_scan': True}
        else:
            scan_frequency = self._settings.get('scan_frequency', 'restart_1_day')
            last_scan_time = self._settings.get('last_scan_time')

            if last_scan_time:
                time_since_scan = time.time() - last_scan_time
                hours = int(time_since_scan / 3600)

                if scan_frequency == 'restart_1_day':
                    self.update_status(f"Automatic scan skipped - scanned {hours}h ago, will scan after 24h")
                elif scan_frequency == 'restart_1_week':
                    days = int(time_since_scan / 86400)
                    self.update_status(f"Automatic scan skipped - scanned {days} days ago, will scan after 7 days")

            self.update_status("Loading existing data...")
            self.cluster_complete()

        return {'needs_scan': False}

    def get_scan_frequency(self):
        return self._settings.get('scan_frequency', 'restart_1_day')

    def set_scan_frequency(self, frequency):
        self._settings.set('scan_frequency', frequency)

    def get_grid_size(self):
        return self._settings.get('grid_size', 180)

    def set_grid_size(self, size):
        self._settings.set('grid_size', size)

    def get_include_folders(self):
        return self._settings.get('include_folders', [])

    def set_include_folders(self, folders):
        self._settings.set('include_folders', folders)

    def get_exclude_folders(self):
        return self._settings.get('exclude_folders', [])

    def set_exclude_folders(self, folders):
        self._settings.set('exclude_folders', folders)

    def get_wildcard_exclusions(self):
        return self._settings.get('wildcard_exclusions', '')

    def set_wildcard_exclusions(self, wildcards):
        self._settings.set('wildcard_exclusions', wildcards)

    def get_view_mode(self):
        return self._settings.get('view_mode', 'entire_photo')

    def set_view_mode(self, mode):
        self._settings.set('view_mode', mode)

    def get_sort_mode(self):
        return self._settings.get('sort_mode', 'names_asc')

    def set_sort_mode(self, mode):
        self._settings.set('sort_mode', mode)

    def is_window_foreground(self):
        return self._window_foreground

    def set_window_foreground(self, foreground):
        self._window_foreground = foreground

    def get_dynamic_resources(self):
        return self._dynamic_resources

    def close(self):
        """Cleanup resources"""
        self._db.close()
