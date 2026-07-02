import os
import sys
import glob
import cv2
import uuid
import time

# Add backend directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.insight_embedding import InsightEmbedder
from app.db.connection import get_db_connection, upsert_customer, _embedding_to_blob
from app.db.vector_search import insert_embedding_with_vector
import psycopg2

DATASET_PATH = r"C:\SCHOOL\asian_celeb_112x112_folders"
BATCH_SIZE = 100

def get_connection_with_retry(retries=3, delay=5):
    for attempt in range(retries):
        try:
            conn = get_db_connection()
            return conn
        except Exception as e:
            print(f"Failed to connect to DB: {e}. Retrying in {delay}s...")
            time.sleep(delay)
    raise Exception("Could not connect to DB after multiple retries.")

def main():
    if not os.path.exists(DATASET_PATH):
        print(f"Dataset path {DATASET_PATH} not found!")
        return

    print("Initializing embedder...")
    embedder = InsightEmbedder()
    
    person_folders = [f.path for f in os.scandir(DATASET_PATH) if f.is_dir()]
    total_people = len(person_folders)
    print(f"Found {total_people} people in dataset.")
    
    conn = get_connection_with_retry()
    
    count = 0
    batch_count = 0
    
    for i, folder in enumerate(person_folders):
        person_name = os.path.basename(folder)
        
        # Find the first image in the folder
        image_files = glob.glob(os.path.join(folder, "*.[jp][pn]*[g]")) # match jpg, jpeg, png
        if not image_files:
            continue
            
        img_path = image_files[0]
        frame = cv2.imread(img_path)
        if frame is None:
            continue
            
        detections = embedder.detect(frame)
        if len(detections[0]) == 0:
            print(f"[{i+1}/{total_people}] No face detected in {img_path}")
            continue
            
        # Take first face
        bbox, landmark, score = detections[0][0], detections[1][0], detections[2][0]
        
        embedding = embedder.get_embedding(frame, landmark)
        if embedding is None:
            print(f"[{i+1}/{total_people}] Failed to extract embedding for {img_path}")
            continue
            
        customer_id = f"test_{uuid.uuid4().hex[:8]}"
        blob = _embedding_to_blob(embedding)
        
        try:
            upsert_customer(
                conn=conn, 
                customer_id=customer_id, 
                name=f"Celeb {person_name}",
                note="From asian_celeb dataset test"
            )
            
            insert_embedding_with_vector(
                conn=conn,
                customer_id=customer_id,
                face_embedding_blob=blob,
                embedding_np=embedding
            )
            batch_count += 1
            count += 1
            print(f"[{i+1}/{total_people}] Processed Celeb {person_name}")
            
            if batch_count >= BATCH_SIZE:
                conn.commit()
                print(f"+++ Committed batch of {batch_count}. Total ingested: {count} +++")
                batch_count = 0
                
        except psycopg2.OperationalError as e:
            print(f"DB Connection error: {e}. Reconnecting...")
            # Try to reconnect
            conn.close()
            time.sleep(2)
            conn = get_connection_with_retry()
            # Retry this current one
            upsert_customer(conn, customer_id, name=f"Celeb {person_name}", note="From asian_celeb dataset test")
            insert_embedding_with_vector(conn, customer_id, blob, embedding)
            conn.commit()
            batch_count = 0
            
        except psycopg2.InterfaceError as e:
            print(f"DB Interface error: {e}. Reconnecting...")
            conn = get_connection_with_retry()
            upsert_customer(conn, customer_id, name=f"Celeb {person_name}", note="From asian_celeb dataset test")
            insert_embedding_with_vector(conn, customer_id, blob, embedding)
            conn.commit()
            batch_count = 0
            
        except Exception as e:
            print(f"Error processing {person_name}: {e}")
            conn.rollback()
            batch_count = 0
            continue
            
    # Final commit for remaining
    if batch_count > 0:
        try:
            conn.commit()
            print(f"+++ Committed final batch of {batch_count}. Total ingested: {count} +++")
        except Exception as e:
            print(f"Final commit error: {e}")
            
    conn.close()
    print(f"Done! Successfully ingested {count} out of {total_people} people.")

if __name__ == "__main__":
    main()
