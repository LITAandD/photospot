"""한국관광공사 TourAPI(KorService2)에서 공공누리 1·3유형 사진만 가져와 등록.

- 3유형은 '변경 금지'라 앱에 보여줄 때 자르거나 보정하지 말고 원본 비율 그대로 표시해야 한다.
  (내부 색 분석용 축소는 저장·배포하지 않으므로 별개)
- 요청 파라미터는 활용매뉴얼 최신판으로 한 번 더 확인할 것.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.parse
import urllib.request

BASE_URL = "https://apis.data.go.kr/B551011/KorService2"
LICENSE_MAP = {"Type1": "kogl_type1", "Type3": "kogl_type3"}     # 2·4유형(상업 이용 금지)과 미표기는 제외


def _get(url: str, timeout: int = 20) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def _http_json_default(url: str) -> dict:
    return json.loads(_get(url))


def fetch_detail_images(service_key: str, content_id: str, app_name: str = "PhotoSpot", http_get=_get) -> list[dict]:
    params = {"serviceKey": service_key, "MobileOS": "ETC", "MobileApp": app_name,
              "_type": "json", "contentId": content_id, "numOfRows": 50, "pageNo": 1}
    raw = json.loads(http_get(f"{BASE_URL}/detailImage2?{urllib.parse.urlencode(params)}"))
    return usable_images(raw, content_id)


def usable_images(raw: dict, content_id: str) -> list[dict]:
    items = ((raw.get("response") or {}).get("body") or {}).get("items") or {}
    items = items.get("item", []) if isinstance(items, dict) else []
    if isinstance(items, dict):
        items = [items]
    out = []
    for it in items:
        lic = LICENSE_MAP.get((it.get("cpyrhtDivCd") or "").strip())
        url = (it.get("originimgurl") or "").strip()
        if lic and url:
            out.append({"url": url, "license": lic, "name": it.get("imgname"),
                        "source_ref": f"{content_id}:{it.get('serialnum')}"})
    return out


class LocalStorage:
    def __init__(self, root: str):
        self.root = root

    def save(self, rel_path: str, data: bytes) -> str:
        full = self.open_path(rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)
        return rel_path

    def open_path(self, rel_path: str) -> str:
        root = Path(self.root).resolve()
        full = (root / rel_path).resolve()
        if not full.is_relative_to(root) or full == root:
            raise ValueError("Storage path must stay within the storage root")
        return str(full)

    def delete(self, rel_path: str) -> None:
        try:
            os.remove(self.open_path(rel_path))
        except FileNotFoundError:
            pass


def register_images(conn, spot_id: str, images: list[dict], storage: LocalStorage, http_get=_get) -> int:
    added = 0
    with conn.cursor() as cur:
        for img in images:
            cur.execute("SELECT 1 FROM photos WHERE source='tourapi' AND source_ref=%s", (img["source_ref"],))
            if cur.fetchone():
                continue
            path = storage.save(f"tourapi/{img['source_ref'].replace(':', '_')}.jpg", http_get(img["url"]))
            cur.execute("""INSERT INTO photos (spot_id, source, source_ref, license, storage_path)
                           VALUES (%s, 'tourapi', %s, %s, %s)""",
                        (spot_id, img["source_ref"], img["license"], path))
            added += 1
    conn.commit()
    return added
