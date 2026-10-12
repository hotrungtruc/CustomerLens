import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.connection import get_db_connection

conn = get_db_connection()
try:
    conn.execute("DELETE FROM customer_embeddings WHERE customer_id LIKE 'LN%'")
    conn.execute("DELETE FROM recognize_logs WHERE customer_id LIKE 'LN%'")
    conn.execute("DELETE FROM customers WHERE customer_id LIKE 'LN%'")
    conn.commit()
    print("Database test cleanup complete.")
finally:
    conn.close()
