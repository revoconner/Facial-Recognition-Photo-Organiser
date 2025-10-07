import sys
import os
import base64
import threading
from pathlib import Path
from typing import Optional, List
from io import BytesIO
from PIL import Image, ImageOps
import torch
import webview
import pystray
from pystray import MenuItem as item

from utils import get_appdata_path, create_tray_icon
from database import FaceDatabase
from thumbnail_cache import ThumbnailCache
from settings import Settings
from workers import ScanWorker, ClusterWorker


class API:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._threshold = settings.get('threshold', 50)
        
        db_path = get_appdata_path()
        print(f"Database location: {db_path}")
        
        self._db = FaceDatabase(str(db_path))
        self._window = None
        self._scan_worker = None
        self._cluster_worker = None
        self._tray_icon = None
        self._close_to_tray = settings.get('close_to_tray', True)
        self._quit_flag = False
        self._dynamic_resources = settings.get('dynamic_resources', True)
        self._window_foreground = True

        cache_path = db_path.parent / "thumbnail_cache"
        self._thumbnail_cache = ThumbnailCache(str(cache_path))
        print(f"Thumbnail cache location: {cache_path}")

    def set_window(self, window):
        self._window = window
        self._setup_window_events()
        if self._close_to_tray:
            self._setup_tray()
    
    def _setup_window_events(self):
        def on_closing():
            if self._quit_flag:
                return False
            if self._close_to_tray:
                self._window.hide()
                self._window_foreground = False
                return True
            return False
        
        self._window.events.closing += on_closing
    
    def _setup_tray(self):
        if self._tray_icon:
            return
        
        def on_quit(icon, item):
            print("Tray quit clicked")
            self._quit_flag = True
            icon.stop()
            
            if self._window:
                try:
                    self._window.evaluate_js("showCleanupMessage()")
                except:
                    pass
            
            try:
                for win in webview.windows:
                    print(f"Destroying window from tray: {win}")
                    win.destroy()
            except Exception as e:
                print(f"Error destroying windows from tray: {e}")
            
            import threading
            def force_exit():
                import time
                time.sleep(0.5)
                print("Force exiting from tray")
                import os
                os._exit(0)
            
            exit_thread = threading.Thread(target=force_exit, daemon=True)
            exit_thread.start()
        
        def on_restore(icon=None, item=None):
            if self._window:
                try:
                    self._window.restore()
                    self._window.show()
                    self._window_foreground = True
                except Exception as e:
                    print(f"Error restoring window: {e}")
        
        icon_image = create_tray_icon()
        
        menu = pystray.Menu(
            item('Open', on_restore, default=True),
            item('Quit', on_quit)
        )
        
        self._tray_icon = pystray.Icon(
            "face_recognition",
            icon_image,
            "Face Recognition",
            menu
        )
        
        self._tray_icon.on_activate = on_restore
        
        tray_thread = threading.Thread(target=self._tray_icon.run, daemon=False)
        tray_thread.start()
    
    def update_status(self, message: str):
        if self._window:
            safe_message = message.replace('"', '\\"').replace('\n', ' ')
            self._window.evaluate_js(f'updateStatusMessage("{safe_message}")')
    
    def update_progress(self, current: int, total: int):
        if self._window:
            percent = (current / total) * 100 if total > 0 else 0
            self._window.evaluate_js(f'updateProgress({current}, {total}, {percent})')

    def get_cache_stats(self):
        return self._thumbnail_cache.get_cache_size()
    
    def clear_thumbnail_cache(self):
        stats = self._thumbnail_cache.clear_cache()
        if self._window:
            self._window.evaluate_js('loadPeople()')
        return stats
    
    def scan_complete(self):
        total_faces = self._db.get_total_faces()
        total_photos = self._db.get_total_photos()
        pending_count = self._db.get_photos_needing_scan()
        
        self.update_status(f"Scan complete: {total_faces} faces in {total_photos} photos")
        
        if pending_count > 0:
            self.update_status(f"Warning: {pending_count} photos had errors and were skipped")
        
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
        if self._window:
            self._window.evaluate_js('hideProgress()')
            self._window.evaluate_js('loadPeople()')
    
    def get_system_info(self):
        GPU_AVAILABLE = torch.cuda.is_available()
        return {
            'pytorch_version': torch.__version__,
            'gpu_available': GPU_AVAILABLE,
            'cuda_version': torch.version.cuda if GPU_AVAILABLE else 'N/A',
            'gpu_name': torch.cuda.get_device_name(0) if GPU_AVAILABLE else 'N/A',
            'total_faces': self._db.get_total_faces()
        }
    
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
        
        result = []
        
        for person in persons:
            person_id = person['person_id']
            is_hidden = person_id in hidden_persons
            
            if is_hidden and not show_hidden:
                continue
            
            name = self._db.get_person_name_fast(clustering_id, person_id)
            
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
    
    def hide_person(self, clustering_id, person_id):
        self._db.hide_person(clustering_id, person_id)
        if self._window:
            self._window.evaluate_js('loadPeople()')
    
    def unhide_person(self, clustering_id, person_id):
        self._db.unhide_person(clustering_id, person_id)
        if self._window:
            self._window.evaluate_js('loadPeople()')
    
    def hide_photo(self, face_id):
        self._db.hide_photo(face_id)
        if self._window:
            self._window.evaluate_js('reloadCurrentPhotos()')
        return {'success': True}
    
    def unhide_photo(self, face_id):
        self._db.unhide_photo(face_id)
        if self._window:
            self._window.evaluate_js('reloadCurrentPhotos()')
        return {'success': True}
    
    def rename_person(self, clustering_id, person_id, new_name):
        if not new_name or not new_name.strip():
            return {'success': False, 'message': 'Name cannot be empty'}
        
        new_name = new_name.strip()
        
        face_ids = self._db.get_face_ids_for_person(clustering_id, person_id, limit=10000)
        
        if not face_ids:
            return {'success': False, 'message': 'No faces found for this person'}
        
        self._db.tag_faces(face_ids, new_name)
        
        if self._window:
            self._window.evaluate_js('loadPeople()')
        
        return {'success': True, 'faces_tagged': len(face_ids)}
    
    def untag_person(self, clustering_id, person_id):
        face_ids = self._db.get_face_ids_for_person(clustering_id, person_id, limit=10000)
        
        if not face_ids:
            return {'success': False, 'message': 'No faces found for this person'}
        
        self._db.untag_faces(face_ids)
        
        if self._window:
            self._window.evaluate_js('loadPeople()')
        
        return {'success': True, 'faces_untagged': len(face_ids)}
    
    def set_primary_photo(self, tag_name, face_id):
        try:
            if not tag_name or tag_name.startswith('Person ') or tag_name == 'Unmatched Faces':
                return {'success': False, 'message': 'Please name this person before setting a primary photo'}
            
            self._db.set_primary_photo_for_tag(tag_name, face_id)
            if self._window:
                self._window.evaluate_js('loadPeople()')
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
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            return f"data:image/jpeg;base64,{img_base64}"
        except Exception as e:
            return None
    
    def get_named_people_for_transfer(self, clustering_id):
        try:
            people = self._db.get_all_named_people(clustering_id)
            return {'success': True, 'people': people}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def transfer_face_to_person(self, face_id, target_name):
        try:
            self._db.transfer_face_to_person(face_id, target_name)
            if self._window:
                self._window.evaluate_js('loadPeople()')
                self._window.evaluate_js('reloadCurrentPhotos()')
            return {'success': True, 'message': f'Face transferred to {target_name}'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def remove_face_permanently(self, face_id):
        try:
            self._db.hide_photo(face_id)
            if self._window:
                self._window.evaluate_js('reloadCurrentPhotos()')
            return {'success': True, 'message': 'Face removed from this person'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
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
    
    def save_log(self, log_content):
        try:
            import tkinter as tk
            from tkinter import filedialog
            
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            
            file_path = filedialog.asksaveasfilename(
                title="Save Log File",
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                initialfile="face_recognition_log.txt"
            )
            
            root.destroy()
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                return {'success': True, 'path': file_path}
            else:
                return {'success': False, 'message': 'Save cancelled'}
                
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def check_initial_state(self):
        total_faces = self._db.get_total_faces()
        total_photos = self._db.get_total_photos()
        
        self.update_status(f"Database status: {total_photos} photos scanned, {total_faces} faces detected")
        
        self.update_status("Checking filesystem for changes...")
        self.start_scanning()
        return {'needs_scan': True}
    
    def get_close_to_tray(self):
        return self._close_to_tray
    
    def set_close_to_tray(self, enabled):
        self._close_to_tray = enabled
        self._settings.set('close_to_tray', enabled)
        if enabled:
            if not self._tray_icon or not self._tray_icon.visible:
                self._setup_tray()
        else:
            if self._tray_icon:
                try:
                    self._tray_icon.stop()
                except:
                    pass
                self._tray_icon = None
    
    def get_dynamic_resources(self):
        return self._dynamic_resources
    
    def set_dynamic_resources(self, enabled):
        self._dynamic_resources = enabled
        self._settings.set('dynamic_resources', enabled)
        if enabled:
            self.update_status("Dynamic resource management enabled - will throttle when in background")
        else:
            self.update_status("Dynamic resource management disabled - full speed always")
    
    def get_show_unmatched(self):
        return self._settings.get('show_unmatched', False)
    
    def set_show_unmatched(self, enabled):
        self._settings.set('show_unmatched', enabled)
    
    def get_show_hidden(self):
        return self._settings.get('show_hidden', False)
    
    def set_show_hidden(self, enabled):
        self._settings.set('show_hidden', enabled)
    
    def get_show_hidden_photos(self):
        return self._settings.get('show_hidden_photos', False)
    
    def set_show_hidden_photos(self, enabled):
        self._settings.set('show_hidden_photos', enabled)
    
    def get_show_dev_options(self):
        return self._settings.get('show_dev_options', False)
    
    def set_show_dev_options(self, enabled):
        self._settings.set('show_dev_options', enabled)
    
    def get_min_photos_enabled(self):
        return self._settings.get('min_photos_enabled', False)
    
    def set_min_photos_enabled(self, enabled):
        self._settings.set('min_photos_enabled', enabled)
    
    def get_min_photos_count(self):
        return self._settings.get('min_photos_count', 2)
    
    def set_min_photos_count(self, count):
        self._settings.set('min_photos_count', count)
    
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
        if self._window:
            self._window.evaluate_js('reloadCurrentPhotos()')
    
    def get_sort_mode(self):
        return self._settings.get('sort_mode', 'names_asc')
    
    def set_sort_mode(self, mode):
        self._settings.set('sort_mode', mode)
    
    def select_folder(self):
        try:
            result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
            if result and len(result) > 0:
                return result[0]
            return None
        except Exception as e:
            print(f"Error selecting folder: {e}")
            return None
    
    def is_window_foreground(self):
        return self._window_foreground
    
    def set_window_foreground(self, foreground):
        self._window_foreground = foreground
    
    def minimize_window(self):
        if self._window:
            if self._close_to_tray:
                self._window.hide()
                self._window_foreground = False
            else:
                self._window.minimize()
                self._window_foreground = False
    
    def maximize_window(self):
        if self._window:
            self._window.toggle_fullscreen()
    
    def close_window(self):
        print(f"close_window called: close_to_tray={self._close_to_tray}, quit_flag={self._quit_flag}")
        
        if self._close_to_tray and not self._quit_flag:
            print("Hiding window to tray")
            if self._window:
                self._window.hide()
                self._window_foreground = False
        else:
            print("Attempting to close application")
            self._quit_flag = True
            
            if self._window:
                self._window.evaluate_js("showCleanupMessage()")
            
            if self._tray_icon:
                print("Stopping tray icon")
                try:
                    self._tray_icon.stop()
                    print("Tray icon stopped")
                except Exception as e:
                    print(f"Error stopping tray icon: {e}")
                self._tray_icon = None
            
            if self._window:
                print("Destroying window")
                try:
                    for win in webview.windows:
                        print(f"Destroying window: {win}")
                        win.destroy()
                    print("All windows destroyed")
                except Exception as e:
                    print(f"Error destroying windows: {e}")
                    import traceback
                    traceback.print_exc()
            
            import threading
            def force_exit():
                import time
                time.sleep(0.5)
                print("Force exiting application")
                import os
                os._exit(0)
            
            exit_thread = threading.Thread(target=force_exit, daemon=True)
            exit_thread.start()
    
    def close(self):
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except:
                pass
        self._db.close()
