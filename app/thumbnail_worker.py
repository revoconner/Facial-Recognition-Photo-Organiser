import threading
import queue
from typing import Optional, List


class ThumbnailWorker:
    """Background worker that pre-generates thumbnails during photo scanning"""
    
    def __init__(self, thumbnail_cache, num_threads=4):
        self.thumbnail_cache = thumbnail_cache
        self.queue = queue.Queue()
        self.workers = []
        self.stop_flag = threading.Event()
        self.total_queued = 0
        self.total_processed = 0
        
        # Start worker threads
        for i in range(num_threads):
            worker = threading.Thread(
                target=self._worker_loop, 
                daemon=True,
                name=f"ThumbnailWorker-{i}"
            )
            worker.start()
            self.workers.append(worker)
        
        print(f"Started {num_threads} thumbnail worker threads")
    
    def _worker_loop(self):
        """Background worker that processes thumbnail jobs"""
        while not self.stop_flag.is_set():
            try:
                job = self.queue.get(timeout=1)
                if job is None:
                    break
                
                face_id, image_path, bbox, size = job
                
                # Generate thumbnail (uses cache internally)
                try:
                    self.thumbnail_cache.create_thumbnail_with_cache(
                        face_id, image_path, size, bbox
                    )
                    self.total_processed += 1
                except Exception as e:
                    print(f"Error generating thumbnail for face {face_id}: {e}")
                
                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Thumbnail worker error: {e}")
    
    def add_job(self, face_id: int, image_path: str, 
                bbox: Optional[List[float]], size: int = 180):
        """Add thumbnail generation job to queue"""
        self.queue.put((face_id, image_path, bbox, size))
        self.total_queued += 1
    
    def get_progress(self):
        """Get progress of thumbnail generation"""
        return {
            'queued': self.total_queued,
            'processed': self.total_processed,
            'pending': self.queue.qsize(),
            'percent': (self.total_processed / self.total_queued * 100) 
                      if self.total_queued > 0 else 0
        }
    
    def wait_completion(self, timeout=None):
        """Wait for all queued jobs to complete"""
        try:
            self.queue.join()
            return True
        except:
            return False
    
    def stop(self):
        """Stop all worker threads"""
        print(f"Stopping thumbnail workers ({self.total_processed}/{self.total_queued} completed)")
        self.stop_flag.set()
        
        # Send stop signals
        for _ in self.workers:
            try:
                self.queue.put(None)
            except:
                pass
        
        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=2)
        
        print("Thumbnail workers stopped")
