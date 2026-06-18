import sqlite3
import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

backend_dir = Path(__file__).parent
load_dotenv(dotenv_path=backend_dir / ".env")

db_path = backend_dir / "data" / "database" / "production.db"

def deduplicate_sqlite():
    if not db_path.exists():
        print(f"Local SQLite database not found at: {db_path}")
        return False, 0, 0

    print("Connecting to local SQLite database...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        # Check rows before
        cursor.execute("SELECT COUNT(*) FROM customer_embeddings")
        before_count = cursor.fetchone()[0]
        
        # Deduplicate: Keep the row with minimum ID for each distinct (customer_id, face_embedding)
        cursor.execute("""
            DELETE FROM customer_embeddings
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM customer_embeddings
                GROUP BY customer_id, face_embedding
            )
        """)
        conn.commit()
        
        # Check rows after
        cursor.execute("SELECT COUNT(*) FROM customer_embeddings")
        after_count = cursor.fetchone()[0]
        deleted_count = before_count - after_count
        print(f"SQLite Deduplication Complete:")
        print(f"  Rows before: {before_count}")
        print(f"  Rows after: {after_count}")
        print(f"  Deleted: {deleted_count} duplicates")
        return True, before_count, after_count
    except Exception as e:
        print("Error deduplicating SQLite:", e)
        return False, 0, 0
    finally:
        conn.close()

def sync_to_supabase():
    supabase_url = os.getenv("SUPABASE_URL")
    if not supabase_url:
        print("No SUPABASE_URL configured in .env. Skipping sync.")
        return False

    print("Connecting to Supabase PostgreSQL database...")
    try:
        pg_conn = psycopg2.connect(supabase_url)
        pg_cursor = pg_conn.cursor()
        
        # 1. Fetch valid customer_ids from Supabase customers table to avoid foreign key violations
        pg_cursor.execute("SELECT customer_id FROM customers")
        supabase_customer_ids = {row[0] for row in pg_cursor.fetchall()}
        print(f"Found {len(supabase_customer_ids)} customers in Supabase.")

        # 2. Fetch all deduplicated customer embeddings from SQLite database
        if not db_path.exists():
            print("No local SQLite database found to read embeddings from.")
            pg_conn.close()
            return False

        conn_sqlite = sqlite3.connect(db_path)
        sqlite_cursor = conn_sqlite.cursor()
        sqlite_cursor.execute("SELECT customer_id, face_embedding, embedding_dim, model_name, created_at, updated_at FROM customer_embeddings")
        local_embeddings = sqlite_cursor.fetchall()
        conn_sqlite.close()

        print(f"Fetched {len(local_embeddings)} embedding records from SQLite.")

        # 3. Clear existing embeddings on Supabase to ensure a clean slate
        pg_cursor.execute("DELETE FROM customer_embeddings")
        print("Cleared existing embeddings from Supabase customer_embeddings table.")

        # 4. Insert the clean embeddings into Supabase
        synced_count = 0
        skipped_count = 0
        for row in local_embeddings:
            cid, blob, dim, model, created_at, updated_at = row
            if cid not in supabase_customer_ids:
                print(f"  Skipping embedding for '{cid}': customer does not exist in Supabase 'customers' table.")
                skipped_count += 1
                continue
                
            pg_cursor.execute("""
                INSERT INTO customer_embeddings (customer_id, face_embedding, embedding_dim, model_name, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (cid, blob, dim, model, created_at, updated_at))
            synced_count += 1

        pg_conn.commit()
        print(f"Supabase Sync Complete:")
        print(f"  Successfully synced: {synced_count} records")
        print(f"  Skipped (no matching customer in Supabase): {skipped_count} records")
        pg_conn.close()
        return True
    except Exception as e:
        print("Error syncing to Supabase:", e)
        return False

if __name__ == "__main__":
    print("=== DATABASE CLEANUP & SYNC START ===")
    success_sqlite, before, after = deduplicate_sqlite()
    if success_sqlite:
        sync_to_supabase()
    print("=== DATABASE CLEANUP & SYNC END ===")
