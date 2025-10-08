import json
from pathlib import Path


class Settings:
    def __init__(self, settings_path: str):
        self.settings_path = Path(settings_path)
        self.settings_file = self.settings_path / "settings.json"
        self.settings_path.mkdir(parents=True, exist_ok=True)
        
        self.defaults = {
            'threshold': 50,
            'close_to_tray': True,
            'dynamic_resources': True,
            'show_unmatched': False,
            'show_hidden': False,
            'show_hidden_photos': False,
            'show_dev_options': False,
            'min_photos_enabled': False,
            'min_photos_count': 2,
            'grid_size': 180,
            'window_width': 1200,
            'window_height': 800,
            'include_folders': [],
            'exclude_folders': [],
            'wildcard_exclusions': '',
            'view_mode': 'entire_photo',
            'sort_mode': 'names_asc',
            'hide_unnamed_persons': False,
            'scan_frequency': 'restart_1_day',
            'last_scan_time': None,
            'show_face_tags_preview': True
        }
        
        self.settings = self.load()
    
    def load(self) -> dict:
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    loaded = json.load(f)
                    return {**self.defaults, **loaded}
        except Exception as e:
            print(f"Error loading settings: {e}")
        
        return self.defaults.copy()
    
    def save(self):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def get(self, key: str, default=None):
        return self.settings.get(key, default)
    
    def set(self, key: str, value):
        self.settings[key] = value
        self.save()
    
    def update(self, updates: dict):
        self.settings.update(updates)
        self.save()
