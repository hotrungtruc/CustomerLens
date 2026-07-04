import psycopg2
import os

supabase_url = None
with open(".env", "r") as f:
    for line in f:
        line = line.strip()
        if line.startswith("SUPABASE_URL="):
            supabase_url = line.split("=", 1)[1].strip('"').strip("'")

try:
    conn = psycopg2.connect(supabase_url)
    cur = conn.cursor()

    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public';
    """)
    tables = cur.fetchall()
    
    print("=== TABLES IN PUBLIC SCHEMA ===")
    for table in tables:
        table_name = table[0]
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]
            print(f"- {table_name}: {count} rows")
            
            # Print columns
            cur.execute(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}';
            """)
            columns = cur.fetchall()
            print("  Columns:", ", ".join([f"{c[0]} ({c[1]})" for c in columns]))
            
        except Exception as e:
            conn.rollback()
            print(f"- {table_name}: Error getting count: {e}")

    cur.close()
    conn.close()
except Exception as e:
    print("Database connection failed:", e)
