"""
System Tray Integration for Qt Application
"""
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Qt


class SystemTray(QSystemTrayIcon):
    """System tray icon with menu"""

    def __init__(self, main_window, api, icon_path):
        super().__init__()

        self.main_window = main_window
        self.api = api

        # Set icon
        icon = QIcon(icon_path)
        self.setIcon(icon)
        self.setToolTip("Face Recognition Photo Organizer")

        # Create context menu
        self.create_menu()

        # Connect signals
        self.activated.connect(self.on_tray_activated)

        # Show tray icon
        self.show()

    def create_menu(self):
        """Create the tray context menu"""
        menu = QMenu()

        # Restore/Show action
        restore_action = QAction("Open", self.main_window)
        restore_action.triggered.connect(self.restore_window)
        menu.addAction(restore_action)

        menu.addSeparator()

        # Quit action
        quit_action = QAction("Quit", self.main_window)
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def on_tray_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.restore_window()

    def restore_window(self):
        """Restore and show the main window"""
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        self.api.set_window_foreground(True)

    def quit_application(self):
        """Quit the application completely"""
        # Close the window which will trigger cleanup
        self.main_window.close()

        # Force quit
        from PySide6.QtWidgets import QApplication
        QApplication.quit()
