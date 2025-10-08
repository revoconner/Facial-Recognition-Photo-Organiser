import sqlite3
from pathlib import Path
import os

def clear_tags_and_clustering():
    appdata = os.environ.get('APPDATA')
    if appdata:
        db_path = Path(appdata) / "facial_recognition" / "face_data" / "metadata.db"
    else:
        db_path = Path.home() / "AppData" / "Roaming" / "facial_recognition" / "face_data" / "metadata.db"
    
    if not db_path.exists():
        print(f"Database not found at: {db_path}")
        return
    
    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\nClearing old data...")
    
    cursor.execute("DELETE FROM face_tags")
    tags_deleted = cursor.rowcount
    print(f"Deleted {tags_deleted} face tags")
    
    cursor.execute("DELETE FROM tag_primary_photos")
    primary_deleted = cursor.rowcount
    print(f"Deleted {primary_deleted} primary photo assignments")
    
    cursor.execute("DELETE FROM cluster_assignments")
    assignments_deleted = cursor.rowcount
    print(f"Deleted {assignments_deleted} cluster assignments")
    
    cursor.execute("DELETE FROM hidden_persons")
    hidden_deleted = cursor.rowcount
    print(f"Deleted {hidden_deleted} hidden persons")
    
    cursor.execute("DELETE FROM clusterings")
    clusterings_deleted = cursor.rowcount
    print(f"Deleted {clusterings_deleted} clusterings")
    
    conn.commit()
    
    cursor.execute("SELECT COUNT(*) FROM faces")
    face_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM photos WHERE scan_status = 'completed'")
    photo_count = cursor.fetchone()[0]
    
    print(f"\nDatabase cleaned successfully!")
    print(f"Kept: {photo_count} photos, {face_count} face embeddings")
    print(f"\nNext steps:")
    print(f"1. Start the app")
    print(f"2. It will auto-cluster with Chinese Whispers")
    print(f"3. Manually rename people (this will set is_manual=1)")
    print(f"4. Future recalibrations will merge clusters with same manual tags")
    
    conn.close()

if __name__ == "__main__":
    clear_tags_and_clustering()