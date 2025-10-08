import sqlite3
from pathlib import Path
import os

def remove_annie_tags():
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
    
    cursor.execute("SELECT COUNT(*) FROM face_tags WHERE tag_name = 'Annie'")
    count_before = cursor.fetchone()[0]
    
    if count_before == 0:
        print("No 'Annie' tags found in database")
        conn.close()
        return
    
    print(f"\nFound {count_before} faces tagged as 'Annie'")
    confirm = input("Delete all 'Annie' tags? (yes/no): ")
    
    if confirm.lower() != 'yes':
        print("Cancelled")
        conn.close()
        return
    
    cursor.execute("DELETE FROM face_tags WHERE tag_name = 'Annie'")
    deleted_tags = cursor.rowcount
    
    cursor.execute("DELETE FROM tag_primary_photos WHERE tag_name = 'Annie'")
    deleted_primary = cursor.rowcount
    
    conn.commit()
    
    print(f"\nDeleted {deleted_tags} face tags")
    print(f"Deleted {deleted_primary} primary photo assignment")
    print("\nDone! Restart the app to recalibrate with clean Annie tags")
    
    conn.close()

if __name__ == "__main__":
    remove_annie_tags()