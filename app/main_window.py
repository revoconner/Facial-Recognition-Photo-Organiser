"""
PySide6 Main Window for Face Recognition Photo Organizer
"""
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QSlider,
    QComboBox, QProgressBar, QFrame, QScrollArea, QGridLayout,
    QMenu, QMessageBox, QToolButton
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QRect, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPixmap, QIcon, QAction, QImage, QPainter, QPainterPath, QBrush, QRegion, QColor


class PersonListItem(QWidget):
    """Custom widget for displaying a person in the list"""
    clicked = Signal(dict)

    def __init__(self, person_data, parent=None):
        super().__init__(parent)
        self.person_data = person_data
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Thumbnail (circular)
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(60, 60)
        self.thumbnail_label.setStyleSheet("background: transparent;")
        self.thumbnail_label.setScaledContents(False)

        if self.person_data.get('thumbnail'):
            self.set_thumbnail(self.person_data['thumbnail'])
        else:
            # Set placeholder circular background
            placeholder = QPixmap(60, 60)
            placeholder.fill(Qt.transparent)
            painter = QPainter(placeholder)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QBrush(Qt.gray))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(0, 0, 60, 60)
            painter.end()
            self.thumbnail_label.setPixmap(placeholder)

        layout.addWidget(self.thumbnail_label)

        # Info section
        info_layout = QVBoxLayout()

        self.name_label = QLabel(self.person_data['name'])
        self.name_label.setStyleSheet("font-weight: bold; color: #e0e0e0;")

        count_text = f"{self.person_data['count']} photos"
        if self.person_data.get('tagged_count', 0) > 0:
            count_text += f" ({self.person_data['tagged_count']} tagged)"

        self.count_label = QLabel(count_text)
        self.count_label.setStyleSheet("color: #a0a0a0; font-size: 12px;")

        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.count_label)
        info_layout.addStretch()

        layout.addLayout(info_layout, 1)

        # Menu button
        self.menu_btn = QToolButton()
        self.menu_btn.setText("⋮")
        self.menu_btn.setStyleSheet("""
            QToolButton {
                border: none;
                padding: 4px;
                color: #a0a0a0;
                font-size: 18px;
            }
            QToolButton:hover {
                background: #3a3a3a;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.menu_btn)

        self.setStyleSheet("""
            PersonListItem {
                background: #1a1a1a;
                border-radius: 8px;
            }
        """)
        self._hover = False

    def enterEvent(self, event):
        """Animate on hover enter"""
        self._hover = True
        self.setStyleSheet("""
            PersonListItem {
                background: #2a2a2a;
                border-radius: 8px;
            }
        """)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Animate on hover leave"""
        self._hover = False
        self.setStyleSheet("""
            PersonListItem {
                background: #1a1a1a;
                border-radius: 8px;
            }
        """)
        super().leaveEvent(event)

    def set_thumbnail(self, base64_data):
        """Set thumbnail from base64 data as circular image"""
        if base64_data.startswith('data:image'):
            # Extract base64 part
            base64_str = base64_data.split(',')[1]
            import base64
            img_data = base64.b64decode(base64_str)

            image = QImage()
            image.loadFromData(img_data)

            pixmap = QPixmap.fromImage(image)
            scaled_pixmap = pixmap.scaled(60, 60, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

            # Create circular mask
            circular_pixmap = QPixmap(60, 60)
            circular_pixmap.fill(Qt.transparent)

            painter = QPainter(circular_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)

            # Create circular path
            path = QPainterPath()
            path.addEllipse(0, 0, 60, 60)
            painter.setClipPath(path)

            # Draw scaled pixmap centered
            x = (60 - scaled_pixmap.width()) // 2
            y = (60 - scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, scaled_pixmap)
            painter.end()

            self.thumbnail_label.setPixmap(circular_pixmap)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.person_data)
        super().mousePressEvent(event)


class PhotoGridWidget(QWidget):
    """Widget for displaying photo grid with lazy loading"""
    photo_clicked = Signal(dict)

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.photos = []
        self.grid_size = 180
        self.loaded_count = 0
        self.batch_size = 200  # Load 200 at a time
        self.loading = False
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area for photos
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().valueChanged.connect(self.on_scroll)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(8)

        self.scroll.setWidget(self.grid_widget)
        layout.addWidget(self.scroll)

    def set_photos(self, photos):
        """Set photos to display"""
        print(f"PhotoGrid: Setting {len(photos)} photos")
        self.photos = photos
        self.loaded_count = 0
        self.render_initial_batch()

    def render_initial_batch(self):
        """Load first batch of photos"""
        # Clear existing items
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        print(f"PhotoGrid: Loading initial batch of {min(self.batch_size, len(self.photos))} photos")

        # Defer loading until after layout pass to get correct width
        QTimer.singleShot(0, self.load_more_photos)

    def on_scroll(self, value):
        """Load more photos when scrolling near bottom"""
        if self.loading or self.loaded_count >= len(self.photos):
            return

        scrollbar = self.scroll.verticalScrollBar()
        # Load more when 80% scrolled
        if value >= scrollbar.maximum() * 0.8:
            self.load_more_photos()

    def load_more_photos(self):
        """Load next batch of photos"""
        if self.loading or self.loaded_count >= len(self.photos):
            return

        self.loading = True
        start_idx = self.loaded_count
        end_idx = min(start_idx + self.batch_size, len(self.photos))

        print(f"PhotoGrid: Loading photos {start_idx} to {end_idx-1}")

        # Calculate columns based on scroll viewport width (more accurate than self.width())
        viewport_width = self.scroll.viewport().width()
        width = viewport_width if viewport_width > 100 else 800
        cols = max(1, width // (self.grid_size + 8))

        print(f"PhotoGrid: Viewport width={width}, cols={cols}")

        # Add photos
        for idx in range(start_idx, end_idx):
            photo = self.photos[idx]
            photo_label = QLabel()
            photo_label.setFixedSize(self.grid_size, self.grid_size)
            photo_label.setStyleSheet(f"""
                QLabel {{
                    background: #2a2a2a;
                    border-radius: {int(self.grid_size * 0.08)}px;
                    border: 2px solid transparent;
                }}
                QLabel:hover {{
                    border-color: #3b82f6;
                }}
            """)
            photo_label.setScaledContents(False)

            # Generate thumbnail on-demand
            thumbnail = self.api.get_thumbnail_for_photo(photo, self.grid_size)
            if thumbnail:
                self.set_photo_thumbnail(photo_label, thumbnail)

            # Store photo data
            photo_label.setProperty('photo_data', photo)
            photo_label.mousePressEvent = lambda e, p=photo: self.photo_clicked.emit(p)

            row = idx // cols
            col = idx % cols
            self.grid_layout.addWidget(photo_label, row, col)

        self.loaded_count = end_idx
        self.loading = False

        print(f"PhotoGrid: Loaded {self.loaded_count}/{len(self.photos)} photos")

        # Force layout update to prevent overlapping
        self.grid_widget.updateGeometry()
        self.scroll.update()

    def set_grid_size(self, size):
        """Update grid thumbnail size"""
        self.grid_size = size
        # Reload with new size
        if self.photos:
            self.render_initial_batch()

    def set_photo_thumbnail(self, label, base64_data):
        """Set photo thumbnail from base64 with rounded corners"""
        if base64_data.startswith('data:image'):
            base64_str = base64_data.split(',')[1]
            import base64
            img_data = base64.b64decode(base64_str)

            image = QImage()
            image.loadFromData(img_data)

            pixmap = QPixmap.fromImage(image)
            scaled_pixmap = pixmap.scaled(
                self.grid_size, self.grid_size,
                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )

            # Create rounded corner pixmap
            radius = int(self.grid_size * 0.08)
            rounded_pixmap = QPixmap(self.grid_size, self.grid_size)
            rounded_pixmap.fill(Qt.transparent)

            painter = QPainter(rounded_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)

            # Create rounded rectangle path
            path = QPainterPath()
            path.addRoundedRect(0, 0, self.grid_size, self.grid_size, radius, radius)
            painter.setClipPath(path)

            # Draw scaled pixmap centered
            x = (self.grid_size - scaled_pixmap.width()) // 2
            y = (self.grid_size - scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, scaled_pixmap)
            painter.end()

            label.setPixmap(rounded_pixmap)

    def resizeEvent(self, event):
        """Handle resize to recalculate grid columns"""
        super().resizeEvent(event)
        # Reload grid with new column count
        if self.photos and self.loaded_count > 0:
            self.render_initial_batch()


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self, api):
        super().__init__()
        self.api = api
        self.current_person = None

        self.setup_ui()
        self.setup_connections()
        self.load_initial_data()

    def setup_ui(self):
        """Setup the UI components"""
        self.setWindowTitle("Face Recognition Photo Organizer")
        self.setMinimumSize(1200, 800)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left sidebar - People list
        self.people_widget = self.create_people_widget()
        splitter.addWidget(self.people_widget)

        # Right content area
        self.content_widget = self.create_content_widget()
        splitter.addWidget(self.content_widget)

        splitter.setSizes([300, 900])
        main_layout.addWidget(splitter)

        # Bottom bar
        bottom_bar = self.create_bottom_bar()
        main_layout.addWidget(bottom_bar)

        # Apply dark theme with polish
        self.setStyleSheet("""
            QMainWindow {
                background: #0d0d0d;
            }
            QWidget {
                background: #0d0d0d;
                color: #e0e0e0;
            }
            QListWidget {
                background: #1a1a1a;
                border: none;
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::item {
                border-radius: 6px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #3a3a3a;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4a4a4a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 10px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #3a3a3a;
                border-radius: 5px;
                min-width: 30px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #4a4a4a;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }
            QSplitter::handle {
                background: #2a2a2a;
                width: 1px;
            }
            QSplitter::handle:hover {
                background: #3a3a3a;
            }
        """)

    def create_people_widget(self):
        """Create the people list sidebar"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)

        # Header
        header = QHBoxLayout()

        title = QLabel("People")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title)

        header.addStretch()

        # Sort button
        self.sort_btn = QToolButton()
        self.sort_btn.setText("↕")  # Sort icon placeholder
        self.sort_btn.setToolTip("Sort people")
        self.sort_btn.setStyleSheet("""
            QToolButton {
                font-size: 18px;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                color: #a0a0a0;
            }
            QToolButton:hover {
                background: #2a2a2a;
                color: #e0e0e0;
            }
        """)
        header.addWidget(self.sort_btn)

        # Jump to button
        self.jump_to_btn = QToolButton()
        self.jump_to_btn.setText("⊡")  # Jump to icon placeholder
        self.jump_to_btn.setToolTip("Jump to name")
        self.jump_to_btn.setStyleSheet("""
            QToolButton {
                font-size: 18px;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                color: #a0a0a0;
            }
            QToolButton:hover {
                background: #2a2a2a;
                color: #e0e0e0;
            }
        """)
        header.addWidget(self.jump_to_btn)

        # Filter/menu button
        self.people_menu_btn = QToolButton()
        self.people_menu_btn.setText("⋮")
        self.people_menu_btn.setToolTip("People options")
        self.people_menu_btn.setStyleSheet("""
            QToolButton {
                font-size: 18px;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                color: #a0a0a0;
            }
            QToolButton:hover {
                background: #2a2a2a;
                color: #e0e0e0;
            }
        """)
        header.addWidget(self.people_menu_btn)

        layout.addLayout(header)

        # People list
        self.people_list = QListWidget()
        self.people_list.setSpacing(4)
        self.people_list.setStyleSheet("QListWidget::item { background: transparent; }")
        layout.addWidget(self.people_list)

        container.setStyleSheet("background: #1a1a1a; border-radius: 8px;")
        return container

    def create_content_widget(self):
        """Create the content area with photo grid"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)

        # Header with controls
        header = QHBoxLayout()

        self.content_title = QLabel("Select a person")
        self.content_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(self.content_title)

        # Photo menu button
        self.photo_menu_btn = QToolButton()
        self.photo_menu_btn.setText("⋮")
        self.photo_menu_btn.setToolTip("Photo options")
        self.photo_menu_btn.setStyleSheet("""
            QToolButton {
                font-size: 18px;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                color: #a0a0a0;
            }
            QToolButton:hover {
                background: #2a2a2a;
                color: #e0e0e0;
            }
        """)
        header.addWidget(self.photo_menu_btn)

        header.addStretch()

        # Size slider
        size_label = QLabel("Size:")
        header.addWidget(size_label)

        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setMinimum(100)
        self.size_slider.setMaximum(300)
        self.size_slider.setValue(180)
        self.size_slider.setFixedWidth(150)
        header.addWidget(self.size_slider)

        # View mode dropdown
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItem("Show entire photo", "entire_photo")
        self.view_mode_combo.addItem("Zoom to tagged faces", "zoom_to_faces")
        self.view_mode_combo.setStyleSheet("""
            QComboBox {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 6px 12px;
            }
        """)
        header.addWidget(self.view_mode_combo)

        layout.addLayout(header)

        # Photo grid (pass api reference for thumbnail generation)
        self.photo_grid = PhotoGridWidget(self.api)
        layout.addWidget(self.photo_grid)

        return container

    def create_bottom_bar(self):
        """Create the bottom status bar"""
        container = QFrame()
        container.setFrameShape(QFrame.StyledPanel)
        container.setFixedHeight(40)
        container.setStyleSheet("background: #1a1a1a; border-top: 1px solid #2a2a2a;")

        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(16)

        # Settings button
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setFixedHeight(28)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background: #3b82f6;
                color: white;
                border: none;
                padding: 4px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #2563eb;
            }
        """)
        layout.addWidget(self.settings_btn)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setStyleSheet("color: #3a3a3a;")
        layout.addWidget(separator)

        # Status info labels
        self.pytorch_label = QLabel("PyTorch")
        self.gpu_label = QLabel("Checking GPU...")
        self.cuda_label = QLabel("CUDA: N/A")
        self.face_count_label = QLabel("Found: 0 faces")

        for label in [self.pytorch_label, self.gpu_label, self.cuda_label, self.face_count_label]:
            label.setStyleSheet("color: #888888; font-size: 11px;")
            layout.addWidget(label)

            # Add separator between labels
            sep = QLabel("|")
            sep.setStyleSheet("color: #3a3a3a; font-size: 11px;")
            layout.addWidget(sep)

        layout.addStretch()

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3a3a3a;
                border-radius: 3px;
                text-align: center;
                background: #2a2a2a;
            }
            QProgressBar::chunk {
                background: #3b82f6;
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.progress_bar)

        self.progress_text = QLabel("Initializing...")
        self.progress_text.setVisible(False)
        self.progress_text.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(self.progress_text)

        # Help button
        self.help_btn = QPushButton("?")
        self.help_btn.setFixedSize(24, 24)
        self.help_btn.setStyleSheet("""
            QPushButton {
                background: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 12px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #3a3a3a;
                border-color: #4a4a4a;
            }
        """)
        layout.addWidget(self.help_btn)

        return container

    def setup_connections(self):
        """Setup signal/slot connections"""
        self.size_slider.valueChanged.connect(self.on_size_changed)
        self.view_mode_combo.currentIndexChanged.connect(self.on_view_mode_changed)
        self.settings_btn.clicked.connect(self.show_settings)
        self.people_menu_btn.clicked.connect(self.show_people_menu)
        self.photo_menu_btn.clicked.connect(self.show_photo_menu)
        self.sort_btn.clicked.connect(self.show_sort_menu)
        self.jump_to_btn.clicked.connect(self.show_jump_to_dialog)
        self.help_btn.clicked.connect(self.show_help)

    def load_initial_data(self):
        """Load initial data from API"""
        # Get system info
        try:
            info = self.api.get_system_info()
            self.pytorch_label.setText(f"PyTorch {info['pytorch_version']}")

            if info['gpu_available']:
                self.gpu_label.setText(f"GPU: {info['gpu_name']}")
                self.cuda_label.setText(f"CUDA: {info['cuda_version']}")
            else:
                self.gpu_label.setText("GPU: N/A (CPU mode)")
                self.cuda_label.setText("CUDA: N/A")

            self.face_count_label.setText(f"Found: {info['total_faces']} faces")
        except Exception as e:
            print(f"Error loading system info: {e}")

        # Load people list
        self.load_people()

        # Check initial state
        QTimer.singleShot(500, self.check_initial_state)

    def check_initial_state(self):
        """Check if scanning is needed"""
        try:
            result = self.api.check_initial_state()
            if not result.get('needs_scan'):
                # Data is ready
                pass
        except Exception as e:
            print(f"Error checking initial state: {e}")

    def load_people(self):
        """Load people list from API"""
        try:
            people = self.api.get_people()
            self.people_list.clear()

            for person in people:
                # Create custom item
                item_widget = PersonListItem(person)
                item_widget.clicked.connect(self.on_person_selected)

                item = QListWidgetItem(self.people_list)
                item.setSizeHint(item_widget.sizeHint())
                self.people_list.addItem(item)
                self.people_list.setItemWidget(item, item_widget)
        except Exception as e:
            print(f"Error loading people: {e}")

    def on_person_selected(self, person_data):
        """Handle person selection"""
        print(f"=== PERSON SELECTED ===")
        print(f"Person data: {person_data}")
        print(f"Person ID: {person_data.get('id')}")
        print(f"Person name: {person_data.get('name')}")
        print(f"Clustering ID: {person_data.get('clustering_id')}")

        self.current_person = person_data
        self.content_title.setText(person_data['name'])
        self.load_photos()

    def load_photos(self):
        """Load photos for current person"""
        if not self.current_person:
            return

        try:
            print(f"=== LOADING PHOTOS ===")
            print(f"Clustering ID: {self.current_person['clustering_id']}")
            print(f"Person ID: {self.current_person['id']}")

            result = self.api.get_photos(
                self.current_person['clustering_id'],
                self.current_person['id']
            )

            print(f"Got {len(result['photos'])} photos")

            self.photo_grid.set_photos(result['photos'])
        except Exception as e:
            print(f"Error loading photos: {e}")
            import traceback
            traceback.print_exc()

    def on_size_changed(self, value):
        """Handle grid size change"""
        self.photo_grid.set_grid_size(value)
        self.api.set_grid_size(value)

    def on_view_mode_changed(self, index):
        """Handle view mode change"""
        mode = self.view_mode_combo.currentData()
        self.api.set_view_mode(mode)
        self.load_photos()  # Reload with new mode

    def show_settings(self):
        """Show settings dialog"""
        # TODO: Implement settings dialog
        QMessageBox.information(self, "Settings", "Settings dialog coming soon!")

    def show_people_menu(self):
        """Show people list menu"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QMenu::item:selected {
                background: #3b82f6;
            }
        """)

        menu.addAction("Hide unnamed persons")
        menu.addAction("Show hidden persons")
        menu.addSeparator()
        menu.addAction("Refresh list")

        menu.exec(self.people_menu_btn.mapToGlobal(self.people_menu_btn.rect().bottomLeft()))

    def show_photo_menu(self):
        """Show photo options menu"""
        if not self.current_person:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QMenu::item:selected {
                background: #3b82f6;
            }
        """)

        menu.addAction("Set primary photo")
        menu.addAction("Rename person")
        menu.addSeparator()
        menu.addAction("Hide person")
        menu.addAction("Export photos")

        menu.exec(self.photo_menu_btn.mapToGlobal(self.photo_menu_btn.rect().bottomLeft()))

    def show_sort_menu(self):
        """Show sort options menu"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QMenu::item:selected {
                background: #3b82f6;
            }
        """)

        menu.addAction("Sort by name (A-Z)")
        menu.addAction("Sort by name (Z-A)")
        menu.addAction("Sort by photo count (high to low)")
        menu.addAction("Sort by photo count (low to high)")

        menu.exec(self.sort_btn.mapToGlobal(self.sort_btn.rect().bottomLeft()))

    def show_jump_to_dialog(self):
        """Show jump to name dialog"""
        # TODO: Implement jump to dialog
        QMessageBox.information(self, "Jump To", "Jump to name dialog coming soon!")

    def show_help(self):
        """Show help dialog"""
        # TODO: Implement help dialog with keyboard shortcuts, etc.
        help_text = """
        <h3>Keyboard Shortcuts</h3>
        <p><b>↑/↓</b> - Navigate people list</p>
        <p><b>Enter</b> - View selected person's photos</p>
        <p><b>Ctrl+F</b> - Search/Jump to name</p>
        <p><b>Ctrl+,</b> - Open settings</p>

        <h3>Tips</h3>
        <p>• Click and drag to select multiple photos</p>
        <p>• Right-click photos for more options</p>
        <p>• Adjust similarity threshold in settings</p>
        """
        QMessageBox.information(self, "Help", help_text)

    def update_progress(self, current, total, percent):
        """Update progress bar"""
        self.progress_bar.setVisible(True)
        self.progress_text.setVisible(True)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def update_status(self, message):
        """Update status message"""
        self.progress_text.setVisible(True)
        self.progress_text.setText(message)

    def hide_progress(self):
        """Hide progress bar"""
        self.progress_bar.setVisible(False)
        self.progress_text.setVisible(False)

    def closeEvent(self, event):
        """Handle window close event"""
        # Check if close to tray is enabled
        close_to_tray = self.api._settings.get('close_to_tray', True)

        if close_to_tray and hasattr(self.api, '_tray') and self.api._tray:
            # Minimize to tray instead of closing
            event.ignore()
            self.hide()
            self.api.set_window_foreground(False)
        else:
            # Actually close the application
            event.accept()
            self.api.close()
