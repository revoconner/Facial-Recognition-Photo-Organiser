import sqlite3
import lmdb
import pickle
import threading
from pathlib import Path
from typing import List, Optional, Tuple, Set, Dict
from collections import Counter
import numpy as np


class FaceDatabase:
    def __init__(self, db_folder: str):
        self.db_folder = Path(db_folder)
        self.db_folder.mkdir(parents=True, exist_ok=True)
        
        self.sqlite_path = self.db_folder / "metadata.db"
        
        # Thread-local storage for connections
        self._local = threading.local()
        
        # Initialize primary connection with optimizations
        self.conn = self._create_connection()
        
        self.lmdb_path = self.db_folder / "encodings.lmdb"
        self.env = lmdb.open(
            str(self.lmdb_path),
            map_size=10*1024*1024*1024,
            max_dbs=1,
            readahead=True,      # Enable readahead for speed
            metasync=False,      # Faster writes
            sync=False,          # Async writes
            writemap=True        # Direct memory mapping
        )
        
        self._init_tables()
        self._temp_table_counter = 0
        
        # Memory cache for frequently accessed data
        self._cache = {
            'active_clustering': None,
            'persons_list': None,
            'cache_timestamp': 0
        }
    
    def _create_connection(self):
        """Create optimized SQLite connection"""
        conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        # Apply performance optimizations
        cursor = conn.cursor()
        cursor.executescript('''
            PRAGMA journal_mode = WAL;
            PRAGMA synchronous = NORMAL;
            PRAGMA cache_size = -64000;
            PRAGMA temp_store = MEMORY;
            PRAGMA mmap_size = 268435456;
            PRAGMA page_size = 4096;
        ''')
        conn.commit()
        
        return conn
    
    def _get_connection(self):
        """Get thread-local connection"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = self._create_connection()
        return self._local.conn
    
    def _init_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS photos (
                photo_id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT,
                scan_status TEXT DEFAULT 'pending',
                date_added REAL DEFAULT (julianday('now'))
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS faces (
                face_id INTEGER PRIMARY KEY AUTOINCREMENT,
                photo_id INTEGER NOT NULL,
                bbox_x1 REAL,
                bbox_y1 REAL,
                bbox_x2 REAL,
                bbox_y2 REAL,
                FOREIGN KEY (photo_id) REFERENCES photos(photo_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clusterings (
                clustering_id INTEGER PRIMARY KEY AUTOINCREMENT,
                threshold REAL NOT NULL,
                created_at REAL DEFAULT (julianday('now')),
                is_active BOOLEAN DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cluster_assignments (
                face_id INTEGER NOT NULL,
                clustering_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                confidence_score REAL,
                PRIMARY KEY (face_id, clustering_id),
                FOREIGN KEY (face_id) REFERENCES faces(face_id),
                FOREIGN KEY (clustering_id) REFERENCES clusterings(clustering_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hidden_persons (
                clustering_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                hidden_at REAL DEFAULT (julianday('now')),
                PRIMARY KEY (clustering_id, person_id),
                FOREIGN KEY (clustering_id) REFERENCES clusterings(clustering_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hidden_photos (
                face_id INTEGER PRIMARY KEY,
                hidden_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (face_id) REFERENCES faces(face_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS face_tags (
                face_id INTEGER PRIMARY KEY,
                tag_name TEXT NOT NULL,
                tagged_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (face_id) REFERENCES faces(face_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tag_primary_photos (
                tag_name TEXT PRIMARY KEY,
                face_id INTEGER NOT NULL,
                set_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (face_id) REFERENCES faces(face_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_status ON photos(scan_status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_path ON photos(file_path)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_hash ON photos(file_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_assign ON cluster_assignments(clustering_id, person_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_face ON cluster_assignments(clustering_id, person_id, face_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_hidden_persons ON hidden_persons(clustering_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_hidden_photos ON hidden_photos(face_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_face_tags_name ON face_tags(tag_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_face_tags_combined ON face_tags(tag_name, face_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tag_primary_photos ON tag_primary_photos(tag_name)')
        
        self.conn.commit()
    
    def _get_temp_table_name(self) -> str:
        """Generate unique temp table name"""
        self._temp_table_counter += 1
        return f"temp_ids_{self._temp_table_counter}"
    
    def _execute_with_temp_table(self, cursor, ids: List[int], query_template: str, 
                                  params: tuple = (), id_column: str = 'id',
                                  fetch_results: bool = False):
        """Execute a query using a temporary table for large ID lists
        
        Args:
            fetch_results: If True, fetch and return results before dropping table.
                          Required for SELECT queries to avoid temp table cleanup issues.
        """
        if not ids:
            cursor.execute("SELECT * FROM (SELECT 1) WHERE 0=1")
            return [] if fetch_results else cursor
        
        if len(ids) <= 900:
            placeholders = ','.join('?' * len(ids))
            simple_query = query_template.replace(
                f'JOIN {{temp_table}} tt ON ft.face_id = tt.{id_column}',
                f'WHERE ft.face_id IN ({placeholders})'
            ).replace(
                f'JOIN {{temp_table}} tt ON f.face_id = tt.{id_column}',
                f'WHERE f.face_id IN ({placeholders})'
            )
            cursor.execute(simple_query, ids + list(params))
            return cursor.fetchall() if fetch_results else cursor
        
        temp_table = self._get_temp_table_name()
        
        try:
            cursor.execute(f'CREATE TEMP TABLE {temp_table} ({id_column} INTEGER)')
            
            batch_size = 900
            for i in range(0, len(ids), batch_size):
                batch = ids[i:i+batch_size]
                placeholders = ','.join(['(?)'] * len(batch))
                cursor.execute(f'INSERT INTO {temp_table} VALUES {placeholders}', batch)
            
            final_query = query_template.replace('{temp_table}', temp_table)
            cursor.execute(final_query, params)
            
            # Fetch results BEFORE dropping table if needed
            if fetch_results:
                results = cursor.fetchall()
            
            return results if fetch_results else cursor
        finally:
            try:
                cursor.execute(f'DROP TABLE IF EXISTS {temp_table}')
            except:
                pass
    
    def add_photo(self, file_path: str, file_hash: str) -> Optional[int]:
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO photos (file_path, file_hash)
                VALUES (?, ?)
            ''', (file_path, file_hash))
            self.conn.commit()
            
            if cursor.lastrowid:
                return cursor.lastrowid
            
            return self.get_photo_id(file_path)
        except Exception as e:
            print(f"Database error in add_photo: {e}")
            self.conn.rollback()
            return None
    
    def get_photo_id(self, file_path: str) -> Optional[int]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT photo_id FROM photos WHERE file_path = ?', (file_path,))
        row = cursor.fetchone()
        return row[0] if row else None
    
    def get_all_scanned_paths(self) -> Set[str]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT file_path FROM photos WHERE scan_status = "completed"')
        return {row[0] for row in cursor.fetchall()}
    
    def get_pending_and_error_paths(self) -> List[str]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT file_path FROM photos 
            WHERE scan_status IN ("pending", "error")
        ''')
        return [row[0] for row in cursor.fetchall()]
    
    def remove_deleted_photos(self, existing_paths: Set[str]) -> int:
        cursor = self.conn.cursor()
        cursor.execute('SELECT photo_id, file_path FROM photos')
        all_db_photos = cursor.fetchall()
        
        deleted_count = 0
        deleted_photo_ids = []
        for photo_id, file_path in all_db_photos:
            if file_path not in existing_paths:
                deleted_photo_ids.append(photo_id)
                deleted_count += 1
        
        if deleted_photo_ids:
            cursor.execute(f'SELECT face_id FROM faces WHERE photo_id IN ({",".join("?" * len(deleted_photo_ids))})', deleted_photo_ids)
            deleted_face_ids = [row[0] for row in cursor.fetchall()]
            
            if deleted_face_ids:
                self._execute_with_temp_table(
                    cursor, deleted_face_ids,
                    'DELETE FROM face_tags WHERE face_id IN (SELECT id FROM {temp_table})'
                )
                self._execute_with_temp_table(
                    cursor, deleted_face_ids,
                    'DELETE FROM tag_primary_photos WHERE face_id IN (SELECT id FROM {temp_table})'
                )
                self._execute_with_temp_table(
                    cursor, deleted_face_ids,
                    'DELETE FROM hidden_photos WHERE face_id IN (SELECT id FROM {temp_table})'
                )
            
            placeholders = ','.join('?' * len(deleted_photo_ids))
            cursor.execute(f'DELETE FROM faces WHERE photo_id IN ({placeholders})', deleted_photo_ids)
            cursor.execute(f'DELETE FROM photos WHERE photo_id IN ({placeholders})', deleted_photo_ids)
        
        self.conn.commit()
        return deleted_count
    
    def get_photos_needing_scan(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM photos 
            WHERE scan_status IN ("pending", "error")
        ''')
        return cursor.fetchone()[0]
    
    def add_face(self, photo_id: int, embedding: np.ndarray, bbox: List[float]) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO faces (photo_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2) 
            VALUES (?, ?, ?, ?, ?)
        ''', (photo_id, bbox[0], bbox[1], bbox[2], bbox[3]))
        self.conn.commit()
        face_id = cursor.lastrowid
        
        with self.env.begin(write=True) as txn:
            key = str(face_id).encode()
            value = pickle.dumps(embedding)
            txn.put(key, value)
        
        return face_id
    
    def get_face_embedding(self, face_id: int) -> Optional[np.ndarray]:
        with self.env.begin() as txn:
            key = str(face_id).encode()
            value = txn.get(key)
            if value:
                return pickle.loads(value)
        return None
    
    def get_all_embeddings(self) -> Tuple[List[int], np.ndarray]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT face_id FROM faces ORDER BY face_id')
        face_ids = [row[0] for row in cursor.fetchall()]
        
        embeddings = []
        valid_face_ids = []
        for face_id in face_ids:
            embedding = self.get_face_embedding(face_id)
            if embedding is not None:
                embeddings.append(embedding)
                valid_face_ids.append(face_id)
        
        if embeddings:
            return valid_face_ids, np.array(embeddings)
        return [], np.array([])
    
    def create_clustering(self, threshold: float) -> int:
        cursor = self.conn.cursor()
        
        # Get old clustering ID before deactivating
        cursor.execute('SELECT clustering_id FROM clusterings WHERE is_active = 1')
        old_clustering = cursor.fetchone()
        old_clustering_id = old_clustering[0] if old_clustering else None
        
        cursor.execute('UPDATE clusterings SET is_active = 0')
        cursor.execute('INSERT INTO clusterings (threshold, is_active) VALUES (?, 1)', (threshold,))
        new_clustering_id = cursor.lastrowid
        
        # Migrate hidden persons from old clustering to new one
        if old_clustering_id:
            cursor.execute('''
                INSERT OR IGNORE INTO hidden_persons (clustering_id, person_id)
                SELECT ?, person_id FROM hidden_persons
                WHERE clustering_id = ?
            ''', (new_clustering_id, old_clustering_id))
            print(f"Migrated hidden persons from clustering {old_clustering_id} to {new_clustering_id}")
        
        self.conn.commit()
        
        # Invalidate cache after clustering change
        self.invalidate_cache()
        
        return new_clustering_id
    
    def save_cluster_assignments(self, clustering_id: int, face_ids: List[int], 
                                 person_ids: List[int], confidences: List[float]):
        cursor = self.conn.cursor()
        data = [(fid, clustering_id, pid, conf) 
                for fid, pid, conf in zip(face_ids, person_ids, confidences)]
        cursor.executemany('''
            INSERT OR REPLACE INTO cluster_assignments 
            (face_id, clustering_id, person_id, confidence_score)
            VALUES (?, ?, ?, ?)
        ''', data)
        self.conn.commit()
    
    def get_active_clustering(self) -> Optional[dict]:
        """Get active clustering with caching"""
        import time
        current_time = time.time()
        
        # Cache for 5 seconds
        if (self._cache['active_clustering'] is not None and 
            current_time - self._cache['cache_timestamp'] < 5):
            return self._cache['active_clustering']
        
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM clusterings WHERE is_active = 1')
        row = cursor.fetchone()
        result = dict(row) if row else None
        
        # Update cache
        self._cache['active_clustering'] = result
        self._cache['cache_timestamp'] = current_time
        
        return result
    
    def invalidate_cache(self):
        """Invalidate memory cache (call after clustering changes)"""
        self._cache['active_clustering'] = None
        self._cache['persons_list'] = None
        self._cache['cache_timestamp'] = 0
    
    def get_persons_in_clustering(self, clustering_id: int) -> List[dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT person_id, COUNT(*) as face_count
            FROM cluster_assignments
            WHERE clustering_id = ?
            GROUP BY person_id
            ORDER BY person_id
        ''', (clustering_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_face_ids_for_person(self, clustering_id: int, person_id: int) -> List[int]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT face_id FROM cluster_assignments
            WHERE clustering_id = ? AND person_id = ?
        ''', (clustering_id, person_id))
        return [row[0] for row in cursor.fetchall()]
    
    def get_photos_by_person(self, clustering_id: int, person_id: int) -> List[dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT DISTINCT p.file_path, f.face_id, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2
            FROM photos p
            JOIN faces f ON p.photo_id = f.photo_id
            JOIN cluster_assignments ca ON f.face_id = ca.face_id
            WHERE ca.clustering_id = ? AND ca.person_id = ?
        ''', (clustering_id, person_id))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_face_data(self, face_id: int) -> Optional[dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT f.face_id, f.photo_id, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, p.file_path
            FROM faces f
            JOIN photos p ON f.photo_id = p.photo_id
            WHERE f.face_id = ?
        ''', (face_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def hide_person(self, clustering_id: int, person_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO hidden_persons (clustering_id, person_id)
            VALUES (?, ?)
        ''', (clustering_id, person_id))
        self.conn.commit()
    
    def unhide_person(self, clustering_id: int, person_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM hidden_persons 
            WHERE clustering_id = ? AND person_id = ?
        ''', (clustering_id, person_id))
        self.conn.commit()
    
    def get_hidden_persons(self, clustering_id: int) -> Set[int]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT person_id FROM hidden_persons
            WHERE clustering_id = ?
        ''', (clustering_id,))
        return {row[0] for row in cursor.fetchall()}
    
    def hide_photo(self, face_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO hidden_photos (face_id)
            VALUES (?)
        ''', (face_id,))
        self.conn.commit()
    
    def unhide_photo(self, face_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM hidden_photos 
            WHERE face_id = ?
        ''', (face_id,))
        self.conn.commit()
    
    def get_hidden_photos(self) -> Set[int]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT face_id FROM hidden_photos')
        return {row[0] for row in cursor.fetchall()}
    
    def set_primary_photo_for_tag(self, tag_name: str, face_id: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO tag_primary_photos (tag_name, face_id)
            VALUES (?, ?)
        ''', (tag_name, face_id))
        self.conn.commit()
    
    def get_primary_photo_for_tag(self, tag_name: str) -> Optional[int]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT face_id FROM tag_primary_photos
            WHERE tag_name = ?
        ''', (tag_name,))
        row = cursor.fetchone()
        if row:
            face_id = row[0]
            face_data = self.get_face_data(face_id)
            if face_data:
                return face_id
            else:
                cursor.execute('DELETE FROM tag_primary_photos WHERE tag_name = ?', (tag_name,))
                self.conn.commit()
                return None
        return None
    
    def tag_faces(self, face_ids: List[int], tag_name: str):
        cursor = self.conn.cursor()
        data = [(fid, tag_name) for fid in face_ids]
        cursor.executemany('''
            INSERT OR REPLACE INTO face_tags (face_id, tag_name)
            VALUES (?, ?)
        ''', data)
        self.conn.commit()
    
    def untag_faces(self, face_ids: List[int]):
        """Fixed version using temp table for large lists"""
        if not face_ids:
            return
        
        cursor = self.conn.cursor()
        self._execute_with_temp_table(
            cursor, face_ids,
            'DELETE FROM face_tags WHERE face_id IN (SELECT id FROM {temp_table})'
        )
        self.conn.commit()
    
    def get_face_tags(self, face_ids: List[int]) -> Dict[int, str]:
        """Get tags for a list of face IDs. Handles large lists using temp tables."""
        if not face_ids:
            return {}
        
        cursor = self.conn.cursor()
        
        if len(face_ids) <= 900:
            placeholders = ','.join('?' * len(face_ids))
            cursor.execute(f'''
                SELECT face_id, tag_name FROM face_tags
                WHERE face_id IN ({placeholders})
            ''', face_ids)
            rows = cursor.fetchall()
        else:
            rows = self._execute_with_temp_table(
                cursor, face_ids,
                '''SELECT ft.face_id, ft.tag_name 
                   FROM face_tags ft
                   JOIN {temp_table} tt ON ft.face_id = tt.id''',
                id_column='id',
                fetch_results=True
            )
        
        return {row[0]: row[1] for row in rows}
    
    def get_person_tag_summary(self, face_ids: List[int]) -> Optional[Dict]:
        """Fixed version - handles large face_id lists"""
        if not face_ids:
            return None
        
        tags = self.get_face_tags(face_ids)
        
        if not tags:
            return None
        
        tag_counts = Counter(tags.values())
        most_common_tag, count = tag_counts.most_common(1)[0]
        
        return {
            'name': most_common_tag,
            'tagged_count': count,
            'total_count': len(face_ids),
            'all_tags': dict(tag_counts)
        }
    
    def update_photo_status(self, photo_id: int, status: str):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE photos SET scan_status = ? WHERE photo_id = ?', 
                      (status, photo_id))
        self.conn.commit()
    
    def get_total_faces(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM faces')
        return cursor.fetchone()[0]
    
    def get_total_photos(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM photos WHERE scan_status = "completed"')
        return cursor.fetchone()[0]
    
    def close(self):
        """Close all database connections"""
        # Close main connection
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()
        
        # Close thread-local connections
        if hasattr(self, '_local') and hasattr(self._local, 'conn'):
            if self._local.conn:
                self._local.conn.close()
        
        # Close LMDB
        if hasattr(self, 'env') and self.env:
            self.env.close()
