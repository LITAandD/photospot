"""Serve the browser-only demo and stateless calculations on one Vercel domain."""
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]
# The shared catalog readers initialize indexes. Vercel's application bundle is
# read-only, so each Python process uses its own writable copy of public facts.
# User profiles, birth inputs and sessions are never written to this database.
_catalog_directory = TemporaryDirectory(prefix="photospot-preview-")
_catalog_path = Path(_catalog_directory.name) / "places.sqlite3"
shutil.copyfile(ROOT / "catalog" / "places.sqlite3", _catalog_path)
os.environ["PLACE_CATALOG_DB"] = str(_catalog_path)

from api.preview import app  # noqa: E402

# Vercel promotes these files to its CDN. Unmatched browser routes return the
# SPA entry point, while /preview/* and /health retain their FastAPI handlers.
# API-only runs (tests, CI's Python job) have no exported bundle, and StaticFiles
# raises on every unmatched request when its directory is missing.
_frontend = ROOT / "app" / "dist"
if _frontend.is_dir():
    app.frontend("/", directory=_frontend,
                 fallback="404.html" if (_frontend / '404.html').is_file() else None, check_dir=False)
