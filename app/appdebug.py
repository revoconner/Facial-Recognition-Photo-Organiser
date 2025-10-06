
"""
Minimal PyQt6 viewer for debugging face recognition database
Just reads and displays - no modifications, no scanning
"""

import sys
import os
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Optional
import base64
from io import BytesIO

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QLabel, QScrollArea, QPushButton,
    QSpinBox, QCheckBox, QTextEdit, QSplitter, QGroupBox
)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImage
from PIL import Image
import numpy as np

# Hardcoded paths from settings.json
SETTINGS = {
    "threshold": 45,
    "show_unmatched": False,
    "show_hidden": True,
    "min_photos_enabled": False,
    "min_photos_count": 50,
    "sort_mode": "photos_asc"
}

class DatabaseReader:
    """Minimal database reader - read only"""
    
    def __init__(self):
        self.appdata_path = Path(os.environ.get('APPDATA')) / "facial_recognition" / "face_data"
        self.db_path = self.appdata_path / "metadata.db"
        
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found at {self.db_path}")
        
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
    
    def get_active_clustering(self) -> Optional[int]:
        """Get the active clustering ID"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT clustering_id FROM clusterings WHERE is_active = 1')
        row = cursor.fetchone()
        return row[0] if row else None
    
    def get_all_persons(self, clustering_id: int) -> List[Dict]:
        """Get all persons in the clustering"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT person_id, COUNT(*) as face_count
            FROM cluster_assignments
            WHERE clustering_id = ?
            GROUP BY person_id
            ORDER BY person_id
        ''', (clustering_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_person_name(self, clustering_id: int, person_id: int) -> str:
        """Get the name for a person"""
        cursor = self.conn.cursor()
        
        # Get face IDs for this person
        cursor.execute('''
            SELECT face_id FROM cluster_assignments
            WHERE clustering_id = ? AND person_id = ?
        ''', (clustering_id, person_id))
        face_ids = [row[0] for row in cursor.fetchall()]
        
        if not face_ids:
            return f"Person {person_id}" if person_id > 0 else "Unmatched Faces"
        
        # Check for tags
        placeholders = ','.join('?' * len(face_ids))
        cursor.execute(f'''
            SELECT tag_name, COUNT(*) as count 
            FROM face_tags 
            WHERE face_id IN ({placeholders})
            GROUP BY tag_name
            ORDER BY count DESC
            LIMIT 1
        ''', face_ids)
        
        row = cursor.fetchone()
        if row:
            return row[0]
        
        return f"Person {person_id}" if person_id > 0 else "Unmatched Faces"
    
    def get_first_photo_path(self, clustering_id: int, person_id: int) -> Optional[str]:
        """Get the first photo path for thumbnail generation"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT p.file_path, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2
            FROM photos p
            JOIN faces f ON p.photo_id = f.photo_id
            JOIN cluster_assignments ca ON f.face_id = ca.face_id
            WHERE ca.clustering_id = ? AND ca.person_id = ?
            LIMIT 1
        ''', (clustering_id, person_id))
        
        row = cursor.fetchone()
        if row:
            return {
                'path': row[0],
                'bbox': [row[1], row[2], row[3], row[4]]
            }
        return None
    
    def is_person_hidden(self, clustering_id: int, person_id: int) -> bool:
        """Check if person is hidden"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT 1 FROM hidden_persons
            WHERE clustering_id = ? AND person_id = ?
        ''', (clustering_id, person_id))
        return cursor.fetchone() is not None
    
    def close(self):
        self.conn.close()


class ThumbnailGenerator:
    """Simple thumbnail generator"""
    
    @staticmethod
    def create_thumbnail(image_path: str, bbox: List[float] = None, size: int = 80) -> Optional[QPixmap]:
        """Create a thumbnail from image path"""
        try:
            if not os.path.exists(image_path):
                return None
            
            img = Image.open(image_path)
            
            # Crop to face if bbox provided
            if bbox:
                x1, y1, x2, y2 = bbox
                padding = 20
                x1 = max(0, x1 - padding)
                y1 = max(0, y1 - padding)
                x2 = min(img.width, x2 + padding)
                y2 = min(img.height, y2 + padding)
                img = img.crop((int(x1), int(y1), int(x2), int(y2)))
            
            # Create thumbnail
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            img = img.convert('RGB')
            
            # Convert to QPixmap
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            
            qimg = QImage()
            qimg.loadFromData(buffer.getvalue())
            return QPixmap.fromImage(qimg)
            
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
            return None


class PersonListWidget(QWidget):
    """Widget to display list of persons"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = DatabaseReader()
        self.init_ui()
        self.load_data()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Stats label
        self.stats_label = QLabel("Loading...")
        layout.addWidget(self.stats_label)
        
        # Filter controls
        filter_layout = QHBoxLayout()
        
        self.show_hidden_cb = QCheckBox("Show Hidden")
        self.show_hidden_cb.setChecked(SETTINGS['show_hidden'])
        self.show_hidden_cb.stateChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.show_hidden_cb)
        
        self.show_unmatched_cb = QCheckBox("Show Unmatched")
        self.show_unmatched_cb.setChecked(SETTINGS['show_unmatched'])
        self.show_unmatched_cb.stateChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.show_unmatched_cb)
        
        self.min_photos_cb = QCheckBox("Min Photos:")
        self.min_photos_cb.setChecked(SETTINGS['min_photos_enabled'])
        self.min_photos_cb.stateChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.min_photos_cb)
        
        self.min_photos_spin = QSpinBox()
        self.min_photos_spin.setRange(1, 1000)
        self.min_photos_spin.setValue(SETTINGS['min_photos_count'])
        self.min_photos_spin.valueChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.min_photos_spin)
        
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # List widget
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(60, 60))
        layout.addWidget(self.list_widget)
        
        # Info label
        self.info_label = QLabel("")
        layout.addWidget(self.info_label)
        
        self.setLayout(layout)
        
        # Data storage
        self.all_persons = []
        self.filtered_persons = []
    
    def load_data(self):
        """Load persons from database"""
        try:
            clustering_id = self.db.get_active_clustering()
            if not clustering_id:
                self.stats_label.setText("No active clustering found")
                return
            
            self.stats_label.setText(f"Loading from clustering {clustering_id}...")
            
            # Get all persons
            persons = self.db.get_all_persons(clustering_id)
            
            # Enrich with names and thumbnails
            self.all_persons = []
            total_faces = 0
            
            for person in persons:
                person_id = person['person_id']
                face_count = person['face_count']
                total_faces += face_count
                
                # Get name
                name = self.db.get_person_name(clustering_id, person_id)
                
                # Check if hidden
                is_hidden = self.db.is_person_hidden(clustering_id, person_id)
                if is_hidden:
                    name += " (hidden)"
                
                person_data = {
                    'id': person_id,
                    'name': name,
                    'count': face_count,
                    'is_hidden': is_hidden,
                    'clustering_id': clustering_id
                }
                
                self.all_persons.append(person_data)
            
            # Sort by photo count (ascending as per settings)
            if SETTINGS['sort_mode'] == 'photos_asc':
                self.all_persons.sort(key=lambda x: x['count'])
            elif SETTINGS['sort_mode'] == 'photos_desc':
                self.all_persons.sort(key=lambda x: x['count'], reverse=True)
            elif SETTINGS['sort_mode'] == 'names_asc':
                self.all_persons.sort(key=lambda x: x['name'])
            else:
                self.all_persons.sort(key=lambda x: x['name'], reverse=True)
            
            self.stats_label.setText(
                f"Loaded {len(self.all_persons)} persons with {total_faces} total faces"
            )
            
            # Apply initial filters
            self.apply_filters()
            
        except Exception as e:
            self.stats_label.setText(f"Error loading data: {e}")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
    
    def apply_filters(self):
        """Apply filters and update display"""
        self.filtered_persons = []
        
        show_hidden = self.show_hidden_cb.isChecked()
        show_unmatched = self.show_unmatched_cb.isChecked()
        min_photos_enabled = self.min_photos_cb.isChecked()
        min_photos = self.min_photos_spin.value()
        
        for person in self.all_persons:
            # Filter hidden
            if person['is_hidden'] and not show_hidden:
                continue
            
            # Filter unmatched
            if person['id'] == 0 and not show_unmatched:
                continue
            
            # Filter by min photos
            if min_photos_enabled and person['count'] < min_photos:
                continue
            
            self.filtered_persons.append(person)
        
        self.update_display()
    
    def update_display(self):
        """Update the list widget display"""
        self.list_widget.clear()
        
        self.info_label.setText(f"Showing {len(self.filtered_persons)} of {len(self.all_persons)} persons")
        
        # Add items with basic info (no thumbnails initially)
        for person in self.filtered_persons:
            item = QListWidgetItem(f"{person['name']} ({person['count']} photos)")
            item.setData(Qt.ItemDataRole.UserRole, person)
            self.list_widget.addItem(item)
        
        # Load thumbnails asynchronously
        QTimer.singleShot(100, self.load_thumbnails)
    
    def load_thumbnails(self):
        """Load thumbnails for visible items"""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            person = item.data(Qt.ItemDataRole.UserRole)
            
            # Get first photo for thumbnail
            photo_data = self.db.get_first_photo_path(person['clustering_id'], person['id'])
            if photo_data:
                pixmap = ThumbnailGenerator.create_thumbnail(
                    photo_data['path'], 
                    photo_data['bbox'], 
                    size=60
                )
                if pixmap:
                    item.setIcon(pixmap)
            
            # Process events to keep UI responsive
            if i % 10 == 0:
                QApplication.processEvents()
    
    def closeEvent(self, event):
        self.db.close()
        event.accept()


class DebugViewer(QMainWindow):
    """Main debug viewer window"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Face Recognition Database Debug Viewer")
        self.setGeometry(100, 100, 800, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        layout = QVBoxLayout(central)
        
        # Title
        title = QLabel("Face Recognition Database Debug Viewer")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)
        
        # Info
        info = QLabel(f"Database: {Path(os.environ.get('APPDATA')) / 'facial_recognition' / 'face_data'}")
        info.setStyleSheet("padding: 5px;")
        layout.addWidget(info)
        
        # Person list widget
        self.person_widget = PersonListWidget()
        layout.addWidget(self.person_widget)
        
        # Log area
        log_group = QGroupBox("Debug Log")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        self.log("Debug viewer started")
        self.log(f"Python: {sys.version}")
        self.log(f"PyQt6 loaded successfully")
    
    def log(self, message):
        """Add message to log"""
        self.log_text.append(message)


def main():
    app = QApplication(sys.argv)
    
    # Set dark theme
    app.setStyleSheet("""
        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QListWidget {
            background-color: #1e1e1e;
            border: 1px solid #3c3c3c;
        }
        QListWidget::item:selected {
            background-color: #094771;
        }
        QCheckBox, QLabel {
            color: #ffffff;
        }
        QTextEdit {
            background-color: #1e1e1e;
            border: 1px solid #3c3c3c;
        }
        QGroupBox {
            border: 1px solid #3c3c3c;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title {
            color: #ffffff;
        }
    """)
    
    viewer = DebugViewer()
    viewer.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()