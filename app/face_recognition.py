import sys
import os
import argparse
import sqlite3
import lmdb
import pickle
import hashlib
import threading
import json
import base64
import time
from pathlib import Path
from typing import List, Optional, Tuple, Set
import numpy as np
import cv2
from insightface.app import FaceAnalysis
from PIL import Image
import networkx as nx
import torch
import webview
import pystray
from pystray import MenuItem as item
from PIL import Image as PILImage, ImageDraw

GPU_AVAILABLE = torch.cuda.is_available()
DEVICE = torch.device('cuda' if GPU_AVAILABLE else 'cpu')


class FaceDatabase:
    def __init__(self, db_folder: str):
        self.db_folder = Path(db_folder)
        self.db_folder.mkdir(parents=True, exist_ok=True)
        
        self.sqlite_path = self.db_folder / "metadata.db"
        self.conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        self.lmdb_path = self.db_folder / "encodings.lmdb"
        self.env = lmdb.open(
            str(self.lmdb_path),
            map_size=10*1024*1024*1024,
            max_dbs=1
        )
        
        self._init_tables()
    
    def _init_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS photos (
                photo_id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT,
                scan_status TEXT DEFAULT 'pending',
                date_added REAL DEFAULT (julianday('now'))
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS faces (
                face_id INTEGER PRIMARY KEY AUTOINCREMENT,
                photo_id INTEGER NOT NULL,
                FOREIGN KEY (photo_id) REFERENCES photos(photo_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clusterings (
                clustering_id INTEGER PRIMARY KEY AUTOINCREMENT,
                threshold REAL NOT NULL,
                created_at REAL DEFAULT (julianday('now')),
                is_active BOOLEAN DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cluster_assignments (
                face_id INTEGER NOT NULL,
                clustering_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                confidence_score REAL,
                PRIMARY KEY (face_id, clustering_id),
                FOREIGN KEY (face_id) REFERENCES faces(face_id),
                FOREIGN KEY (clustering_id) REFERENCES clusterings(clustering_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_status ON photos(scan_status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_path ON photos(file_path)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_assign ON cluster_assignments(clustering_id, person_id)')
        
        self.conn.commit()
    
    def add_photo(self, file_path: str, file_hash: str) -> Optional[int]:
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO photos (file_path, file_hash)
                VALUES (?, ?)
            ''', (file_path, file_hash))
            self.conn.commit()
            
            if cursor.lastrowid:
                return cursor.lastrowid
            
            return self.get_photo_id(file_path)
        except Exception as e:
            print(f"Database error in add_photo: {e}")
            self.conn.rollback()
            return None
    
    def get_photo_id(self, file_path: str) -> Optional[int]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT photo_id FROM photos WHERE file_path = ?', (file_path,))
        row = cursor.fetchone()
        return row[0] if row else None
    
    def get_all_scanned_paths(self) -> Set[str]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT file_path FROM photos WHERE scan_status = "completed"')
        return {row[0] for row in cursor.fetchall()}
    
    def get_pending_and_error_paths(self) -> List[str]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT file_path FROM photos 
            WHERE scan_status IN ("pending", "error")
        ''')
        return [row[0] for row in cursor.fetchall()]
    
    def remove_deleted_photos(self, existing_paths: Set[str]) -> int:
        cursor = self.conn.cursor()
        cursor.execute('SELECT photo_id, file_path FROM photos')
        all_db_photos = cursor.fetchall()
        
        deleted_count = 0
        deleted_photo_ids = []
        for photo_id, file_path in all_db_photos:
            if file_path not in existing_paths:
                deleted_photo_ids.append(photo_id)
                deleted_count += 1
        
        if deleted_photo_ids:
            placeholders = ','.join('?' * len(deleted_photo_ids))
            cursor.execute(f'DELETE FROM faces WHERE photo_id IN ({placeholders})', deleted_photo_ids)
            cursor.execute(f'DELETE FROM photos WHERE photo_id IN ({placeholders})', deleted_photo_ids)
        
        self.conn.commit()
        return deleted_count
    
    def get_photos_needing_scan(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM photos 
            WHERE scan_status IN ("pending", "error")
        ''')
        return cursor.fetchone()[0]
    
    def add_face(self, photo_id: int, embedding: np.ndarray) -> int:
        cursor = self.conn.cursor()
        cursor.execute('INSERT INTO faces (photo_id) VALUES (?)', (photo_id,))
        self.conn.commit()
        face_id = cursor.lastrowid
        
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
        cursor = self.conn.cursor()
        cursor.execute('SELECT face_id FROM faces ORDER BY face_id')
        face_ids = [row[0] for row in cursor.fetchall()]
        
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
        cursor = self.conn.cursor()
        cursor.execute('UPDATE clusterings SET is_active = 0')
        cursor.execute('INSERT INTO clusterings (threshold, is_active) VALUES (?, 1)', (threshold,))
        self.conn.commit()
        return cursor.lastrowid
    
    def save_cluster_assignments(self, clustering_id: int, face_ids: List[int], 
                                 person_ids: List[int], confidences: List[float]):
        cursor = self.conn.cursor()
        data = [(fid, clustering_id, pid, conf) 
                for fid, pid, conf in zip(face_ids, person_ids, confidences)]
        cursor.executemany('''
            INSERT OR REPLACE INTO cluster_assignments 
            (face_id, clustering_id, person_id, confidence_score)
            VALUES (?, ?, ?, ?)
        ''', data)
        self.conn.commit()
    
    def get_active_clustering(self) -> Optional[dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM clusterings WHERE is_active = 1')
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_persons_in_clustering(self, clustering_id: int) -> List[dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT person_id, COUNT(*) as face_count
            FROM cluster_assignments
            WHERE clustering_id = ?
            GROUP BY person_id
            ORDER BY person_id
        ''', (clustering_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_photos_by_person(self, clustering_id: int, person_id: int) -> List[str]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT DISTINCT p.file_path
            FROM photos p
            JOIN faces f ON p.photo_id = f.photo_id
            JOIN cluster_assignments ca ON f.face_id = ca.face_id
            WHERE ca.clustering_id = ? AND ca.person_id = ?
        ''', (clustering_id, person_id))
        return [row[0] for row in cursor.fetchall()]
    
    def update_photo_status(self, photo_id: int, status: str):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE photos SET scan_status = ? WHERE photo_id = ?', 
                      (status, photo_id))
        self.conn.commit()
    
    def get_total_faces(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM faces')
        return cursor.fetchone()[0]
    
    def get_total_photos(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM photos WHERE scan_status = "completed"')
        return cursor.fetchone()[0]
    
    def close(self):
        self.conn.close()
        self.env.close()


class ScanWorker(threading.Thread):
    def __init__(self, db: FaceDatabase, location: str, api):
        super().__init__()
        self.db = db
        self.location = location
        self.api = api
        self.face_app = None
        self.daemon = True
    
    def run(self):
        try:
            self.api.update_status("Initializing InsightFace model...")
            self.face_app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
            self.face_app.prepare(ctx_id=-1, det_size=(640, 640))
            self.api.update_status("Model loaded")
        except Exception as e:
            self.api.update_status(f"Error loading model: {e}")
            return
        
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}
        
        self.api.update_status("Discovering photos...")
        all_image_files = set()
        for root, dirs, files in os.walk(self.location):
            for file in files:
                if Path(file).suffix.lower() in image_extensions:
                    all_image_files.add(os.path.join(root, file))
        
        self.api.update_status("Cleaning up deleted photos from database...")
        deleted_count = self.db.remove_deleted_photos(all_image_files)
        if deleted_count > 0:
            self.api.update_status(f"Removed {deleted_count} deleted photos from database")
        
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
                (photo_id,)
            ).fetchone()
            
            if not status_row:
                self.api.update_status(f"ERROR: Photo record not found after insert - {os.path.basename(file_path)}")
                return
            
            existing_status = status_row[0]
            
            if existing_status == 'completed':
                return
            
            image = cv2.imread(file_path)
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
                self.db.add_face(photo_id, embedding_norm)
            
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
    def __init__(self, location: str, threshold: float):
        self._location = location
        self._threshold = threshold
        
        script_dir = Path(__file__).parent.resolve()
        db_path = script_dir / "face_data"
        print(f"Database location: {db_path}")
        
        self._db = FaceDatabase(str(db_path))
        self._window = None
        self._scan_worker = None
        self._cluster_worker = None
        self._tray_icon = None
        self._close_to_tray = True
        self._quit_flag = False
        self._dynamic_resources = True
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
        
        should_recalibrate = new_photos_found or not has_existing_clustering
        
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
            self._scan_worker = ScanWorker(self._db, self._location, self)
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
    
    def recalibrate(self, threshold):
        self._threshold = threshold
        self.start_clustering()
    
    def get_people(self):
        clustering = self._db.get_active_clustering()
        if not clustering:
            return []
        
        persons = self._db.get_persons_in_clustering(clustering['clustering_id'])
        result = []
        
        for person in persons:
            person_id = person['person_id']
            face_count = person['face_count']
            
            name = f"Person {person_id}" if person_id > 0 else "Unmatched Faces"
            result.append({
                'id': person_id,
                'name': name,
                'count': face_count,
                'clustering_id': clustering['clustering_id']
            })
        
        return result
    
    def get_photos(self, clustering_id, person_id):
        photo_paths = self._db.get_photos_by_person(clustering_id, person_id)
        photos = []
        
        for path in photo_paths:
            thumbnail = self.create_thumbnail(path)
            if thumbnail:
                photos.append({
                    'path': path,
                    'thumbnail': thumbnail,
                    'name': os.path.basename(path)
                })
        
        return photos
    
    def create_thumbnail(self, image_path: str, size: int = 150) -> Optional[str]:
        try:
            img = Image.open(image_path)
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            img_rgb = img.convert('RGB')
            
            from io import BytesIO
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
        if enabled:
            self.update_status("Dynamic resource management enabled - will throttle when in background")
        else:
            self.update_status("Dynamic resource management disabled - full speed always")
    
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
    parser = argparse.ArgumentParser(description='Face Recognition Photo Organizer')
    parser.add_argument('-threshold', type=int, required=True, 
                       help='Recognition threshold (0-100, recommended: 30-50)')
    parser.add_argument('-location', type=str, required=True,
                       help='Root folder containing photos')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.location):
        print(f"Error: Location '{args.location}' does not exist")
        sys.exit(1)
    
    if args.threshold < 0 or args.threshold > 100:
        print("Error: Threshold must be between 0 and 100")
        sys.exit(1)
    
    print("=" * 60)
    print("Face Recognition Photo Organizer")
    print("=" * 60)
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {GPU_AVAILABLE}")
    if GPU_AVAILABLE:
        print(f"CUDA version: {torch.version.cuda}")
        print(f"GPU device: {torch.cuda.get_device_name(0)}")
    print(f"Scan location: {args.location}")
    print(f"Initial threshold: {args.threshold}%")
    print("=" * 60)
    
    api = API(args.location, args.threshold)
    
    window = webview.create_window(
        'Face Recognition Photo Organizer',
        'ui.html',
        js_api=api,
        width=1200,
        height=800,
        resizable=True,
        frameless=True
    )
    
    api.set_window(window)
    
    webview.start(debug=False)
    
    api.close()


if __name__ == "__main__":
    main()
