"""
Lightbox Dialog for Full Photo Preview
"""
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QImage, QKeyEvent, QPainter, QColor, QFont
import base64


class LightboxDialog(QDialog):
    """Full-screen lightbox for photo preview"""

    def __init__(self, api, photos, current_index=0, parent=None):
        super().__init__(parent)
        print(f"LightboxDialog init: {len(photos)} photos, current_index={current_index}")
        self.api = api
        self.photos = photos
        self.current_index = current_index
        self.photo_loaded = False
        try:
            self.setup_ui()
            print("UI setup complete")
            # Don't load photo yet - wait for dialog to be shown with correct size
        except Exception as e:
            print(f"Error in LightboxDialog init: {e}")
            import traceback
            traceback.print_exc()
            raise

    def setup_ui(self):
        """Setup the lightbox UI"""
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setStyleSheet("background: rgba(0, 0, 0, 0.95);")

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar with close button
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(20, 20, 20, 20)
        top_bar.addStretch()

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(40, 40)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 20px;
                color: white;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
        """)
        self.close_btn.clicked.connect(self.close)
        top_bar.addWidget(self.close_btn)

        layout.addLayout(top_bar)

        # Center content - image with navigation
        center_layout = QHBoxLayout()
        center_layout.setContentsMargins(20, 20, 20, 20)

        # Previous button
        self.prev_btn = QPushButton("‹")
        self.prev_btn.setFixedSize(50, 50)
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 25px;
                color: white;
                font-size: 48px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.05);
                color: rgba(255, 255, 255, 0.3);
            }
        """)
        self.prev_btn.clicked.connect(self.show_previous)
        center_layout.addWidget(self.prev_btn, alignment=Qt.AlignCenter)

        # Image label
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent;")
        center_layout.addWidget(self.image_label, 1)

        # Next button
        self.next_btn = QPushButton("›")
        self.next_btn.setFixedSize(50, 50)
        self.next_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 25px;
                color: white;
                font-size: 48px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.05);
                color: rgba(255, 255, 255, 0.3);
            }
        """)
        self.next_btn.clicked.connect(self.show_next)
        center_layout.addWidget(self.next_btn, alignment=Qt.AlignCenter)

        layout.addLayout(center_layout, 1)

        # Bottom bar with counter and actions
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(20, 20, 20, 20)

        # Counter
        self.counter_label = QLabel()
        self.counter_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 14px;
                background: rgba(0, 0, 0, 0.5);
                padding: 8px 16px;
                border-radius: 4px;
            }
        """)
        bottom_bar.addWidget(self.counter_label)

        bottom_bar.addStretch()

        # Open in external app button
        self.open_external_btn = QPushButton("Open in Default App")
        self.open_external_btn.setStyleSheet("""
            QPushButton {
                background: rgba(59, 130, 246, 0.8);
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(37, 99, 235, 0.9);
            }
        """)
        self.open_external_btn.clicked.connect(self.open_in_external_app)
        bottom_bar.addWidget(self.open_external_btn)

        layout.addLayout(bottom_bar)

    def load_current_photo(self):
        """Load and display the current photo"""
        try:
            if not self.photos or self.current_index >= len(self.photos):
                print("No photos to load")
                return

            photo = self.photos[self.current_index]
            print(f"Loading photo: {photo.get('name', 'unknown')}, path: {photo.get('path', 'no path')}")

            # Update counter
            total = len(self.photos)
            self.counter_label.setText(f"{self.current_index + 1} of {total}")

            # Update navigation buttons
            self.prev_btn.setEnabled(self.current_index > 0)
            self.next_btn.setEnabled(self.current_index < total - 1)

            # Load full-size preview
            print(f"Requesting full size preview for: {photo['path']}")
            preview = self.api.get_full_size_preview(photo['path'])
            if preview:
                print("Preview received, setting image")
                self.set_image_from_base64(preview)
            else:
                print("No preview returned from API")
        except Exception as e:
            print(f"Error loading photo: {e}")
            import traceback
            traceback.print_exc()

    def set_image_from_base64(self, base64_data):
        """Set image from base64 data"""
        try:
            if base64_data.startswith('data:image'):
                base64_str = base64_data.split(',')[1]
                import base64
                img_data = base64.b64decode(base64_str)

                image = QImage()
                image.loadFromData(img_data)
                print(f"Image loaded: {image.width()}x{image.height()}")

                # Use a large default size for scaling (will fit screen)
                # Don't rely on self.size() which may not be correct yet
                from PySide6.QtWidgets import QApplication
                screen = QApplication.primaryScreen().geometry()
                max_width = screen.width() - 200
                max_height = screen.height() - 200

                print(f"Scaling to fit: max_width={max_width}, max_height={max_height}")

                pixmap = QPixmap.fromImage(image)
                scaled_pixmap = pixmap.scaled(
                    max_width, max_height,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )

                print(f"Scaled pixmap: {scaled_pixmap.width()}x{scaled_pixmap.height()}")

                self.image_label.setPixmap(scaled_pixmap)
                print("Pixmap set on label")
        except Exception as e:
            print(f"Error setting image: {e}")
            import traceback
            traceback.print_exc()

    def show_previous(self):
        """Show previous photo"""
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_photo()

    def show_next(self):
        """Show next photo"""
        if self.current_index < len(self.photos) - 1:
            self.current_index += 1
            self.load_current_photo()

    def open_in_external_app(self):
        """Open current photo in default external app"""
        if self.photos and self.current_index < len(self.photos):
            photo = self.photos[self.current_index]
            self.api.open_photo(photo['path'])

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard shortcuts"""
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Left:
            self.show_previous()
        elif event.key() == Qt.Key_Right:
            self.show_next()
        else:
            super().keyPressEvent(event)

    def showEvent(self, event):
        """Handle show event - load photo once dialog is shown"""
        super().showEvent(event)
        # Load photo on first show
        if not self.photo_loaded:
            print("showEvent: Loading photo now that dialog is visible")
            self.photo_loaded = True
            self.load_current_photo()
