import psycopg2
import os

supabase_url = None
with open(".env", "r") as f:
    for line in f:
        line = line.strip()
        if line.startswith("SUPABASE_URL="):
            supabase_url = line.split("=", 1)[1].strip('"').strip("'")

def update_model_name():
    try:
        print("Connecting to the database...")
        conn = psycopg2.connect(supabase_url)
        conn.autocommit = True
        cur = conn.cursor()

        print("Updating model_name 'w600k_mbf' to 'edgeface_s_gamma_05' in customer_embeddings...")
        cur.execute("""
            UPDATE customer_embeddings 
            SET model_name = 'edgeface_s_gamma_05' 
            WHERE model_name = 'w600k_mbf';
        """)
        print(f"=> Successfully updated {cur.rowcount} rows.")

        cur.execute("""
            ALTER TABLE customer_embeddings 
            ALTER COLUMN model_name SET DEFAULT 'edgeface_s_gamma_05';
        """)
        print("=> Updated column default value to 'edgeface_s_gamma_05'.")

        cur.close()
        conn.close()
        print("Database update completed successfully!")

    except Exception as e:
        if 'conn' in locals() and not conn.autocommit:
            conn.rollback()
        print("Error during update:", e)

if __name__ == "__main__":
    update_model_name()
