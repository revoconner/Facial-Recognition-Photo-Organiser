import sys
import argparse
import torch
import webview

from utils import get_resource_path, get_appdata_path
from settings import Settings
from api import API
from logger import setup_logging, get_logger

GPU_AVAILABLE = torch.cuda.is_available()


def main():
    # Console output must not depend on the Windows system code page. Folder paths
    # can contain characters outside cp1252 (for example U+018F, the Azerbaijani
    # schwa); without this the startup prints below raise UnicodeEncodeError on a
    # non-UTF-8 locale. Guarded because sys.stdout/stderr can be None in a windowed
    # (no-console) build.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser()
    parser.add_argument('--minimized', action='store_true', help='Start minimized to tray')
    args = parser.parse_args()
    
    settings_path = get_appdata_path()
    settings = Settings(str(settings_path))

    # Configure file + console logging now that the data dir and the user's chosen
    # level are known. Every module logs through this (see logger.py).
    setup_logging(settings_path / "logs", settings.get("log_level", "INFO"))
    log = get_logger("startup")

    log.info("Face Recognition Photo Organizer starting")
    log.info("PyTorch %s | CUDA available: %s", torch.__version__, GPU_AVAILABLE)
    if GPU_AVAILABLE:
        log.info("CUDA %s | GPU: %s", torch.version.cuda, torch.cuda.get_device_name(0))
    log.info("Settings file: %s", settings.settings_file)
    log.info("Threshold %s%% | include=%s exclude=%s wildcards=%s",
             settings.get('threshold'), settings.get('include_folders'),
             settings.get('exclude_folders'), settings.get('wildcard_exclusions'))
    
    api = API(settings)
    
    ui_html_path = get_resource_path('ui.html')
    
    window = webview.create_window(
        'Face Recognition Photo Organizer',
        ui_html_path,
        js_api=api,
        width=settings.get('window_width', 1200),
        height=settings.get('window_height', 800),
        resizable=True,
        frameless=True,
        easy_drag=False,
        hidden=args.minimized
    )
    
    api.set_window(window)
    
    webview.start(debug=False)
    
    api.close()


if __name__ == "__main__":
    main()
