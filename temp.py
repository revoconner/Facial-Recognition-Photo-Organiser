import sys
import os
import argparse
import sqlite3
import lmdb
import pickle
import hashlib
from pathlib import Path
from typing import List, Optional
import numpy as np
import cv2
from insightface.app import FaceAnalysis
from PIL import Image

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QListWidget, QLabel, QProgressBar,
                             QListWidgetItem, QSplitter)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QIcon


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
            CREATE TABLE IF NOT EXISTS persons (
                person_id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_label TEXT NOT NULL,
                face_count INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS faces (
                face_id INTEGER PRIMARY KEY AUTOINCREMENT,
                photo_id INTEGER NOT NULL,
                person_id INTEGER,
                confidence_score REAL,
                FOREIGN KEY (photo_id) REFERENCES photos(photo_id),
                FOREIGN KEY (person_id) REFERENCES persons(person_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_status ON photos(scan_status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id)')
        
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
    
    def add_face(self, photo_id: int, embedding: np.ndarray, person_id: Optional[int] = None) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO faces (photo_id, person_id)
            VALUES (?, ?)
        ''', (photo_id, person_id))
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
    
    def get_all_person_embeddings(self, person_id: int) -> List[np.ndarray]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT face_id FROM faces WHERE person_id = ?', (person_id,))
        face_ids = [row[0] for row in cursor.fetchall()]
        
        embeddings = []
        for face_id in face_ids:
            embedding = self.get_face_embedding(face_id)
            if embedding is not None:
                embeddings.append(embedding)
        
        return embeddings
    
    def create_new_person(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM persons')
        count = cursor.fetchone()[0]
        
        label = f"Person {count + 1}"
        cursor.execute('INSERT INTO persons (person_label) VALUES (?)', (label,))
        self.conn.commit()
        return cursor.lastrowid
    
    def assign_face_to_person(self, face_id: int, person_id: int, confidence: float = None):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE faces 
            SET person_id = ?, confidence_score = ?
            WHERE face_id = ?
        ''', (person_id, confidence, face_id))
        
        cursor.execute('''
            UPDATE persons 
            SET face_count = (SELECT COUNT(*) FROM faces WHERE person_id = ?)
            WHERE person_id = ?
        ''', (person_id, person_id))
        
        self.conn.commit()
    
    def get_pending_photos(self) -> List[dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM photos 
            WHERE scan_status = 'pending'
        ''')
        return [dict(row) for row in cursor.fetchall()]
    
    def update_photo_status(self, photo_id: int, status: str):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE photos SET scan_status = ? WHERE photo_id = ?', 
                      (status, photo_id))
        self.conn.commit()
    
    def get_all_persons(self) -> List[dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM persons ORDER BY person_id')
        return [dict(row) for row in cursor.fetchall()]
    
    def get_photos_by_person(self, person_id: int) -> List[str]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT DISTINCT p.file_path
            FROM photos p
            JOIN faces f ON p.photo_id = f.photo_id
            WHERE f.person_id = ?
        ''', (person_id,))
        return [row[0] for row in cursor.fetchall()]
    
    def close(self):
        self.conn.close()
        self.env.close()


def cosine_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    return np.dot(embedding1, embedding2) / (np.linalg.norm(embedding1) * np.linalg.norm(embedding2))


def cosine_similarity_batch(embeddings: np.ndarray, target_embedding: np.ndarray) -> np.ndarray:
    embeddings_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    target_norm = target_embedding / np.linalg.norm(target_embedding)
    return np.dot(embeddings_norm, target_norm)


class FaceRecognitionWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal()
    log = pyqtSignal(str)
    
    def __init__(self, db: FaceDatabase, location: str, threshold: float):
        super().__init__()
        self.db = db
        self.location = location
        self.threshold = threshold / 100.0
        self.face_app = None
    
    def run(self):
        try:
            self.log.emit("Initializing InsightFace model...")
            self.face_app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
            self.face_app.prepare(ctx_id=-1, det_size=(640, 640))
            self.log.emit("Model loaded successfully")
        except Exception as e:
            self.log.emit(f"Error loading model: {e}")
            self.finished.emit()
            return
        
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}
        image_files = []
        
        self.log.emit(f"Scanning folder: {self.location}")
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
            
            if len(faces) == 0:
                self.db.update_photo_status(photo_id, 'completed')
                return
            
            for face in faces:
                embedding = face.embedding
                embedding_norm = embedding / np.linalg.norm(embedding)
                
                result = self.find_matching_person(embedding_norm)
                
                if result is None:
                    person_id = self.db.create_new_person()
                    similarity = 0.0
                    self.log.emit(f"Created Person {person_id} (no match found)")
                else:
                    person_id, similarity = result
                    self.log.emit(f"Matched to Person {person_id} (similarity: {similarity:.3f})")
                
                face_id = self.db.add_face(photo_id, embedding_norm, person_id)
                self.db.assign_face_to_person(face_id, person_id, similarity)
            
            self.db.update_photo_status(photo_id, 'completed')
            
        except Exception as e:
            self.log.emit(f"Error processing {os.path.basename(file_path)}: {str(e)}")
            if 'photo_id' in locals():
                self.db.update_photo_status(photo_id, 'error')
    
    def find_matching_person(self, embedding: np.ndarray) -> Optional[tuple]:
        persons = self.db.get_all_persons()
        
        best_match_person_id = None
        best_match_similarity = -1
        
        for person in persons:
            person_id = person['person_id']
            person_embeddings = self.db.get_all_person_embeddings(person_id)
            
            if not person_embeddings:
                continue
            
            person_embeddings_array = np.array(person_embeddings)
            
            similarities = cosine_similarity_batch(person_embeddings_array, embedding)
            
            max_similarity = np.max(similarities)
            
            if max_similarity > best_match_similarity:
                best_match_similarity = max_similarity
                best_match_person_id = person_id
        
        if best_match_similarity >= self.threshold:
            return (best_match_person_id, best_match_similarity)
        
        return None


class MainWindow(QMainWindow):
    def __init__(self, location: str, threshold: float):
        super().__init__()
        self.location = location
        self.threshold = threshold
        self.db = FaceDatabase("./face_data")
        
        self.setWindowTitle("Face Recognition Photo Organizer (InsightFace)")
        self.setGeometry(100, 100, 1200, 800)
        
        self.setup_ui()
        self.start_scanning()
    
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
        self.status_label = QLabel(f"Scanning: {self.location}")
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
        
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 5, 0, 0)
        
        threshold_info = QLabel(f"Threshold: {self.threshold}% (Higher = stricter)")
        threshold_info.setStyleSheet("color: #888; font-size: 10px;")
        bottom_layout.addWidget(threshold_info)
        
        layout.addWidget(bottom_widget)
    
    def start_scanning(self):
        self.worker = FaceRecognitionWorker(self.db, self.location, self.threshold)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.scanning_finished)
        self.worker.log.connect(self.update_log)
        self.worker.start()
    
    def update_progress(self, current: int, total: int):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Processing {current}/{total}")
    
    def update_log(self, message: str):
        self.log_label.setText(message)
    
    def scanning_finished(self):
        self.status_label.setText(f"Complete: {self.person_list.count()} persons found")
        self.log_label.setText("")
        self.progress_bar.hide()
        self.load_persons()
    
    def load_persons(self):
        self.person_list.clear()
        persons = self.db.get_all_persons()
        
        for person in persons:
            item_text = f"{person['person_label']} ({person['face_count']} faces)"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, person['person_id'])
            self.person_list.addItem(item)
    
    def on_person_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        if current is None:
            return
        
        person_id = current.data(Qt.ItemDataRole.UserRole)
        self.load_photos(person_id)
    
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
    
    def load_photos(self, person_id: int):
        self.photo_list.clear()
        photos = self.db.get_photos_by_person(person_id)
        
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
    parser = argparse.ArgumentParser(description='Face Recognition Photo Organizer (InsightFace)')
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
    
    app = QApplication(sys.argv)
    window = MainWindow(args.location, args.threshold)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()