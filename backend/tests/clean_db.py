import sqlite3

conn = sqlite3.connect("data/database/production.db")
cur = conn.cursor()
cur.execute("DELETE FROM customers WHERE customer_id LIKE 'LN%' OR customer_id >= '013'")
cur.execute("DELETE FROM customer_embeddings WHERE customer_id LIKE 'LN%' OR customer_id >= '013'")
cur.execute("DELETE FROM recognize_logs WHERE customer_id LIKE 'LN%' OR customer_id >= '013'")
conn.commit()
remaining = [r[0] for r in cur.execute("SELECT customer_id FROM customers").fetchall()]
print(f"Cleaned DB. Remaining customers ({len(remaining)}): {remaining}")
conn.close()

