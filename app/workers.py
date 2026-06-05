import os
import shutil
import hashlib
import time
import threading
import fnmatch
import random
from pathlib import Path
from typing import Optional, Tuple, List
import numpy as np
import cv2
from PIL import Image, ImageOps
from insightface.app import FaceAnalysis
import networkx as nx
import torch

from utils import get_insightface_root
from metadata import read_photo_metadata

GPU_AVAILABLE = torch.cuda.is_available()
DEVICE = torch.device('cuda' if GPU_AVAILABLE else 'cpu')


class ScanWorker(threading.Thread):
    def __init__(self, db, api):
        super().__init__()
        self.db = db
        self.api = api
        self.face_app = None
        self.daemon = True
        self.batch_size = 25
    
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
        
        try:
            pil_image = Image.open(file_path)
            pil_image = ImageOps.exif_transpose(pil_image)
            image_rgb = np.array(pil_image.convert('RGB'))
            image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
            return image_bgr
            
        except Exception as e:
            self.api.update_status(f"ERROR: Cannot read image - {os.path.basename(file_path)}: {str(e)}")
            return None

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

        self.api.set_new_photos_found(len(new_photos) > 0)

        if len(photos_to_scan) == 0:
            self.api.update_status("No new photos to scan")
        else:
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

            self.api.update_status(f"Starting scan of {total} photos in batches of {self.batch_size}...")

            for batch_start in range(0, total, self.batch_size):
                batch_end = min(batch_start + self.batch_size, total)
                batch = photos_to_scan[batch_start:batch_end]

                self.process_batch(batch, scanned_count + batch_start, total_photos, new_photos)

                should_throttle = self.api.get_dynamic_resources() and not self.api.is_window_foreground()
                if should_throttle:
                    time.sleep(0.5)

        # Tell the UI the scan is done first, so the people list (and any clustering)
        # isn't blocked by a long first-time metadata pass.
        self.api.scan_complete()

        # If scan_complete kicked off a re-cluster, let it finish before the metadata
        # backfill writes. SQLite (even in WAL) allows only one writer; running the
        # backfill concurrently with the clustering save competed for that lock and
        # aborted clustering with "database is locked". Clustering is the priority.
        self.api.wait_for_active_clustering()

        # Fold-in metadata backfill (F2): read metadata for already-completed photos that
        # don't have it yet, with no re-detection. Runs after clustering so it proceeds
        # in the background on this worker thread; it's resumable (meta_version) and runs
        # every scan until the whole library is captured, then finds nothing to do.
        self.backfill_metadata()

    def backfill_metadata(self):
        """Read filesystem + EXIF metadata for completed photos missing it (no face
        detection). Commits in batches and honors the dynamic-resource throttle. This is
        how libraries scanned before metadata capture existed get populated."""
        missing = self.db.get_photos_missing_metadata()
        if not missing:
            return

        total = len(missing)
        self.api.update_status(f"Reading metadata for {total} photos (no re-detection needed)...")

        processed = 0
        for photo_id, file_path in missing:
            if os.path.exists(file_path):
                try:
                    hot, eav = read_photo_metadata(file_path)
                    self.db.update_photo_metadata(photo_id, hot, eav)
                except Exception as e:
                    self.api.update_status(
                        f"WARNING: metadata read failed - {os.path.basename(file_path)}: {e}")

            processed += 1

            if processed % 100 == 0 or processed == total:
                self.db.conn.commit()
                self.api.update_progress(processed, total, label="Reading metadata")
            if processed % 1000 == 0:
                self.api.update_status(f"Metadata: {processed}/{total}")

            if self.api.get_dynamic_resources() and not self.api.is_window_foreground():
                time.sleep(0.005)

        self.db.conn.commit()
        self.api.update_status(f"Metadata read complete: {total} photos")
    
    def process_batch(self, batch: List[str], start_idx: int, total_photos: int, new_photos: set):
        batch_data = []
        
        for idx, file_path in enumerate(batch):
            current_overall = start_idx + idx + 1
            self.api.update_progress(current_overall, total_photos)
            
            is_new = file_path in new_photos
            status_prefix = "NEW" if is_new else "RETRY"
            
            if (idx + 1) % 5 == 0 or idx == 0 or (idx + 1) == len(batch):
                self.api.update_status(f"Scanning {status_prefix}: {os.path.basename(file_path)} (batch {idx + 1}/{len(batch)})")
            
            photo_data = self.process_photo_no_commit(file_path)
            if photo_data:
                batch_data.append(photo_data)
        
        if batch_data:
            self.commit_batch(batch_data)
    
    def process_photo_no_commit(self, file_path: str) -> Optional[dict]:
        try:
            if not os.path.exists(file_path):
                self.api.update_status(f"ERROR: File not found - {os.path.basename(file_path)}")
                return {'file_path': file_path, 'status': 'error', 'faces': []}
            
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            
            photo_id = self.db.add_photo(file_path, file_hash)
            
            if not photo_id:
                self.api.update_status(f"ERROR: Failed to add photo to database - {os.path.basename(file_path)}")
                return None
            
            status_row = self.db.conn.execute(
                'SELECT scan_status FROM photos WHERE photo_id = ?', 
                (photo_id,)
            ).fetchone()
            
            if not status_row:
                self.api.update_status(f"ERROR: Photo record not found - {os.path.basename(file_path)}")
                return None
            
            existing_status = status_row[0]
            
            if existing_status == 'completed':
                return None
            
            image = self.load_image(file_path)
            if image is None:
                self.api.update_status(f"ERROR: Cannot read image - {os.path.basename(file_path)}")
                return {'file_path': file_path, 'photo_id': photo_id, 'status': 'error', 'faces': []}
            
            faces = self.face_app.get(image)
            
            if len(faces) == 0:
                self.api.update_status(f"INFO: No faces detected - {os.path.basename(file_path)}")
            else:
                self.api.update_status(f"INFO: Found {len(faces)} face(s) - {os.path.basename(file_path)}")
            
            face_data = []
            for face in faces:
                embedding = face.embedding
                embedding_norm = embedding / np.linalg.norm(embedding)
                bbox = face.bbox.tolist()
                face_data.append({'embedding': embedding_norm, 'bbox': bbox})

            # Capture photo metadata (F2) while we have the file open. Dimensions come
            # from the already-decoded image so there's no second decode.
            h, w = image.shape[:2]
            hot, eav = read_photo_metadata(file_path, width=w, height=h)

            return {
                'file_path': file_path,
                'photo_id': photo_id,
                'status': 'completed',
                'faces': face_data,
                'metadata': (hot, eav)
            }
            
        except Exception as e:
            self.api.update_status(f"ERROR: Exception processing {os.path.basename(file_path)}: {str(e)}")
            return {'file_path': file_path, 'photo_id': photo_id if 'photo_id' in locals() else None, 'status': 'error', 'faces': []}
    
    def commit_batch(self, batch_data: List[dict]):
        try:
            cursor = self.db.conn.cursor()
            
            for photo_data in batch_data:
                photo_id = photo_data['photo_id']

                for face_data in photo_data['faces']:
                    face_id = self.db.add_face(photo_id, face_data['embedding'], face_data['bbox'])

                self.db.update_photo_status(photo_id, photo_data['status'])

                if photo_data.get('metadata'):
                    hot, eav = photo_data['metadata']
                    self.db.update_photo_metadata(photo_id, hot, eav)

            self.db.conn.commit()
            
        except Exception as e:
            self.api.update_status(f"ERROR: Batch commit failed: {str(e)}")
            self.db.conn.rollback()
            
            for photo_data in batch_data:
                if photo_data.get('photo_id'):
                    try:
                        self.db.update_photo_status(photo_data['photo_id'], 'error')
                        self.db.conn.commit()
                    except:
                        pass


class ClusterWorker(threading.Thread):
    def __init__(self, db, threshold: float, api):
        super().__init__()
        self.db = db
        self.threshold = threshold / 100.0
        self.api = api
        self.daemon = True
        self.min_edge_weight = self.threshold + 0.05
        self.max_iterations = 25
    
    def run(self):
        try:
            self.api.update_status("Loading embeddings...")
            face_ids, embeddings = self.db.get_all_embeddings()
            
            if len(embeddings) == 0:
                self.api.update_status("No faces found")
                return
            
            old_clustering = self.db.get_active_clustering()
            old_clustering_id = old_clustering['clustering_id'] if old_clustering else None
            
            hidden_face_ids = set()
            if old_clustering_id:
                self.api.update_status("Saving hidden persons...")
                hidden_person_ids = self.db.get_hidden_persons(old_clustering_id)
                
                for person_id in hidden_person_ids:
                    person_face_ids = self.db.get_face_ids_for_person(old_clustering_id, person_id)
                    hidden_face_ids.update(person_face_ids)
                    
                    name = self.db.get_person_name_fast(old_clustering_id, person_id)
                    self.api.update_status(f"  Hidden person to preserve: {name} ({len(person_face_ids)} faces)")
                
                self.api.update_status(f"Total hidden faces to track: {len(hidden_face_ids)}")
            
            self.api.update_status(f"Clustering {len(embeddings)} faces with Chinese Whispers...")
            
            person_ids, confidences, embeddings_norm = self.cluster_with_pytorch(embeddings)
            
            self.api.update_status("Merging clusters by existing tags...")
            person_ids = self.merge_by_tags(face_ids, person_ids)
            
            self.api.update_status("Saving clustering...")
            clustering_id = self.db.create_clustering(self.threshold * 100)
            self.db.save_cluster_assignments(clustering_id, face_ids, person_ids, confidences)
            
            self.api.update_status("Applying tags to new faces...")
            self.apply_tags_to_clusters(clustering_id, face_ids, person_ids)
            
            if hidden_face_ids:
                self.api.update_status("Restoring hidden persons...")
                self.restore_hidden_persons(clustering_id, face_ids, person_ids, hidden_face_ids)
            
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
    
    def restore_hidden_persons(self, clustering_id: int, face_ids: List[int], person_ids: List[int], hidden_face_ids: set):
        new_person_ids_to_hide = set()
        
        for idx, face_id in enumerate(face_ids):
            if face_id in hidden_face_ids:
                new_person_id = person_ids[idx]
                if new_person_id > 0:
                    new_person_ids_to_hide.add(new_person_id)
        
        for person_id in new_person_ids_to_hide:
            name = self.db.get_person_name_fast(clustering_id, person_id)
            self.db.hide_person(clustering_id, person_id)
            self.api.update_status(f"  Restored hidden status for: {name} (person_id={person_id})")
        
        self.api.update_status(f"Hidden {len(new_person_ids_to_hide)} persons after reclustering")
    
    def cluster_with_pytorch(self, embeddings: np.ndarray) -> Tuple[List[int], List[float], torch.Tensor]:
        n_faces = len(embeddings)
        
        device_name = "GPU" if GPU_AVAILABLE else "CPU"
        self.api.update_status(f"Using {device_name} for clustering...")
        
        embeddings_tensor = torch.tensor(embeddings, dtype=torch.float32).to(DEVICE)
        
        self.api.update_status("Normalizing embeddings...")
        embeddings_norm = embeddings_tensor / embeddings_tensor.norm(dim=1, keepdim=True)
        
        batch_size = 1000
        n_batches = (n_faces + batch_size - 1) // batch_size
        
        self.api.update_status("Building similarity graph...")
        
        adjacency = {}
        edge_count = 0
        
        for i in range(n_batches):
            start_i = i * batch_size
            end_i = min((i + 1) * batch_size, n_faces)
            batch_i = embeddings_norm[start_i:end_i]
            
            similarities = torch.mm(batch_i, embeddings_norm.T)
            similarities_cpu = similarities.cpu().numpy()
            
            for local_idx, global_idx in enumerate(range(start_i, end_i)):
                similar_indices = np.where(similarities_cpu[local_idx] >= self.min_edge_weight)[0]
                
                neighbors = {}
                for j in similar_indices:
                    if global_idx != j:
                        weight = float(similarities_cpu[local_idx, j])
                        neighbors[int(j)] = weight
                        edge_count += 1
                
                if neighbors:
                    adjacency[global_idx] = neighbors
            
            if (i + 1) % 10 == 0 or i == n_batches - 1:
                self.api.update_status(f"Graph building: batch {i+1}/{n_batches}")
        
        self.api.update_status(f"Graph built: {len(adjacency)} nodes, {edge_count} edges")
        
        labels = list(range(n_faces))
        
        self.api.update_status("Running Chinese Whispers clustering...")
        
        for iteration in range(self.max_iterations):
            changes = 0
            node_order = list(range(n_faces))
            random.shuffle(node_order)
            
            for node in node_order:
                if node not in adjacency:
                    continue
                
                neighbors = adjacency[node]
                if not neighbors:
                    continue
                
                label_weights = {}
                for neighbor, weight in neighbors.items():
                    neighbor_label = labels[neighbor]
                    label_weights[neighbor_label] = label_weights.get(neighbor_label, 0) + weight
                
                if label_weights:
                    best_label = max(label_weights.items(), key=lambda x: x[1])[0]
                    
                    if labels[node] != best_label:
                        labels[node] = best_label
                        changes += 1
            
            if (i + 1) % 5 == 0 or i == n_batches - 1:
                self.api.update_status(f"Iteration {iteration+1}/{self.max_iterations}: {changes} changes")
            
            if changes < n_faces * 0.001:
                self.api.update_status(f"Converged after {iteration+1} iterations")
                break
        
        self.api.update_status("Validating clusters...")
        
        unique_labels = set(labels)
        label_mapping = {old: new for new, old in enumerate(sorted(unique_labels), start=1)}
        
        person_ids = [0] * n_faces
        confidences = [0.0] * n_faces
        rejected = 0
        
        for old_label in unique_labels:
            cluster_indices = [i for i, l in enumerate(labels) if l == old_label]
            
            if len(cluster_indices) == 1:
                person_ids[cluster_indices[0]] = 0
                confidences[cluster_indices[0]] = 0.0
                continue
            
            cluster_embeddings = embeddings_norm[cluster_indices]
            centroid = cluster_embeddings.mean(dim=0)
            centroid = centroid / centroid.norm()
            
            similarities_to_centroid = torch.mv(cluster_embeddings, centroid)
            
            new_person_id = label_mapping[old_label]
            
            for idx, face_idx in enumerate(cluster_indices):
                centroid_sim = float(similarities_to_centroid[idx])
                
                if centroid_sim >= self.threshold:
                    person_ids[face_idx] = new_person_id
                    confidences[face_idx] = centroid_sim
                else:
                    person_ids[face_idx] = 0
                    confidences[face_idx] = 0.0
                    rejected += 1
        
        self.api.update_status(f"Validation complete: {rejected} faces rejected")
        
        return person_ids, confidences, embeddings_norm
    
    def merge_by_tags(self, face_ids: List[int], person_ids: List[int]) -> List[int]:
        cursor = self.db.conn.cursor()
        
        cursor.execute('SELECT face_id, tag_name FROM face_tags')
        all_tags = {row[0]: row[1] for row in cursor.fetchall()}
        
        if not all_tags:
            return person_ids
        
        self.api.update_status(f"Found {len(all_tags)} tagged faces")
        
        tag_to_clusters = {}
        
        for idx, face_id in enumerate(face_ids):
            if face_id in all_tags:
                tag_name = all_tags[face_id]
                cluster_id = person_ids[idx]
                
                if cluster_id == 0:
                    continue
                
                if tag_name not in tag_to_clusters:
                    tag_to_clusters[tag_name] = {}
                
                if cluster_id not in tag_to_clusters[tag_name]:
                    tag_to_clusters[tag_name][cluster_id] = 0
                tag_to_clusters[tag_name][cluster_id] += 1
        
        cluster_mapping = {}
        
        for tag_name, cluster_counts in tag_to_clusters.items():
            clusters = list(cluster_counts.keys())
            
            if len(clusters) > 1:
                sorted_clusters = sorted(clusters, key=lambda c: cluster_counts[c], reverse=True)
                target_cluster = sorted_clusters[0]
                
                self.api.update_status(f"Tag '{tag_name}': merging {len(clusters)} clusters into {target_cluster}")
                
                for cluster_id in clusters:
                    if cluster_id != target_cluster:
                        cluster_mapping[cluster_id] = target_cluster
        
        if not cluster_mapping:
            return person_ids
        
        merged_person_ids = [cluster_mapping.get(pid, pid) for pid in person_ids]
        
        return merged_person_ids
    
    def apply_tags_to_clusters(self, clustering_id: int, face_ids: List[int], person_ids: List[int]):
        cursor = self.db.conn.cursor()
        
        cursor.execute('SELECT face_id, tag_name FROM face_tags')
        all_tags = {row[0]: row[1] for row in cursor.fetchall()}
        
        if not all_tags:
            return
        
        cluster_to_tag = {}
        
        for idx, face_id in enumerate(face_ids):
            if face_id in all_tags:
                cluster_id = person_ids[idx]
                tag_name = all_tags[face_id]
                
                if cluster_id == 0:
                    continue
                
                if cluster_id not in cluster_to_tag:
                    cluster_to_tag[cluster_id] = {}
                
                if tag_name not in cluster_to_tag[cluster_id]:
                    cluster_to_tag[cluster_id][tag_name] = 0
                cluster_to_tag[cluster_id][tag_name] += 1
        
        for cluster_id, tag_counts in cluster_to_tag.items():
            dominant_tag = max(tag_counts.items(), key=lambda x: x[1])[0]
            
            cluster_face_ids = [face_ids[idx] for idx, pid in enumerate(person_ids) if pid == cluster_id]
            
            untagged_faces = [fid for fid in cluster_face_ids if fid not in all_tags]
            
            if untagged_faces:
                self.db.tag_faces(untagged_faces, dominant_tag, is_manual=False)
                self.api.update_status(f"Auto-tagged {len(untagged_faces)} faces as '{dominant_tag}'")


class ExportWorker(threading.Thread):
    """Copies (or hardlinks) photos into per-person subfolders under a destination
    the user picks. Originals are never moved, renamed, or modified.

    scope:
        'person'    - export a single person_id (folder named after that person)
        'selected'  - export the given list of person_ids
        'all_named' - export every named person, skipping auto "Person X",
                      "Unmatched Faces", and persons the user has hidden
    mode:
        'copy'     - shutil.copy2 (works across any volume)
        'hardlink' - os.link on the same volume; falls back to copy across volumes
    """

    INVALID_CHARS = set('<>:"/\\|?*')

    def __init__(self, db, api, dest_folder, scope, clustering_id,
                 person_id=None, person_ids=None, mode='copy', show_hidden_photos=False):
        super().__init__()
        self.db = db
        self.api = api
        self.dest_folder = dest_folder
        self.scope = scope
        self.clustering_id = clustering_id
        self.person_id = person_id
        self.person_ids = person_ids or []
        self.mode = mode if mode in ('copy', 'hardlink') else 'copy'
        self.show_hidden_photos = show_hidden_photos
        self.daemon = True
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def sanitize_folder_name(self, name: str) -> str:
        """Port of organise.cpp SanitizeFolderName: swap path-illegal characters for
        underscores and drop trailing spaces/dots (both invalid on Windows)."""
        cleaned = ''.join('_' if c in self.INVALID_CHARS else c for c in name)
        cleaned = cleaned.rstrip(' .')
        return cleaned or 'Unnamed'

    def _long_path(self, path: str) -> str:
        r"""Prefix an absolute Windows path with \\?\ so paths over 260 chars work.
        No-op on non-Windows and on already-prefixed paths."""
        if os.name != 'nt':
            return path
        abs_path = os.path.abspath(path)
        if abs_path.startswith('\\\\?\\'):
            return abs_path
        if abs_path.startswith('\\\\'):
            # UNC share \\server\share -> \\?\UNC\server\share
            return '\\\\?\\UNC\\' + abs_path[2:]
        return '\\\\?\\' + abs_path

    def build_export_map(self) -> dict:
        """Return {person_name: [source_path, ...]} for the requested scope. Hidden
        faces are filtered out (unless show_hidden_photos). Files are deduped twice
        (F3): a collage of one person exports as a single file (not one per face), and
        exact duplicates - identical bytes at different paths, same file_hash - export
        once, keeping the shortest path."""
        hidden_faces = set() if self.show_hidden_photos else self.db.get_hidden_photos()

        if self.scope == 'person':
            person_ids = [self.person_id]
        elif self.scope == 'selected':
            # Exactly what the user picked; the picker already applied visibility rules.
            person_ids = list(self.person_ids)
        else:
            hidden_persons = self.db.get_hidden_persons(self.clustering_id)
            person_ids = [
                p['person_id'] for p in self.db.get_persons_in_clustering(self.clustering_id)
                if p['person_id'] not in hidden_persons
            ]

        # Keyed by display name so merged clusters that share a name land in one folder.
        # Per name we dedupe by file_hash (keeping the shortest path) so exact-duplicate
        # files export once; photos with no hash fall back to a path set (collage dedup
        # alone, since one file = one path).
        name_to_files = {}
        for pid in person_ids:
            if pid == 0:  # Unmatched Faces is a grab-bag, not a real person
                continue

            name = self.db.get_person_name_fast(self.clustering_id, pid).replace(' (hidden)', '')

            if self.scope == 'all_named' and (name.startswith('Person ') or name == 'Unmatched Faces'):
                continue

            files = name_to_files.setdefault(name, {'by_hash': {}, 'no_hash': set()})
            for photo in self.db.get_photos_by_person(self.clustering_id, pid):
                if photo['face_id'] in hidden_faces:
                    continue
                path = photo['file_path']
                file_hash = photo.get('file_hash')
                if file_hash:
                    current = files['by_hash'].get(file_hash)
                    if current is None or (len(path), path) < (len(current), current):
                        files['by_hash'][file_hash] = path
                else:
                    files['no_hash'].add(path)

        result = {}
        for name, files in name_to_files.items():
            paths = set(files['by_hash'].values()) | files['no_hash']
            if paths:
                result[name] = sorted(paths)
        return result

    def _is_same_file(self, src_lp: str, dest_lp: str) -> bool:
        """Decide whether dest is already a copy of src, so a re-run (e.g. after a
        crash mid-export) skips it instead of making a duplicate. Hardlinks share an
        inode (samefile). shutil.copy2 preserves size and mtime, so for copies an
        equal size plus mtime within 2s (covers FAT/exFAT mtime resolution) means it
        was already exported."""
        try:
            if os.path.samefile(src_lp, dest_lp):
                return True
        except OSError:
            pass
        try:
            s = os.stat(src_lp)
            d = os.stat(dest_lp)
            return s.st_size == d.st_size and abs(s.st_mtime - d.st_mtime) <= 2
        except OSError:
            return False

    def export_one(self, src: str, person_folder: str) -> str:
        """Copy or hardlink one file into person_folder. Returns 'exported',
        'skipped_exists' (already present from a prior run), 'missing', or 'failed'.

        The name/_1/_2 chain is walked checking identity at each step: if a
        candidate name already holds this exact file it is skipped (idempotent
        resume); if it holds a different file the next suffix is tried (genuine
        collision between two sources that share a basename)."""
        src_lp = self._long_path(src)
        if not os.path.exists(src_lp):
            self.api.update_status(f"WARNING: Source missing - {src}")
            return 'missing'

        filename = os.path.basename(src)
        stem, ext = os.path.splitext(filename)
        candidate = os.path.join(person_folder, filename)

        dup = 1
        while os.path.exists(self._long_path(candidate)):
            if self._is_same_file(src_lp, self._long_path(candidate)):
                return 'skipped_exists'
            candidate = os.path.join(person_folder, f"{stem}_{dup}{ext}")
            dup += 1

        try:
            dest_lp = self._long_path(candidate)
            if self.mode == 'hardlink':
                try:
                    os.link(src_lp, dest_lp)
                except OSError:
                    # cross-volume, or a filesystem without hardlink support
                    shutil.copy2(src_lp, dest_lp)
            else:
                shutil.copy2(src_lp, dest_lp)
            return 'exported'
        except Exception as e:
            self.api.update_status(f"ERROR: Failed to export {filename}: {e}")
            return 'failed'

    def _finish(self, summary: dict):
        self.api.export_complete(summary)

    def run(self):
        try:
            self.api.update_status("Preparing export...")
            export_map = self.build_export_map()

            people_count = len(export_map)
            total = sum(len(paths) for paths in export_map.values())

            if total == 0:
                self.api.update_status("Export: nothing to export")
                self._finish({'exported': 0, 'skipped_missing': 0, 'failed': 0,
                              'people': 0, 'cancelled': False, 'dest': self.dest_folder})
                return

            self.api.update_status(
                f"Exporting {total} photos for {people_count} "
                f"{'person' if people_count == 1 else 'people'} (mode: {self.mode})...")

            try:
                os.makedirs(self.dest_folder, exist_ok=True)
            except Exception as e:
                self.api.update_status(f"ERROR: Cannot create destination folder: {e}")
                self._finish({'exported': 0, 'skipped_missing': 0, 'failed': total,
                              'people': people_count, 'cancelled': False,
                              'dest': self.dest_folder, 'error': str(e)})
                return

            exported = skipped_missing = skipped_exists = failed = processed = 0
            cancelled = False

            for name, paths in export_map.items():
                if self._cancel.is_set():
                    cancelled = True
                    break

                person_folder = os.path.join(self.dest_folder, self.sanitize_folder_name(name))
                try:
                    os.makedirs(person_folder, exist_ok=True)
                except Exception as e:
                    self.api.update_status(f"ERROR: Cannot create folder for '{name}': {e}")
                    failed += len(paths)
                    processed += len(paths)
                    self.api.update_progress(processed, total, label="Exporting")
                    continue

                for src in paths:
                    if self._cancel.is_set():
                        cancelled = True
                        break

                    processed += 1
                    result = self.export_one(src, person_folder)
                    if result == 'exported':
                        exported += 1
                    elif result == 'skipped_exists':
                        skipped_exists += 1
                    elif result == 'missing':
                        skipped_missing += 1
                    else:
                        failed += 1

                    if processed % 10 == 0 or processed == total:
                        self.api.update_progress(processed, total, label="Exporting")

                if cancelled:
                    break

            summary = {
                'exported': exported,
                'skipped_exists': skipped_exists,
                'skipped_missing': skipped_missing,
                'failed': failed,
                'people': people_count,
                'cancelled': cancelled,
                'dest': self.dest_folder,
            }
            status = "Export cancelled" if cancelled else "Export complete"
            self.api.update_status(
                f"{status}: {exported} exported, {skipped_exists} already present, "
                f"{skipped_missing} missing, {failed} failed")
            self._finish(summary)

        except Exception as e:
            self.api.update_status(f"ERROR: Export failed: {e}")
            import traceback
            traceback.print_exc()
            self._finish({'exported': 0, 'skipped_missing': 0, 'failed': 0,
                          'people': 0, 'cancelled': False,
                          'dest': self.dest_folder, 'error': str(e)})