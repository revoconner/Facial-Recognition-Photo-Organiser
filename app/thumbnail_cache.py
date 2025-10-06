import os
import base64
from pathlib import Path
from typing import Optional, List, Dict
from PIL import Image, ImageOps
from io import BytesIO


class ThumbnailCache:
    """Disk-based thumbnail cache for fast photo grid loading"""
    
    def __init__(self, cache_folder: str):
        self.cache_folder = Path(cache_folder)
        self.cache_folder.mkdir(parents=True, exist_ok=True)
        
    def _get_cache_key(self, face_id: int, bbox: Optional[List[float]], size: int) -> str:
        """Generate cache filename"""
        mode = "zoom" if bbox else "entire"
        return f"face_{face_id}_{mode}_{size}.jpg"
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """Get full path for cache file"""
        return self.cache_folder / cache_key
    
    def get_cached_thumbnail(self, face_id: int, image_path: str, 
                           bbox: Optional[List[float]], size: int) -> Optional[str]:
        """Try to get thumbnail from cache"""
        cache_key = self._get_cache_key(face_id, bbox, size)
        cache_path = self._get_cache_path(cache_key)
        
        if cache_path.exists():
            try:
                source_mtime = os.path.getmtime(image_path)
                cache_mtime = cache_path.stat().st_mtime
                
                if source_mtime > cache_mtime:
                    cache_path.unlink()
                    return None
                
                with open(cache_path, 'rb') as f:
                    img_bytes = f.read()
                    img_base64 = base64.b64encode(img_bytes).decode()
                    return f"data:image/jpeg;base64,{img_base64}"
                    
            except Exception as e:
                print(f"Cache read error for {cache_key}: {e}")
                return None
        
        return None
    
    def save_to_cache(self, face_id: int, bbox: Optional[List[float]], 
                     size: int, thumbnail_bytes: bytes) -> bool:
        """Save thumbnail to cache"""
        try:
            cache_key = self._get_cache_key(face_id, bbox, size)
            cache_path = self._get_cache_path(cache_key)
            
            with open(cache_path, 'wb') as f:
                f.write(thumbnail_bytes)
            
            return True
        except Exception as e:
            print(f"Cache write error: {e}")
            return False
    
    def create_thumbnail_with_cache(self, face_id: int, image_path: str, 
                                   size: int = 150, bbox: Optional[List[float]] = None) -> Optional[str]:
        """Create thumbnail with caching"""
        cached = self.get_cached_thumbnail(face_id, image_path, bbox, size)
        if cached:
            return cached
        
        try:
            img = Image.open(image_path)
            
            # Apply EXIF orientation if present
            img = ImageOps.exif_transpose(img)
            
            if bbox is not None:
                x1, y1, x2, y2 = bbox
                padding = 20
                
                x1 = max(0, x1 - padding)
                y1 = max(0, y1 - padding)
                x2 = min(img.width, x2 + padding)
                y2 = min(img.height, y2 + padding)
                
                img = img.crop((int(x1), int(y1), int(x2), int(y2)))
            
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            img_rgb = img.convert('RGB')
            
            buffer = BytesIO()
            img_rgb.save(buffer, format='JPEG', quality=85)
            img_bytes = buffer.getvalue()
            
            self.save_to_cache(face_id, bbox, size, img_bytes)
            
            img_base64 = base64.b64encode(img_bytes).decode()
            return f"data:image/jpeg;base64,{img_base64}"
            
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
            return None
    
    def get_cache_size(self) -> Dict[str, any]:
        """Get cache statistics"""
        total_size = 0
        file_count = 0
        
        for file_path in self.cache_folder.glob("*.jpg"):
            total_size += file_path.stat().st_size
            file_count += 1
        
        return {
            'size_bytes': total_size,
            'size_mb': round(total_size / (1024 * 1024), 2),
            'file_count': file_count,
            'avg_size_kb': round((total_size / file_count / 1024) if file_count > 0 else 0, 2)
        }
    
    def clear_cache(self) -> Dict[str, any]:
        """Clear all cached thumbnails"""
        stats = self.get_cache_size()
        
        for file_path in self.cache_folder.glob("*.jpg"):
            try:
                file_path.unlink()
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
        
        return stats
