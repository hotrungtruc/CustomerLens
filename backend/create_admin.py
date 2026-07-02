import hashlib
import sys
from app.db.connection import get_db_connection, ensure_schema

def main():
    try:
        conn = get_db_connection()
        ensure_schema(conn)
        
        username = "admin"
        password = "admin123"
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        role = "admin"
        cameras = None

        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, cameras)
            VALUES (?, ?, ?, ?)
            """,
            (username, pwd_hash, role, cameras),
        )
        conn.commit()
        conn.close()
        print("Admin user created successfully.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
