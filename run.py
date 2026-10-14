"""Dev entry point: `python run.py`.

Serves on http://127.0.0.1:5001 (the Luna & Lotus portals use 5000).
Local build only — never deploy without the founder's explicit word.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5001")),
            debug=app.config["DEBUG"])
