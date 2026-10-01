"""
Backward-compatible facade for the database layer.

All public names previously exported from this module are still available here.
New code should import directly from the sub-modules:
  - app.db.pool              → get_db_connection
  - app.db.schema            → ensure_schema
  - app.db.repositories.cameras   → camera / user / credential helpers
  - app.db.repositories.customers → customer CRUD
  - app.db.repositories.logs      → recognize_logs / reports
"""

# Connection & pool
from app.db.pool import (  # noqa: F401
    get_db_connection,
    PostgresConnectionWrapper,
    PostgresCursorWrapper,
)

# Schema management
from app.db.schema import (  # noqa: F401
    ensure_schema,
    DEFAULT_TIME,
    DEFAULT_MODEL,
)

# Camera / credential / user repositories
from app.db.repositories.cameras import (  # noqa: F401
    find_active_device_credential,
    create_camera_and_credential,
    create_device_credential,
    revoke_camera_credentials,
    retire_replaced_camera,
    touch_device_credential,
    list_active_cameras,
    update_camera_display_name,
    delete_camera,
    camera_exists,
    record_camera_connection,
    close_camera_connection,
    list_users_with_permissions,
    list_cameras_allowed_for_user,
    user_can_view_camera,
    replace_user_camera_permissions,
)

# Customer repository
from app.db.repositories.customers import (  # noqa: F401
    get_customer_info,
    create_or_update_customer_profile,
    upsert_customer,
    insert_guest_record,
    update_attendance,
)

# Logs & analytics repository
from app.db.repositories.logs import (  # noqa: F401
    bulk_insert_recognize_logs,
    get_recognize_logs,
    get_reports_data,
)
