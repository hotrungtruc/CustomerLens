import sys
from app.db.connection import get_db_connection

def clean_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Fetch all base tables in public schema
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
          AND table_type = 'BASE TABLE'
    """)
    rows = cursor.fetchall()
    all_tables = [r['table_name'] for r in rows]
    print(f"All tables found in public schema: {all_tables}")
    
    # Tables to keep user data in
    # Keep users table, clean out users that are not admin or moderator if any
    cursor.execute("""
        DELETE FROM users 
        WHERE role NOT IN ('admin', 'moderator') 
          AND username NOT IN ('admin', 'moderator1', 'moderator2')
    """)
    conn.commit()
    
    # Tables to truncate / delete
    # Note: recognize_logs is partitioned, so TRUNCATE TABLE recognize_logs CASCADE will truncate parent and all partitions.
    tables_to_clear = [
        'customer_embeddings',
        'customers',
        'user_camera_permissions',
        'camera_connections',
        'camera_device_credentials',
        'cameras',
        'recognize_logs'
    ]
    
    # Add any extra operational tables if present
    extra_tables = ['orders', 'order_items', 'products', 'table_bookings']
    for ext in extra_tables:
        if ext in all_tables:
            tables_to_clear.append(ext)
            
    print(f"Clearing tables: {tables_to_clear}")
    
    for t in tables_to_clear:
        if t in all_tables:
            try:
                cursor.execute(f"TRUNCATE TABLE {t} CASCADE;")
                conn.commit()
                print(f"Successfully truncated: {t}")
            except Exception as e:
                conn.rollback()
                print(f"Error truncating {t}: {e}, falling back to DELETE")
                try:
                    cursor.execute(f"DELETE FROM {t};")
                    conn.commit()
                    print(f"Successfully deleted all rows from: {t}")
                except Exception as ex:
                    conn.rollback()
                    print(f"Failed to clear {t}: {ex}")

    # Re-check counts
    print("\n--- NEW ROW COUNTS ---")
    for t in ['users'] + tables_to_clear:
        if t in all_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) as cnt FROM {t}")
                res = cursor.fetchone()
                cnt = res['cnt'] if isinstance(res, dict) else res[0]
                print(f"{t}: {cnt}")
            except Exception as e:
                conn.rollback()
                print(f"{t}: count error ({e})")
                
    # Also print remaining users
    cursor.execute("SELECT id, username, role FROM users")
    remaining_users = cursor.fetchall()
    print(f"\nRemaining users: {remaining_users}")

if __name__ == '__main__':
    clean_database()
