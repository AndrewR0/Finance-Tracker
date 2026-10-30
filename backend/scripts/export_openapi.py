"""Write FastAPI's OpenAPI schema to a JSON file. The frontend generates its API types from it.

Usage (from frontend\\): npm run gen:api
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so "app" can be imported from anywhere

from app.main import app  # noqa: E402

Path(sys.argv[1]).write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
