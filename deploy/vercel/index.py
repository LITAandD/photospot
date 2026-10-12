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
from deploy.vercel.frontend import register_spa_routes  # noqa: E402

# Vercel promotes static assets to its CDN. Explicit application routes must
# precede the frontend's generated 404 fallback; vercel.json rewrites alone
# cannot override that fallback. The build saves a small entry copy in the
# function bundle, while image/font/JS files stay on the CDN.
register_spa_routes(app, Path(__file__).with_name('web-entry.html'))
# API-only runs (tests, CI's Python job) have no exported bundle, and StaticFiles
# raises on every unmatched request when its directory is missing.
_frontend = ROOT / "app" / "dist"
if _frontend.is_dir():
    app.frontend("/", directory=_frontend,
                 fallback="404.html" if (_frontend / '404.html').is_file() else None, check_dir=False)
