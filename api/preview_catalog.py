"""Read the checked-in seed rules for the local, explicitly labelled preview only.

Production continues to use PostGIS and reviewed photo evidence. Never import
this module from the production app or mark these sample tags as verified data.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def tuples(sql: str, table: str) -> list[list]:
    section = sql.split(f"INSERT INTO {table} ", 1)[1].split("VALUES", 1)[1].split(";", 1)[0]
    section = re.sub(r"--[^\n]*", "", section)
    rows = []
    for row in re.findall(r"\(((?:'[^']*'|[^'()])*)\)", section):
        tokens = re.findall(r"'[^']*'|NULL|-?\d+(?:\.\d+)?", row)
        rows.append([t[1:-1] if t.startswith("'") else None if t == "NULL" else float(t) for t in tokens])
    return rows


SCHEMA = (ROOT / "schema.sql").read_text(encoding="utf-8")
SEED = (ROOT / "seed_example.sql").read_text(encoding="utf-8")
RULES = [dict(zip(["dimension", "user_value", "attribute", "attr_value", "score"], row))
         for row in tuples(SCHEMA, "match_rules")]
WEIGHTS = [dict(zip(["version", "dimension", "attribute", "layer", "weight"], row))
           for row in tuples(SCHEMA, "score_weights")]
PLACES = {}
for pid, name, category, lng, lat in re.findall(
        r"\('([\w-]+)',\s*'([^']+)',\s*'([^']+)',\s*'[^']+',\s*'[^']+',\s*ST_MakePoint\(([\d.]+),\s*([\d.]+)\)", SEED):
    PLACES[pid] = {"id": pid, "name": name, "category": category, "lng": float(lng), "lat": float(lat)}
SPOTS = {r[0]: {"id": r[0], "place_id": r[1], "name": r[2]} for r in tuples(SEED, "spots")}
SCENES = [dict(zip(["id", "spot_id", "time_slot", "season", "color_temp", "brightness", "saturation", "lighting",
                   "form", "texture", "scale", "crowd_level", "place_character", "photo_mood", "tag_source", "confidence"], r))
          for r in tuples(SEED, "scenes")]
for scene in SCENES:
    scene["elements"] = [r[1] for r in tuples(SEED, "scene_elements") if r[0] == scene["id"]]
    scene["spot_name"] = SPOTS[scene["spot_id"]]["name"]
    scene["place_id"] = SPOTS[scene["spot_id"]]["place_id"]
OPERATING_RULES = [dict(zip(["place_id", "rule_type", "weekday", "start_md", "end_md", "note"], r))
                   for r in tuples(SEED, "operating_rules")]
assert len(PLACES) == len(SCENES) == 8 and len(RULES) > 60 and len(WEIGHTS) == 11
