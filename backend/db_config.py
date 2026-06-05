import os
from pathlib import Path

# ===== Environment Variables (create a .env file) =====
# SUPABASE_URL=postgresql://postgres:PASSWORD@project.supabase.co:5432/postgres
# Or set individual variables:
# SUPABASE_HOST=project.supabase.co
# SUPABASE_USER=postgres
# SUPABASE_PASSWORD=your-password
# SUPABASE_PORT=5432
# SUPABASE_DB=postgres

# ===== Choose your database =====
USE_SUPABASE = os.getenv("USE_SUPABASE", "false").lower() == "true"

if USE_SUPABASE:
    # PostgreSQL/Supabase Configuration
    DATABASE_URL = os.getenv("SUPABASE_URL")
    
    if not DATABASE_URL:
        # Build from individual environment variables
        host = os.getenv("SUPABASE_HOST")
        user = os.getenv("SUPABASE_USER", "postgres")
        password = os.getenv("SUPABASE_PASSWORD")
        port = os.getenv("SUPABASE_PORT", "5432")
        db = os.getenv("SUPABASE_DB", "postgres")
        
        if not host or not password:
            raise ValueError("Missing Supabase credentials. Set SUPABASE_HOST and SUPABASE_PASSWORD")
        
        DATABASE_URL = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    
    DB_TYPE = "postgresql"
else:
    # SQLite Configuration (Local Development)
    DATA_DIR = Path(__file__).parent.parent / "data"
    PRODUCTION_DB_PATH = DATA_DIR / "database" / "production.db"
    DATABASE_URL = f"sqlite:///{PRODUCTION_DB_PATH}"
    DB_TYPE = "sqlite"

print(f"🗄️  Using {DB_TYPE.upper()} database")
if DB_TYPE == "postgresql":
    print(f"   Host: {DATABASE_URL.split('@')[1].split('/')[0]}")
