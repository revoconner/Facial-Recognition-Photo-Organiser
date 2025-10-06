import os
import hashlib
import time
import threading
import fnmatch
from pathlib import Path
from typing import Optional, Tuple, List
import numpy as np
import cv2
from PIL import Image
from insightface.app import FaceAnalysis
import networkx as nx
import torch

from utils import get_insightface_root

GPU_AVAILABLE = torch.cuda.is_available()
DEVICE = torch.device('cuda' if GPU_AVAILABLE else 'cpu')


class ScanWorker(threading.Thread):
    def __init__(self, db, api):
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
                (photo_id,)
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
    def __init__(self, db, threshold: float, api):
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
