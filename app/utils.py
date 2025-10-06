import sys
import os
from pathlib import Path
from PIL import Image as PILImage, ImageDraw
import pillow_heif

pillow_heif.register_heif_opener()


def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def get_appdata_path():
    appdata = os.environ.get('APPDATA')
    if appdata:
        return Path(appdata) / "facial_recognition" / "face_data"
    else:
        return Path.home() / "AppData" / "Roaming" / "facial_recognition" / "face_data"


def get_insightface_root():
    """
    Get the InsightFace model root path.
    When running as EXE, use bundled models.
    When running as script, use default cache.
    """
    if getattr(sys, 'frozen', False):
        base_path = Path(sys._MEIPASS)
        return str(base_path)
    else:
        return str(Path.home() / '.insightface')


def create_tray_icon():
    icon_path = get_resource_path('icon.ico')
    try:
        image = PILImage.open(icon_path)
        return image
    except Exception as e:
        print(f"Error loading icon.ico: {e}")
        width = 64
        height = 64
        image = PILImage.new('RGB', (width, height), (255, 255, 255))
        dc = ImageDraw.Draw(image)
        
        dc.ellipse([10, 10, 54, 54], fill=(59, 130, 246))
        dc.ellipse([20, 20, 30, 30], fill=(255, 255, 255))
        dc.ellipse([34, 20, 44, 30], fill=(255, 255, 255))
        dc.arc([15, 25, 49, 50], 0, 180, fill=(255, 255, 255), width=3)
        
        return image
