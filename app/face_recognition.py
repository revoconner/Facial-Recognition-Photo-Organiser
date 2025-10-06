import sys
import os
import argparse
import duckdb
import lmdb
import pickle
import hashlib
import threading
import json
import base64
import time
import fnmatch
from pathlib import Path
from typing import List, Optional, Tuple, Set, Dict
from collections import Counter
import numpy as np
import cv2
from insightface.app import FaceAnalysis
from PIL import Image
import pillow_heif
from io import BytesIO
import networkx as nx
import torch
import webview
import pystray
from pystray import MenuItem as item
from PIL import Image as PILImage, ImageDraw

pillow_heif.register_heif_opener()

GPU_AVAILABLE = torch.cuda.is_available()
DEVICE = torch.device('cuda' if GPU_AVAILABLE else 'cpu')


def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_appdata_path():
    appdata = os.environ.get('APPDATA')
    if appdata:
        return Path(appdata) / "facial_recognition" / "face_data"
    else:
        return Path.home() / "AppData" / "Roaming" / "facial_recognition" / "face_data"


def get_insightface_root():
    if getattr(sys, 'frozen', False):
        base_path = Path(sys._MEIPASS)
        return str(base_path)
    else:
        return str(Path.home() / '.insightface')


class Settings:
    def __init__(self, settings_path: str):
        self.settings_path = Path(settings_path)
        self.settings_file = self.settings_path / "settings.json"
        self.settings_path.mkdir(parents=True, exist_ok=True)
        
        self.defaults = {
            'threshold': 50,
            'close_to_tray': True,
            'dynamic_resources': True,
            'show_unmatched': False,
            'show_hidden': False,
            'show_hidden_photos': False,
            'show_dev_options': False,
            'min_photos_enabled': False,
            'min_photos_count': 2,
            'grid_size': 180,
            'window_width': 1200,
            'window_height': 800,
            'include_folders': [],
            'exclude_folders': [],
            'wildcard_exclusions': '',
            'view_mode': 'entire_photo',
            'sort_mode': 'names_asc'
        }
        
        self.settings = self.load()
    
    def load(self) -> dict:
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    loaded = json.load(f)
                    return {**self.defaults, **loaded}
        except Exception as e:
            print(f"Error loading settings: {e}")
        
        return self.defaults.copy()
    
    def save(self):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def get(self, key: str, default=None):
        return self.settings.get(key, default)
    
    def set(self, key: str, value):
        self.settings[key] = value
        self.save()
    
    def update(self, updates: dict):
        self.settings.update(updates)
        self.save()


class FaceDatabase:
    def __init__(self, db_folder: str):
        self.db_folder = Path(db_folder)
        self.db_folder.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.db_folder / "metadata.duckdb"
        self.conn = duckdb.connect(str(self.db_path))
        
        cpu_count = os.cpu_count() or 4
        self.conn.execute(f"SET threads TO {cpu_count}")
        self.conn.execute("SET memory_limit = '4GB'")
        
        self.lmdb_path = self.db_folder / "encodings.lmdb"
        self.env = lmdb.open(
            str(self.lmdb_path),
            map_size=10*1024*1024*1024,
            max_dbs=1
        )
        
        self._init_tables()
        self._lock = threading.Lock()
    
    def _init_tables(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS photos (
                photo_id INTEGER PRIMARY KEY,
                file_path VARCHAR UNIQUE NOT NULL,
                file_hash VARCHAR,
                scan_status VARCHAR DEFAULT 'pending',
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.execute('''
            CREATE SEQUENCE IF NOT EXISTS photos_seq START 1
        ''')
        
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS faces (
                face_id INTEGER PRIMARY KEY,
                photo_id INTEGER NOT NULL,
                bbox_x1 DOUBLE,
                bbox_y1 DOUBLE,
                bbox_x2 DOUBLE,
                bbox_y2 DOUBLE
            )
        ''')
        
        self.conn.execute('''
            CREATE SEQUENCE IF NOT EXISTS faces_seq START 1
        ''')
        
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS clusterings (
                clustering_id INTEGER PRIMARY KEY,
                threshold DOUBLE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT false
            )
        ''')
        
        self.conn.execute('''
            CREATE SEQUENCE IF NOT EXISTS clusterings_seq START 1
        ''')
        
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS cluster_assignments (
                face_id INTEGER NOT NULL,
                clustering_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                confidence_score DOUBLE,
                PRIMARY KEY (face_id, clustering_id)
            )
        ''')
        
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS hidden_persons (
                clustering_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                hidden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (clustering_id, person_id)
            )
        ''')
        
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS hidden_photos (
                face_id INTEGER PRIMARY KEY,
                hidden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS face_tags (
                face_id INTEGER PRIMARY KEY,
                tag_name VARCHAR NOT NULL,
                tagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS tag_primary_photos (
                tag_name VARCHAR PRIMARY KEY,
                face_id INTEGER NOT NULL,
                set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_photos_status ON photos(scan_status)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_photos_path ON photos(file_path)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_id)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_cluster_assign ON cluster_assignments(clustering_id, person_id)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_hidden_persons ON hidden_persons(clustering_id)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_hidden_photos ON hidden_photos(face_id)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_face_tags_name ON face_tags(tag_name)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_tag_primary_photos ON tag_primary_photos(tag_name)')
    
    def add_photo(self, file_path: str, file_hash: str) -> Optional[int]:
        with self._lock:
            try:
                result = self.conn.execute('''
                    INSERT INTO photos (photo_id, file_path, file_hash)
                    SELECT nextval('photos_seq'), ?, ?
                    WHERE NOT EXISTS (SELECT 1 FROM photos WHERE file_path = ?)
                    RETURNING photo_id
                ''', [file_path, file_hash, file_path]).fetchone()
                
                if result:
                    return result[0]
                
                return self.get_photo_id(file_path)
            except Exception as e:
                print(f"Database error in add_photo: {e}")
                return None
    
    def get_photo_id(self, file_path: str) -> Optional[int]:
        result = self.conn.execute('SELECT photo_id FROM photos WHERE file_path = ?', [file_path]).fetchone()
        return result[0] if result else None
    
    def get_all_scanned_paths(self) -> Set[str]:
        results = self.conn.execute('SELECT file_path FROM photos WHERE scan_status = ?', ['completed']).fetchall()
        return {row[0] for row in results}
    
    def get_pending_and_error_paths(self) -> List[str]:
        results = self.conn.execute('''
            SELECT file_path FROM photos 
            WHERE scan_status IN ('pending', 'error')
        ''').fetchall()
        return [row[0] for row in results]
    
    def remove_deleted_photos(self, existing_paths: Set[str]) -> int:
        with self._lock:
            all_db_photos = self.conn.execute('SELECT photo_id, file_path FROM photos').fetchall()
            
            deleted_count = 0
            deleted_photo_ids = []
            for photo_id, file_path in all_db_photos:
                if file_path not in existing_paths:
                    deleted_photo_ids.append(photo_id)
                    deleted_count += 1
            
            if deleted_photo_ids:
                deleted_face_ids = self.conn.execute(f'''
                    SELECT face_id FROM faces 
                    WHERE photo_id IN ({','.join(['?'] * len(deleted_photo_ids))})
                ''', deleted_photo_ids).fetchall()
                deleted_face_ids = [row[0] for row in deleted_face_ids]
                
                if deleted_face_ids:
                    face_placeholders = ','.join(['?'] * len(deleted_face_ids))
                    self.conn.execute(f'DELETE FROM face_tags WHERE face_id IN ({face_placeholders})', deleted_face_ids)
                    self.conn.execute(f'DELETE FROM tag_primary_photos WHERE face_id IN ({face_placeholders})', deleted_face_ids)
                    self.conn.execute(f'DELETE FROM hidden_photos WHERE face_id IN ({face_placeholders})', deleted_face_ids)
                
                photo_placeholders = ','.join(['?'] * len(deleted_photo_ids))
                self.conn.execute(f'DELETE FROM faces WHERE photo_id IN ({photo_placeholders})', deleted_photo_ids)
                self.conn.execute(f'DELETE FROM photos WHERE photo_id IN ({photo_placeholders})', deleted_photo_ids)
            
            return deleted_count
    
    def get_photos_needing_scan(self) -> int:
        result = self.conn.execute('''
            SELECT COUNT(*) FROM photos 
            WHERE scan_status IN ('pending', 'error')
        ''').fetchone()
        return result[0]
    
    def add_face(self, photo_id: int, embedding: np.ndarray, bbox: List[float]) -> int:
        with self._lock:
            face_id = self.conn.execute('''
                INSERT INTO faces (face_id, photo_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2) 
                VALUES (nextval('faces_seq'), ?, ?, ?, ?, ?)
                RETURNING face_id
            ''', [photo_id, bbox[0], bbox[1], bbox[2], bbox[3]]).fetchone()[0]
            
            with self.env.begin(write=True) as txn:
                key = str(face_id).encode()
                value = pickle.dumps(embedding)
                txn.put(key, value)
            
            return face_id
    
    def get_face_embedding(self, face_id: int) -> Optional[np.ndarray]:
        with self.env.begin() as txn:
            key = str(face_id).encode()
            value = txn.get(key)
            if value:
                return pickle.loads(value)
        return None
    
    def get_all_embeddings(self) -> Tuple[List[int], np.ndarray]:
        face_ids = self.conn.execute('SELECT face_id FROM faces ORDER BY face_id').fetchall()
        face_ids = [row[0] for row in face_ids]
        
        embeddings = []
        valid_face_ids = []
        for face_id in face_ids:
            embedding = self.get_face_embedding(face_id)
            if embedding is not None:
                embeddings.append(embedding)
                valid_face_ids.append(face_id)
        
        if embeddings:
            return valid_face_ids, np.array(embeddings)
        return [], np.array([])
    
    def create_clustering(self, threshold: float) -> int:
        with self._lock:
            self.conn.execute('UPDATE clusterings SET is_active = false')
            clustering_id = self.conn.execute('''
                INSERT INTO clusterings (clustering_id, threshold, is_active) 
                VALUES (nextval('clusterings_seq'), ?, true)
                RETURNING clustering_id
            ''', [threshold]).fetchone()[0]
            return clustering_id
    
    def save_cluster_assignments(self, clustering_id: int, face_ids: List[int], 
                                 person_ids: List[int], confidences: List[float]):
        with self._lock:
            data = [(fid, clustering_id, pid, conf) 
                    for fid, pid, conf in zip(face_ids, person_ids, confidences)]
            
            self.conn.executemany('''
                INSERT OR REPLACE INTO cluster_assignments 
                (face_id, clustering_id, person_id, confidence_score)
                VALUES (?, ?, ?, ?)
            ''', data)
    
    def get_active_clustering(self) -> Optional[dict]:
        result = self.conn.execute('SELECT * FROM clusterings WHERE is_active = true').fetchone()
        if result:
            return {
                'clustering_id': result[0],
                'threshold': result[1],
                'created_at': result[2],
                'is_active': result[3]
            }
        return None
    
    def get_persons_in_clustering(self, clustering_id: int) -> List[dict]:
        results = self.conn.execute('''
            SELECT person_id, COUNT(*) as face_count
            FROM cluster_assignments
            WHERE clustering_id = ?
            GROUP BY person_id
            ORDER BY person_id
        ''', [clustering_id]).fetchall()
        return [{'person_id': row[0], 'face_count': row[1]} for row in results]
    
    def get_face_ids_for_person(self, clustering_id: int, person_id: int) -> List[int]:
        results = self.conn.execute('''
            SELECT face_id FROM cluster_assignments
            WHERE clustering_id = ? AND person_id = ?
        ''', [clustering_id, person_id]).fetchall()
        return [row[0] for row in results]
    
    def get_photos_by_person(self, clustering_id: int, person_id: int) -> List[dict]:
        results = self.conn.execute('''
            SELECT DISTINCT p.file_path, f.face_id, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2
            FROM photos p
            JOIN faces f ON p.photo_id = f.photo_id
            JOIN cluster_assignments ca ON f.face_id = ca.face_id
            WHERE ca.clustering_id = ? AND ca.person_id = ?
        ''', [clustering_id, person_id]).fetchall()
        return [{
            'file_path': row[0],
            'face_id': row[1],
            'bbox_x1': row[2],
            'bbox_y1': row[3],
            'bbox_x2': row[4],
            'bbox_y2': row[5]
        } for row in results]
    
    def get_face_data(self, face_id: int) -> Optional[dict]:
        result = self.conn.execute('''
            SELECT f.face_id, f.photo_id, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, p.file_path
            FROM faces f
            JOIN photos p ON f.photo_id = p.photo_id
            WHERE f.face_id = ?
        ''', [face_id]).fetchone()
        if result:
            return {
                'face_id': result[0],
                'photo_id': result[1],
                'bbox_x1': result[2],
                'bbox_y1': result[3],
                'bbox_x2': result[4],
                'bbox_y2': result[5],
                'file_path': result[6]
            }
        return None
    
    def hide_person(self, clustering_id: int, person_id: int):
        with self._lock:
            self.conn.execute('''
                INSERT OR IGNORE INTO hidden_persons (clustering_id, person_id)
                VALUES (?, ?)
            ''', [clustering_id, person_id])
    
    def unhide_person(self, clustering_id: int, person_id: int):
        with self._lock:
            self.conn.execute('''
                DELETE FROM hidden_persons 
                WHERE clustering_id = ? AND person_id = ?
            ''', [clustering_id, person_id])
    
    def get_hidden_persons(self, clustering_id: int) -> Set[int]:
        results = self.conn.execute('''
            SELECT person_id FROM hidden_persons
            WHERE clustering_id = ?
        ''', [clustering_id]).fetchall()
        return {row[0] for row in results}
    
    def hide_photo(self, face_id: int):
        with self._lock:
            self.conn.execute('''
                INSERT OR IGNORE INTO hidden_photos (face_id)
                VALUES (?)
            ''', [face_id])
    
    def unhide_photo(self, face_id: int):
        with self._lock:
            self.conn.execute('''
                DELETE FROM hidden_photos 
                WHERE face_id = ?
            ''', [face_id])
    
    def get_hidden_photos(self) -> Set[int]:
        results = self.conn.execute('SELECT face_id FROM hidden_photos').fetchall()
        return {row[0] for row in results}
    
    def set_primary_photo_for_tag(self, tag_name: str, face_id: int):
        with self._lock:
            self.conn.execute('''
                INSERT OR REPLACE INTO tag_primary_photos (tag_name, face_id)
                VALUES (?, ?)
            ''', [tag_name, face_id])
    
    def get_primary_photo_for_tag(self, tag_name: str) -> Optional[int]:
        result = self.conn.execute('''
            SELECT face_id FROM tag_primary_photos
            WHERE tag_name = ?
        ''', [tag_name]).fetchone()
        if result:
            face_id = result[0]
            face_data = self.get_face_data(face_id)
            if face_data:
                return face_id
            else:
                with self._lock:
                    self.conn.execute('DELETE FROM tag_primary_photos WHERE tag_name = ?', [tag_name])
                return None
        return None
    
    def tag_faces(self, face_ids: List[int], tag_name: str):
        with self._lock:
            data = [(fid, tag_name) for fid in face_ids]
            self.conn.executemany('''
                INSERT OR REPLACE INTO face_tags (face_id, tag_name)
                VALUES (?, ?)
            ''', data)
    
    def untag_faces(self, face_ids: List[int]):
        with self._lock:
            if face_ids:
                placeholders = ','.join(['?'] * len(face_ids))
                self.conn.execute(f'DELETE FROM face_tags WHERE face_id IN ({placeholders})', face_ids)
    
    def get_face_tags(self, face_ids: List[int]) -> Dict[int, str]:
        if not face_ids:
            return {}
        
        placeholders = ','.join(['?'] * len(face_ids))
        results = self.conn.execute(f'''
            SELECT face_id, tag_name FROM face_tags
            WHERE face_id IN ({placeholders})
        ''', face_ids).fetchall()
        
        return {row[0]: row[1] for row in results}
    
    def get_person_tag_summary(self, face_ids: List[int]) -> Optional[Dict]:
        if not face_ids:
            return None
        
        tags = self.get_face_tags(face_ids)
        
        if not tags:
            return None
        
        tag_counts = Counter(tags.values())
        most_common_tag, count = tag_counts.most_common(1)[0]
        
        return {
            'name': most_common_tag,
            'tagged_count': count,
            'total_count': len(face_ids),
            'all_tags': dict(tag_counts)
        }
    
    def update_photo_status(self, photo_id: int, status: str):
        with self._lock:
            self.conn.execute('UPDATE photos SET scan_status = ? WHERE photo_id = ?', 
                          [status, photo_id])
    
    def get_total_faces(self) -> int:
        result = self.conn.execute('SELECT COUNT(*) FROM faces').fetchone()
        return result[0]
    
    def get_total_photos(self) -> int:
        result = self.conn.execute('SELECT COUNT(*) FROM photos WHERE scan_status = ?', ['completed']).fetchone()
        return result[0]
    
    def close(self):
        self.conn.close()
        self.env.close()


class ScanWorker(threading.Thread):
    def __init__(self, db: FaceDatabase, api):
        super().__init__()
        self.db = db
        self.api = api
        self.face_app = None
        self.daemon = True
    
    def should_exclude_path(self, path: str) -> bool:
        include_folders = self.api.get_include_folders()
        exclude_folders = self.api.get_exclude_folders()
        wildcard_text = self.api.get_wildcard_exclusions()
        
        path_normalized = os.path.normpath(path)
        
        if not include_folders:
            return False
        
        is_in_include = False
        for include_folder in include_folders:
            include_normalized = os.path.normpath(include_folder)
            if path_normalized.startswith(include_normalized):
                is_in_include = True
                break
        
        if not is_in_include:
            return True
        
        for exclude_folder in exclude_folders:
            exclude_normalized = os.path.normpath(exclude_folder)
            if path_normalized.startswith(exclude_normalized):
                return True
        
        if wildcard_text:
            wildcards = [w.strip() for w in wildcard_text.split(',') if w.strip()]
            
            for wildcard in wildcards:
                wildcard_normalized = os.path.normpath(wildcard)
                
                if os.path.isabs(wildcard_normalized):
                    if path_normalized.startswith(wildcard_normalized):
                        return True
                else:
                    path_parts = path_normalized.split(os.sep)
                    filename = os.path.basename(path_normalized)
                    
                    if fnmatch.fnmatch(filename, wildcard):
                        return True
                    
                    for part in path_parts:
                        if fnmatch.fnmatch(part, wildcard):
                            return True
        
        return False
    
    def load_image(self, file_path: str) -> Optional[np.ndarray]:
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext in {'.heic', '.heif'}:
            try:
                pil_image = Image.open(file_path)
                image_rgb = np.array(pil_image.convert('RGB'))
                image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
                return image_bgr
            except Exception as e:
                self.api.update_status(f"ERROR: Cannot read HEIF image - {os.path.basename(file_path)}: {str(e)}")
                return None
        else:
            image = cv2.imread(file_path)
            return image

    def run(self):
        try:
            self.api.update_status("Initializing InsightFace model...")
            
            model_root = get_insightface_root()
            
            self.face_app = FaceAnalysis(
                name='buffalo_l',
                root=model_root,
                providers=['CPUExecutionProvider']
            )
            self.face_app.prepare(ctx_id=-1, det_size=(640, 640))
            self.api.update_status("Model loaded")
        except Exception as e:
            self.api.update_status(f"Error loading model: {e}")
            return
        
        include_folders = self.api.get_include_folders()
        
        if not include_folders:
            self.api.update_status("No folders configured for scanning")
            self.api.update_status("Please add folders in Settings > Folders to Scan")
            self.api.scan_complete()
            return
        
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.heic', '.heif'}
        
        self.api.update_status("Discovering photos...")
        all_image_files = set()
        
        for location in include_folders:
            if not os.path.exists(location):
                self.api.update_status(f"WARNING: Folder does not exist: {location}")
                continue
            
            self.api.update_status(f"Scanning folder: {location}")
            
            for root, dirs, files in os.walk(location):
                if self.should_exclude_path(root):
                    dirs.clear()
                    continue
                
                for file in files:
                    file_path = os.path.join(root, file)
                    
                    if Path(file).suffix.lower() in image_extensions:
                        if not self.should_exclude_path(file_path):
                            all_image_files.add(file_path)
        
        self.api.update_status(f"Found {len(all_image_files)} images after applying exclusions")
        
        self.api.update_status("Cleaning up deleted photos from database...")
        deleted_count = self.db.remove_deleted_photos(all_image_files)
        if deleted_count > 0:
            self.api.update_status(f"Removed {deleted_count} deleted photos from database")
        
        self.api.set_photos_deleted(deleted_count > 0)
        
        scanned_paths = self.db.get_all_scanned_paths()
        pending_paths_all = self.db.get_pending_and_error_paths()
        pending_paths = set(p for p in pending_paths_all if os.path.exists(p))
        
        stale_pending = len(pending_paths_all) - len(pending_paths)
        if stale_pending > 0:
            self.api.update_status(f"Ignoring {stale_pending} pending files that no longer exist")
        
        new_photos = all_image_files - scanned_paths
        photos_to_scan = list(new_photos | pending_paths)
        
        if len(photos_to_scan) == 0:
            self.api.update_status("No new photos to scan")
            self.api.set_new_photos_found(False)
            self.api.scan_complete()
            return
        
        self.api.set_new_photos_found(len(new_photos) > 0)
        
        total = len(photos_to_scan)
        total_photos = len(all_image_files)
        scanned_count = total_photos - total
        
        self.api.update_status(f"Found {len(new_photos)} new photos, {len(pending_paths)} incomplete")
        
        if len(new_photos) > 0:
            self.api.update_status(f"New photos detected: {len(new_photos)} files")
            new_photos_list = sorted(list(new_photos))
            for i, photo_path in enumerate(new_photos_list[:10]):
                self.api.update_status(f"  NEW: {os.path.basename(photo_path)}")
            if len(new_photos_list) > 10:
                self.api.update_status(f"  ... and {len(new_photos_list) - 10} more")
        
        if len(pending_paths) > 0:
            self.api.update_status(f"Incomplete photos to retry: {len(pending_paths)} files")
            pending_list = sorted(list(pending_paths))
            for i, photo_path in enumerate(pending_list[:10]):
                self.api.update_status(f"  RETRY: {os.path.basename(photo_path)}")
            if len(pending_list) > 10:
                self.api.update_status(f"  ... and {len(pending_list) - 10} more")
        
        self.api.update_status(f"Starting scan of {total} photos...")
        
        for idx, file_path in enumerate(photos_to_scan):
            current_overall = scanned_count + idx + 1
            self.api.update_progress(current_overall, total_photos)
            
            is_new = file_path in new_photos
            status_prefix = "NEW" if is_new else "RETRY"
            
            if (idx + 1) % 10 == 0 or idx == 0 or (idx + 1) == total:
                self.api.update_status(f"Scanning {status_prefix}: {os.path.basename(file_path)} ({idx + 1}/{total})")
            
            process_start = time.time()
            self.process_photo(file_path)
            process_time = time.time() - process_start
            
            should_throttle = self.api.get_dynamic_resources() and not self.api.is_window_foreground()
            
            if should_throttle:
                sleep_time = process_time * 19
                time.sleep(sleep_time)
        
        self.api.scan_complete()
    
    def process_photo(self, file_path: str):
        try:
            if not os.path.exists(file_path):
                self.api.update_status(f"ERROR: File not found - {os.path.basename(file_path)}")
                photo_id = self.db.get_photo_id(file_path)
                if photo_id:
                    self.db.update_photo_status(photo_id, 'error')
                return
            
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            
            photo_id = self.db.add_photo(file_path, file_hash)
            
            if not photo_id:
                self.api.update_status(f"ERROR: Failed to add photo to database - {os.path.basename(file_path)}")
                return
            
            status_row = self.db.conn.execute(
                'SELECT scan_status FROM photos WHERE photo_id = ?', 
                [photo_id]
            ).fetchone()
            
            if not status_row:
                self.api.update_status(f"ERROR: Photo record not found after insert - {os.path.basename(file_path)}")
                return
            
            existing_status = status_row[0]
            
            if existing_status == 'completed':
                return
            
            image = self.load_image(file_path)
            if image is None:
                self.api.update_status(f"ERROR: Cannot read image - {os.path.basename(file_path)}")
                self.db.update_photo_status(photo_id, 'error')
                return
            
            faces = self.face_app.get(image)
            
            if len(faces) == 0:
                self.api.update_status(f"INFO: No faces detected - {os.path.basename(file_path)}")
            else:
                self.api.update_status(f"INFO: Found {len(faces)} face(s) - {os.path.basename(file_path)}")
            
            for face in faces:
                embedding = face.embedding
                embedding_norm = embedding / np.linalg.norm(embedding)
                bbox = face.bbox.tolist()
                self.db.add_face(photo_id, embedding_norm, bbox)
            
            self.db.update_photo_status(photo_id, 'completed')
            
        except Exception as e:
            self.api.update_status(f"ERROR: Exception processing {os.path.basename(file_path)}: {str(e)}")
            if 'photo_id' in locals() and photo_id:
                self.db.update_photo_status(photo_id, 'error')


class ClusterWorker(threading.Thread):
    def __init__(self, db: FaceDatabase, threshold: float, api):
        super().__init__()
        self.db = db
        self.threshold = threshold / 100.0
        self.api = api
        self.daemon = True
    
    def run(self):
        try:
            self.api.update_status("Loading embeddings...")
            face_ids, embeddings = self.db.get_all_embeddings()
            
            if len(embeddings) == 0:
                self.api.update_status("No faces found")
                return
            
            self.api.update_status(f"Clustering {len(embeddings)} faces with PyTorch...")
            
            person_ids, confidences = self.cluster_with_pytorch(embeddings)
            
            self.api.update_status("Saving clustering...")
            clustering_id = self.db.create_clustering(self.threshold * 100)
            self.db.save_cluster_assignments(clustering_id, face_ids, person_ids, confidences)
            
            unique_persons = len(set(person_ids))
            matched_faces = sum(1 for pid in person_ids if pid > 0)
            unmatched_faces = sum(1 for pid in person_ids if pid == 0)
            
            self.api.update_status(f"Clustering complete:")
            self.api.update_status(f"  Total persons: {unique_persons}")
            self.api.update_status(f"  Matched faces: {matched_faces}")
            self.api.update_status(f"  Unmatched faces: {unmatched_faces}")
            self.api.update_status(f"Complete: {unique_persons} persons identified")
            self.api.cluster_complete()
            
        except Exception as e:
            self.api.update_status(f"Error: {str(e)}")
    
    def cluster_with_pytorch(self, embeddings: np.ndarray) -> Tuple[List[int], List[float]]:
        n_faces = len(embeddings)
        
        device_name = "GPU" if GPU_AVAILABLE else "CPU"
        self.api.update_status(f"Using {device_name} for clustering...")
        
        embeddings_tensor = torch.tensor(embeddings, dtype=torch.float32).to(DEVICE)
        
        self.api.update_status("Normalizing embeddings...")
        embeddings_norm = embeddings_tensor / embeddings_tensor.norm(dim=1, keepdim=True)
        
        batch_size = 1000
        n_batches = (n_faces + batch_size - 1) // batch_size
        
        self.api.update_status("Computing similarity matrix...")
        
        G = nx.Graph()
        
        for i in range(n_batches):
            start_i = i * batch_size
            end_i = min((i + 1) * batch_size, n_faces)
            batch_i = embeddings_norm[start_i:end_i]
            
            similarities = torch.mm(batch_i, embeddings_norm.T)
            similarities_cpu = similarities.cpu().numpy()
            
            for local_idx, global_idx in enumerate(range(start_i, end_i)):
                similar_indices = np.where(similarities_cpu[local_idx] >= self.threshold)[0]
                
                for j in similar_indices:
                    if global_idx != j and global_idx < j:
                        G.add_edge(global_idx, int(j), weight=float(similarities_cpu[local_idx, j]))
            
            if (i + 1) % 10 == 0 or i == n_batches - 1:
                self.api.update_status(f"Processing batch {i+1}/{n_batches}...")
        
        self.api.update_status("Finding connected components...")
        components = list(nx.connected_components(G))
        
        person_ids = [0] * n_faces
        confidences = [0.0] * n_faces
        
        for person_id, component in enumerate(components, start=1):
            for face_idx in component:
                person_ids[face_idx] = person_id
                
                neighbors = list(G.neighbors(face_idx))
                if neighbors:
                    weights = [G[face_idx][n]['weight'] for n in neighbors]
                    confidences[face_idx] = float(np.mean(weights))
                else:
                    confidences[face_idx] = 1.0
        
        return person_ids, confidences


def create_tray_icon():
    icon_path = get_resource_path('icon.ico')
    try:
        image = PILImage.open(icon_path)
        return image
    except Exception as e:
        print(f"Error loading icon.ico: {e}")
        width = 64
        height = 64
        image = PILImage.new('RGB', (width, height), (255, 255, 255))
        dc = ImageDraw.Draw(image)
        
        dc.ellipse([10, 10, 54, 54], fill=(59, 130, 246))
        dc.ellipse([20, 20, 30, 30], fill=(255, 255, 255))
        dc.ellipse([34, 20, 44, 30], fill=(255, 255, 255))
        dc.arc([15, 25, 49, 50], 0, 180, fill=(255, 255, 255), width=3)
        
        return image


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
            face_count = person['face_count']
            is_hidden = person_id in hidden_persons
            
            if is_hidden and not show_hidden:
                continue
            
            face_ids = self._db.get_face_ids_for_person(clustering_id, person_id)
            tag_summary = self._db.get_person_tag_summary(face_ids)
            
            if tag_summary:
                name = tag_summary['name']
                tagged_count = tag_summary['tagged_count']
            elif person_id > 0:
                name = f"Person {person_id}"
                tagged_count = 0
            else:
                name = "Unmatched Faces"
                tagged_count = 0
            
            if is_hidden:
                name += " (hidden)"
            
            primary_face_id = None
            if tag_summary:
                primary_face_id = self._db.get_primary_photo_for_tag(tag_summary['name'])
            
            if not primary_face_id and face_ids:
                primary_face_id = face_ids[0]
            
            thumbnail = None
            if primary_face_id:
                face_data = self._db.get_face_data(primary_face_id)
                if face_data:
                    bbox = [face_data['bbox_x1'], face_data['bbox_y1'], 
                           face_data['bbox_x2'], face_data['bbox_y2']]
                    thumbnail = self.create_thumbnail(face_data['file_path'], size=80, bbox=bbox)
            
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
        
        face_ids = self._db.get_face_ids_for_person(clustering_id, person_id)
        
        if not face_ids:
            return {'success': False, 'message': 'No faces found for this person'}
        
        self._db.tag_faces(face_ids, new_name)
        
        if self._window:
            self._window.evaluate_js('loadPeople()')
        
        return {'success': True, 'faces_tagged': len(face_ids)}
    
    def untag_person(self, clustering_id, person_id):
        face_ids = self._db.get_face_ids_for_person(clustering_id, person_id)
        
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
    
    def get_photos(self, clustering_id, person_id):
        photo_data = self._db.get_photos_by_person(clustering_id, person_id)
        hidden_photos = self._db.get_hidden_photos()
        show_hidden_photos = self._settings.get('show_hidden_photos', False)
        photos = []
        
        view_mode = self._settings.get('view_mode', 'entire_photo')
        
        for data in photo_data:
            face_id = data['face_id']
            is_hidden = face_id in hidden_photos
            
            if is_hidden and not show_hidden_photos:
                continue
            
            path = data['file_path']
            bbox = None
            
            if view_mode == 'zoom_to_faces':
                bbox = [data['bbox_x1'], data['bbox_y1'], data['bbox_x2'], data['bbox_y2']]
            
            thumbnail = self.create_thumbnail(path, bbox=bbox)
            if thumbnail:
                photos.append({
                    'path': path,
                    'thumbnail': thumbnail,
                    'name': os.path.basename(path),
                    'face_id': face_id,
                    'is_hidden': is_hidden
                })
        
        return photos
    
    def get_full_size_preview(self, image_path: str) -> Optional[str]:
        try:
            img = Image.open(image_path)
            
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
    
    def create_thumbnail(self, image_path: str, size: int = 150, bbox: Optional[List[float]] = None) -> Optional[str]:
        try:
            img = Image.open(image_path)
            
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--minimized', action='store_true', help='Start minimized to tray')
    args = parser.parse_args()
    print("=" * 60)
    print("Face Recognition Photo Organizer")
    print("=" * 60)
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {GPU_AVAILABLE}")
    if GPU_AVAILABLE:
        print(f"CUDA version: {torch.version.cuda}")
        print(f"GPU device: {torch.cuda.get_device_name(0)}")
    print("=" * 60)
    
    settings_path = get_appdata_path()
    settings = Settings(str(settings_path))
    
    print(f"Settings loaded from: {settings.settings_file}")
    print(f"Threshold: {settings.get('threshold')}%")
    print(f"Include folders: {settings.get('include_folders')}")
    print(f"Exclude folders: {settings.get('exclude_folders')}")
    print(f"Wildcard exclusions: {settings.get('wildcard_exclusions')}")
    print("=" * 60)
    
    api = API(settings)
    
    ui_html_path = get_resource_path('ui.html')
    
    window = webview.create_window(
        'Face Recognition Photo Organizer',
        ui_html_path,
        js_api=api,
        width=settings.get('window_width', 1200),
        height=settings.get('window_height', 800),
        resizable=True,
        frameless=True,
        easy_drag=False,
        hidden=args.minimized
    )
    
    api.set_window(window)
    
    webview.start(debug=False)
    
    api.close()


if __name__ == "__main__":
    main()
