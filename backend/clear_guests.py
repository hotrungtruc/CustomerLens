import sqlite3
import os

DB_PATH = 'data/database/production.db'
GUEST_CACHE = 'data/encodings/GuestCache.p'

print("Clearing GUEST data...")

if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM customer_embeddings WHERE customer_id LIKE 'GUEST_%'")
    cursor.execute("DELETE FROM customers WHERE customer_id LIKE 'GUEST_%'")
    conn.commit()
    conn.close()
    print("Deleted guests from production.db")
else:
    print("DB not found at", DB_PATH)

if os.path.exists(GUEST_CACHE):
    os.remove(GUEST_CACHE)
    print("Deleted GuestCache.p")
else:
    print("GuestCache.p not found.")
