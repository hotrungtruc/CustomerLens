"""
DEPRECATED: Streamlit app has been relocated from `app/utils/` to `backend/scripts/streamlit_app.py`.
This module is maintained solely for backward compatibility.
"""

import sys
import warnings
from pathlib import Path

warnings.warn(
    "backend.app.utils.streamlit_app is deprecated. "
    "Please run 'streamlit run backend/scripts/streamlit_app.py' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from scripts.streamlit_app if available
try:
    from scripts.streamlit_app import *  # noqa: F401, F403
except ImportError:
    pass
