import os
from pathlib import Path
from dotenv import load_dotenv

# Load env variables from .env file
load_dotenv()

# ===== Environment Variables (create a .env file) =====
# SUPABASE_URL=postgresql://postgres:PASSWORD@project.pooler.supabase.com:6543/postgres
# Or set individual variables:
# SUPABASE_HOST=project.pooler.supabase.com
# SUPABASE_USER=postgres
# SUPABASE_PASSWORD=your-password
# SUPABASE_PORT=6543
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
    DATA_DIR = Path(__file__).parent / "data"
    PRODUCTION_DB_PATH = DATA_DIR / "database" / "production.db"
    DATABASE_URL = f"sqlite:///{PRODUCTION_DB_PATH}"
    DB_TYPE = "sqlite"

import logging
_logger = logging.getLogger("db_config")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    import sys
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"))
    _logger.addHandler(_h)

_logger.info("Using %s database", DB_TYPE.upper())
if DB_TYPE == "postgresql":
    try:
        _logger.info("   Host: %s", DATABASE_URL.split('@')[1].split('/')[0])
    except Exception:
        pass
