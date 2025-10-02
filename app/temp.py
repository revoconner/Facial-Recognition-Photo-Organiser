import sys
import os
import argparse
import sqlite3
import lmdb
import pickle
import hashlib
from pathlib import Path
from typing import List, Optional, Tuple
import numpy as np
import cv2
from insightface.app import FaceAnalysis
from PIL import Image
import networkx as nx
import torch

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QListWidget, QLabel, QProgressBar,
                             QListWidgetItem, QSplitter, QPushButton, QSlider,
                             QCheckBox, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QIcon


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
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_assign ON cluster_assignments(clustering_id, person_id)')
        
        self.conn.commit()
    
    def add_photo(self, file_path: str, file_hash: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO photos (file_path, file_hash)
            VALUES (?, ?)
        ''', (file_path, file_hash))
        self.conn.commit()
        return cursor.lastrowid if cursor.lastrowid else self.get_photo_id(file_path)
    
    def get_photo_id(self, file_path: str) -> Optional[int]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT photo_id FROM photos WHERE file_path = ?', (file_path,))
        row = cursor.fetchone()
        return row[0] if row else None
    
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
    
    def close(self):
        self.conn.close()
        self.env.close()


class ScanWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal()
    log = pyqtSignal(str)
    
    def __init__(self, db: FaceDatabase, location: str):
        super().__init__()
        self.db = db
        self.location = location
        self.face_app = None
    
    def run(self):
        try:
            self.log.emit("Initializing InsightFace model...")
            self.face_app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
            self.face_app.prepare(ctx_id=-1, det_size=(640, 640))
            self.log.emit("Model loaded")
        except Exception as e:
            self.log.emit(f"Error loading model: {e}")
            self.finished.emit()
            return
        
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}
        image_files = []
        
        self.log.emit(f"Scanning folder...")
        for root, dirs, files in os.walk(self.location):
            for file in files:
                if Path(file).suffix.lower() in image_extensions:
                    image_files.append(os.path.join(root, file))
        
        total = len(image_files)
        self.log.emit(f"Found {total} images")
        
        for idx, file_path in enumerate(image_files):
            self.progress.emit(idx + 1, total)
            self.process_photo(file_path)
        
        self.finished.emit()
    
    def process_photo(self, file_path: str):
        try:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            
            photo_id = self.db.add_photo(file_path, file_hash)
            
            existing_status = self.db.conn.execute(
                'SELECT scan_status FROM photos WHERE photo_id = ?', 
                (photo_id,)
            ).fetchone()[0]
            
            if existing_status == 'completed':
                return
            
            image = cv2.imread(file_path)
            if image is None:
                self.db.update_photo_status(photo_id, 'error')
                return
            
            faces = self.face_app.get(image)
            
            for face in faces:
                embedding = face.embedding
                embedding_norm = embedding / np.linalg.norm(embedding)
                self.db.add_face(photo_id, embedding_norm)
            
            self.db.update_photo_status(photo_id, 'completed')
            
        except Exception as e:
            self.log.emit(f"Error: {os.path.basename(file_path)}")
            if 'photo_id' in locals():
                self.db.update_photo_status(photo_id, 'error')


class ClusterWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    
    def __init__(self, db: FaceDatabase, threshold: float):
        super().__init__()
        self.db = db
        self.threshold = threshold / 100.0
    
    def run(self):
        try:
            self.progress.emit("Loading embeddings...")
            face_ids, embeddings = self.db.get_all_embeddings()
            
            if len(embeddings) == 0:
                self.progress.emit("No faces found")
                self.finished.emit()
                return
            
            self.progress.emit(f"Clustering {len(embeddings)} faces with PyTorch...")
            
            person_ids, confidences = self.cluster_with_pytorch(embeddings)
            
            self.progress.emit("Saving clustering...")
            clustering_id = self.db.create_clustering(self.threshold * 100)
            self.db.save_cluster_assignments(clustering_id, face_ids, person_ids, confidences)
            
            unique_persons = len(set(person_ids))
            self.progress.emit(f"Complete: {unique_persons} persons")
            self.finished.emit()
            
        except Exception as e:
            self.progress.emit(f"Error: {str(e)}")
            self.finished.emit()
    
    def cluster_with_pytorch(self, embeddings: np.ndarray) -> Tuple[List[int], List[float]]:
        n_faces = len(embeddings)
        
        device_name = "GPU" if GPU_AVAILABLE else "CPU"
        self.progress.emit(f"Using {device_name} for clustering...")
        
        embeddings_tensor = torch.tensor(embeddings, dtype=torch.float32).to(DEVICE)
        
        self.progress.emit("Normalizing embeddings...")
        embeddings_norm = embeddings_tensor / embeddings_tensor.norm(dim=1, keepdim=True)
        
        batch_size = 1000
        n_batches = (n_faces + batch_size - 1) // batch_size
        
        self.progress.emit("Computing similarity matrix...")
        
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
                self.progress.emit(f"Processing batch {i+1}/{n_batches}...")
        
        self.progress.emit("Finding connected components...")
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


class MainWindow(QMainWindow):
    def __init__(self, location: str, threshold: float):
        super().__init__()
        self.location = location
        self.threshold = threshold
        self.db = FaceDatabase("./face_data")
        
        self.setWindowTitle("Face Recognition Photo Organizer (PyTorch)")
        self.setGeometry(100, 100, 1200, 800)
        
        self.setup_ui()
        self.check_scan_status()
    
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(5)
        
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(3)
        
        status_layout = QHBoxLayout()
        self.status_label = QLabel(f"Initializing...")
        self.status_label.setStyleSheet("font-size: 11px;")
        status_layout.addWidget(self.status_label)
        
        self.log_label = QLabel("")
        self.log_label.setStyleSheet("color: #666; font-size: 10px;")
        self.log_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        status_layout.addWidget(self.log_label, 1)
        
        top_layout.addLayout(status_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(15)
        top_layout.addWidget(self.progress_bar)
        
        controls_layout = QHBoxLayout()
        
        threshold_label = QLabel(f"Threshold: {self.threshold}%")
        threshold_label.setStyleSheet("font-size: 11px;")
        controls_layout.addWidget(threshold_label)
        
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setMinimum(10)
        self.threshold_slider.setMaximum(90)
        self.threshold_slider.setValue(int(self.threshold))
        self.threshold_slider.setEnabled(False)
        self.threshold_slider.valueChanged.connect(lambda v: threshold_label.setText(f"Threshold: {v}%"))
        controls_layout.addWidget(self.threshold_slider, 1)
        
        self.cluster_button = QPushButton("Re-cluster")
        self.cluster_button.setEnabled(False)
        self.cluster_button.clicked.connect(self.start_clustering)
        controls_layout.addWidget(self.cluster_button)
        
        self.show_unmatched_checkbox = QCheckBox("Show unmatched faces")
        self.show_unmatched_checkbox.setChecked(True)
        self.show_unmatched_checkbox.setStyleSheet("font-size: 11px;")
        self.show_unmatched_checkbox.stateChanged.connect(self.load_persons)
        controls_layout.addWidget(self.show_unmatched_checkbox)
        
        top_layout.addLayout(controls_layout)
        
        layout.addWidget(top_widget)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)
        
        person_header = QLabel("Persons")
        person_header.setStyleSheet("font-weight: bold; font-size: 13px;")
        left_layout.addWidget(person_header)
        
        self.person_list = QListWidget()
        self.person_list.currentItemChanged.connect(self.on_person_selected)
        left_layout.addWidget(self.person_list)
        
        splitter.addWidget(left_widget)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)
        
        photo_header = QLabel("Photos (double-click to open)")
        photo_header.setStyleSheet("font-weight: bold; font-size: 13px;")
        right_layout.addWidget(photo_header)
        
        self.photo_list = QListWidget()
        self.photo_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.photo_list.setIconSize(QSize(150, 150))
        self.photo_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.photo_list.setSpacing(10)
        self.photo_list.setMovement(QListWidget.Movement.Static)
        self.photo_list.itemDoubleClicked.connect(self.on_photo_clicked)
        right_layout.addWidget(self.photo_list)
        
        splitter.addWidget(right_widget)
        
        splitter.setSizes([300, 900])
        layout.addWidget(splitter)
        
        gpu_status = "GPU Available" if GPU_AVAILABLE else "CPU Only"
        cuda_version = torch.version.cuda if GPU_AVAILABLE else "N/A"
        bottom_info = QLabel(f"PyTorch: {torch.__version__} | {gpu_status} | CUDA: {cuda_version}")
        bottom_info.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(bottom_info)
    
    def check_scan_status(self):
        total_faces = self.db.get_total_faces()
        
        if total_faces == 0:
            self.status_label.setText(f"Starting scan of {self.location}")
            self.start_scanning()
        else:
            active_clustering = self.db.get_active_clustering()
            if active_clustering:
                self.status_label.setText(f"Loaded: {total_faces} faces")
                self.progress_bar.hide()
                self.threshold_slider.setEnabled(True)
                self.cluster_button.setEnabled(True)
                self.load_persons()
            else:
                self.status_label.setText(f"Found {total_faces} faces, starting clustering...")
                self.start_clustering()
    
    def start_scanning(self):
        self.scan_worker = ScanWorker(self.db, self.location)
        self.scan_worker.progress.connect(self.update_scan_progress)
        self.scan_worker.finished.connect(self.scan_finished)
        self.scan_worker.log.connect(self.update_log)
        self.scan_worker.start()
    
    def update_scan_progress(self, current: int, total: int):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Scanning {current}/{total}")
    
    def update_log(self, message: str):
        self.log_label.setText(message)
    
    def scan_finished(self):
        total_faces = self.db.get_total_faces()
        self.status_label.setText(f"Scan complete: {total_faces} faces found")
        self.start_clustering()
    
    def start_clustering(self):
        threshold = self.threshold_slider.value()
        self.cluster_button.setEnabled(False)
        self.threshold_slider.setEnabled(False)
        
        self.cluster_worker = ClusterWorker(self.db, threshold)
        self.cluster_worker.progress.connect(self.update_cluster_progress)
        self.cluster_worker.finished.connect(self.cluster_finished)
        self.cluster_worker.start()
    
    def update_cluster_progress(self, message: str):
        self.status_label.setText(message)
    
    def cluster_finished(self):
        self.progress_bar.hide()
        self.threshold_slider.setEnabled(True)
        self.cluster_button.setEnabled(True)
        self.load_persons()
    
    def load_persons(self):
        self.person_list.clear()
        clustering = self.db.get_active_clustering()
        
        if not clustering:
            return
        
        persons = self.db.get_persons_in_clustering(clustering['clustering_id'])
        
        show_unmatched = self.show_unmatched_checkbox.isChecked()
        
        unmatched_count = 0
        matched_count = 0
        
        for person in persons:
            person_id = person['person_id']
            face_count = person['face_count']
            
            if person_id == 0:
                unmatched_count = face_count
                if not show_unmatched:
                    continue
                item_text = f"Unmatched Faces ({face_count} faces)"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, (clustering['clustering_id'], person_id))
                item.setForeground(Qt.GlobalColor.darkGray)
                self.person_list.addItem(item)
            else:
                matched_count += 1
                item_text = f"Person {person_id} ({face_count} faces)"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, (clustering['clustering_id'], person_id))
                self.person_list.addItem(item)
        
        if not show_unmatched and unmatched_count > 0:
            self.show_unmatched_checkbox.setText(f"Show unmatched faces ({unmatched_count})")
        else:
            self.show_unmatched_checkbox.setText("Show unmatched faces")
    
    def on_person_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        if current is None:
            return
        
        clustering_id, person_id = current.data(Qt.ItemDataRole.UserRole)
        self.load_photos(clustering_id, person_id)
    
    def create_thumbnail(self, image_path: str, size: int = 150) -> Optional[QPixmap]:
        try:
            img = Image.open(image_path)
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            img_rgb = img.convert('RGB')
            temp_path = f"temp_thumb_{hash(image_path)}.jpg"
            img_rgb.save(temp_path, 'JPEG')
            pixmap = QPixmap(temp_path)
            try:
                os.remove(temp_path)
            except:
                pass
            return pixmap
        except Exception as e:
            return None
    
    def load_photos(self, clustering_id: int, person_id: int):
        self.photo_list.clear()
        photos = self.db.get_photos_by_person(clustering_id, person_id)
        
        for photo_path in photos:
            pixmap = self.create_thumbnail(photo_path)
            
            if pixmap:
                item = QListWidgetItem()
                item.setIcon(QIcon(pixmap))
                item.setText(os.path.basename(photo_path))
                item.setData(Qt.ItemDataRole.UserRole, photo_path)
                item.setToolTip(photo_path)
                self.photo_list.addItem(item)
    
    def on_photo_clicked(self, item: QListWidgetItem):
        photo_path = item.data(Qt.ItemDataRole.UserRole)
        os.startfile(photo_path)
    
    def closeEvent(self, event):
        self.db.close()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description='Face Recognition Photo Organizer (PyTorch)')
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
    
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {GPU_AVAILABLE}")
    if GPU_AVAILABLE:
        print(f"CUDA version: {torch.version.cuda}")
        print(f"GPU device: {torch.cuda.get_device_name(0)}")
    
    app = QApplication(sys.argv)
    window = MainWindow(args.location, args.threshold)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()