import psycopg2
import os

# Read database URL from .env
supabase_url = None
with open(".env", "r") as f:
    for line in f:
        line = line.strip()
        if line.startswith("SUPABASE_URL="):
            supabase_url = line.split("=", 1)[1].strip('"').strip("'")

def apply_updates():
    try:
        print("Connecting to the database...")
        conn = psycopg2.connect(supabase_url)
        conn.autocommit = True
        cur = conn.cursor()

        print("1. Adding soft delete columns (is_deleted)...")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE customer_embeddings ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;")
        print("=> Soft delete columns added successfully.")

        print("2. Checking if recognize_logs is already partitioned...")
        # Check if the table is partitioned
        cur.execute("""
            SELECT relkind 
            FROM pg_class 
            WHERE relname = 'recognize_logs';
        """)
        relkind = cur.fetchone()
        if relkind and relkind[0] == 'p':
            print("=> recognize_logs is already a partitioned table. Skipping partition conversion.")
        else:
            print("=> Converting recognize_logs into a partitioned table...")
            
            # Start transaction for table conversion
            conn.autocommit = False
            
            cur.execute("ALTER TABLE recognize_logs RENAME TO recognize_logs_old;")
            
            cur.execute("""
                CREATE TABLE recognize_logs (
                    id UUID DEFAULT gen_random_uuid(),
                    opeid UUID NOT NULL,
                    camera_id VARCHAR(255) NOT NULL,
                    customer_id VARCHAR(255) DEFAULT NULL,
                    track_id INTEGER DEFAULT NULL,
                    bbox JSONB DEFAULT NULL,
                    connection_id VARCHAR(64) DEFAULT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    moderator_username VARCHAR(255) NOT NULL DEFAULT 'admin',
                    PRIMARY KEY (id, moderator_username)
                ) PARTITION BY LIST (moderator_username);
            """)
            
            cur.execute("CREATE TABLE recognize_logs_default PARTITION OF recognize_logs DEFAULT;")
            
            print("=> Migrating data from recognize_logs_old to new partitioned table...")
            cur.execute("""
                INSERT INTO recognize_logs (id, opeid, camera_id, customer_id, track_id, bbox, connection_id, timestamp, moderator_username)
                SELECT 
                    id, opeid, camera_id, customer_id, track_id, bbox, connection_id, timestamp, 
                    'admin' 
                FROM recognize_logs_old;
            """)
            
            cur.execute("DROP TABLE recognize_logs_old;")
            
            conn.commit()
            conn.autocommit = True
            print("=> Data migration and partitioning completed successfully.")

        print("3. Applying Vacuum Tuning...")
        cur.execute("""
            ALTER TABLE recognize_logs_default SET (
                autovacuum_vacuum_scale_factor = 0.05,
                autovacuum_analyze_scale_factor = 0.02,
                autovacuum_vacuum_cost_limit = 1000
            );
        """)
        cur.execute("""
            ALTER TABLE customer_embeddings SET (
                autovacuum_vacuum_scale_factor = 0.05,
                autovacuum_analyze_scale_factor = 0.02
            );
        """)
        cur.execute("""
            ALTER TABLE customers SET (
                autovacuum_vacuum_scale_factor = 0.1,
                autovacuum_analyze_scale_factor = 0.05
            );
        """)
        print("=> Vacuum tuning applied successfully.")

        cur.close()
        conn.close()
        print("All database schema updates completed successfully!")

    except Exception as e:
        if 'conn' in locals() and not conn.autocommit:
            conn.rollback()
        print("Error applying database updates:", e)

if __name__ == "__main__":
    apply_updates()
