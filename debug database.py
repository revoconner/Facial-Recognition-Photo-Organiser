
"""
Debug script to check hiding/renaming issues with large datasets
Run this separately to diagnose the problem
"""

import sqlite3
import os
from pathlib import Path
from collections import Counter

def check_database_issues():
    """Check for issues in the database"""
    
    # Get database path
    appdata = os.environ.get('APPDATA')
    db_path = Path(appdata) / "facial_recognition" / "face_data" / "metadata.db"
    
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("="*60)
    print("DATABASE DIAGNOSTIC REPORT")
    print("="*60)
    
    # Get active clustering
    cursor.execute('SELECT clustering_id, threshold FROM clusterings WHERE is_active = 1')
    clustering = cursor.fetchone()
    if not clustering:
        print("No active clustering found!")
        return
    
    clustering_id = clustering[0]
    print(f"Active clustering: ID={clustering_id}, Threshold={clustering[1]}%")
    
    # Check for persons with many faces
    cursor.execute('''
        SELECT person_id, COUNT(*) as face_count 
        FROM cluster_assignments 
        WHERE clustering_id = ?
        GROUP BY person_id 
        HAVING COUNT(*) > 999
        ORDER BY face_count DESC
        LIMIT 10
    ''', (clustering_id,))
    
    large_persons = cursor.fetchall()
    print(f"\nPersons with >999 faces: {len(large_persons)}")
    for person_id, face_count in large_persons:
        print(f"  Person {person_id}: {face_count} faces")
        
        # Check if tagged
        cursor.execute('''
            SELECT ft.tag_name, COUNT(*) as count
            FROM face_tags ft
            JOIN cluster_assignments ca ON ft.face_id = ca.face_id
            WHERE ca.clustering_id = ? AND ca.person_id = ?
            GROUP BY ft.tag_name
        ''', (clustering_id, person_id))
        
        tags = cursor.fetchall()
        if tags:
            for tag_name, count in tags:
                print(f"    Tagged as '{tag_name}': {count}/{face_count} faces")
        else:
            print(f"    No tags found")
    
    # Check hidden persons
    cursor.execute('''
        SELECT hp.person_id, COUNT(ca.face_id) as face_count
        FROM hidden_persons hp
        LEFT JOIN cluster_assignments ca ON hp.person_id = ca.person_id 
            AND hp.clustering_id = ca.clustering_id
        WHERE hp.clustering_id = ?
        GROUP BY hp.person_id
    ''', (clustering_id,))
    
    hidden_persons = cursor.fetchall()
    print(f"\nHidden persons: {len(hidden_persons)}")
    for person_id, face_count in hidden_persons[:10]:
        print(f"  Person {person_id}: {face_count} faces")
    
    # Check for orphaned tags (tags without corresponding faces)
    cursor.execute('''
        SELECT COUNT(*) FROM face_tags ft
        LEFT JOIN faces f ON ft.face_id = f.face_id
        WHERE f.face_id IS NULL
    ''')
    orphaned = cursor.fetchone()[0]
    print(f"\nOrphaned tags (no corresponding face): {orphaned}")
    
    # Check for duplicate tags
    cursor.execute('''
        SELECT face_id, COUNT(*) 
        FROM face_tags 
        GROUP BY face_id 
        HAVING COUNT(*) > 1
    ''')
    duplicates = cursor.fetchall()
    if duplicates:
        print(f"\nFaces with duplicate tags: {len(duplicates)}")
    
    # Database statistics
    cursor.execute('SELECT COUNT(*) FROM photos WHERE scan_status = "completed"')
    photos = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM faces')
    faces = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM face_tags')
    tags = cursor.fetchone()[0]
    
    print(f"\nDatabase Statistics:")
    print(f"  Photos: {photos}")
    print(f"  Faces: {faces}")
    print(f"  Tagged faces: {tags}")
    print(f"  Untagged faces: {faces - tags}")
    
    conn.close()
    print("\nDiagnostic complete!")

if __name__ == '__main__':
    check_database_issues()