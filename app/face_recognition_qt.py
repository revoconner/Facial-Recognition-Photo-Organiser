"""
Face Recognition Photo Organizer - PySide6 Version
Main entry point using Qt instead of pywebview
"""
import argparse
import sys
import torch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon

from utils import get_resource_path, get_appdata_path
from settings import Settings
from api_qt import APIQt
from main_window import MainWindow
from system_tray import SystemTray

GPU_AVAILABLE = torch.cuda.is_available()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--minimized', action='store_true', help='Start minimized to tray')
    args = parser.parse_args()

    print("=" * 60)
    print("Face Recognition Photo Organizer (Qt Version)")
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

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Face Recognition Photo Organizer")
    app.setOrganizationName("FaceRecognition")

    # Set app icon
    icon_path = get_resource_path('icon.ico')
    app.setWindowIcon(QIcon(icon_path))

    # Create API
    api = APIQt(settings)

    # Create main window
    window = MainWindow(api)
    api.set_window(window)

    # Setup system tray if enabled
    close_to_tray = settings.get('close_to_tray', True)
    if close_to_tray:
        tray = SystemTray(window, api, icon_path)
        api.set_tray(tray)

    # Show or hide window based on startup mode
    if args.minimized and close_to_tray:
        window.hide()
    else:
        window.show()

    # Start event loop
    exit_code = app.exec()

    # Cleanup
    api.close()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
