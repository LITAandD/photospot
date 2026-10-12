"""Shared test configuration: per-IP rate limits are tested explicitly, not by accident."""
import os

os.environ.setdefault("RATE_LIMIT_AUTH_PER_MIN", "0")
os.environ.setdefault("RATE_LIMIT_PREVIEW_PER_MIN", "0")
