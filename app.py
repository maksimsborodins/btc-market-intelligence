"""
Streamlit Cloud entrypoint forwarder.
Ensures seamless deployment whether the Cloud wizard targets app.py, streamlit_app.py or dashboard.py.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import dashboard

if __name__ == "__main__":
    dashboard.main()
