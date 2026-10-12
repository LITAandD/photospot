"""한국관광공사 TourAPI(KorService2)에서 공공누리 1·3유형 사진만 가져와 등록.

- 3유형은 '변경 금지'라 앱에 보여줄 때 자르거나 보정하지 말고 원본 비율 그대로 표시해야 한다.
  (내부 색 분석용 축소는 저장·배포하지 않으므로 별개)
- 요청 파라미터는 활용매뉴얼 최신판으로 한 번 더 확인할 것.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE_URL = "https://apis.data.go.kr/B551011/KorService2"
LICENSE_MAP = {"Type1": "kogl_type1", "Type3": "kogl_type3"}     # 2·4유형(상업 이용 금지)과 미표기는 제외

# resultCode (앞 0 제거 후 비교). 0000 정상, 03 NODATA_ERROR는 빈 결과로 본다.
# 일시 오류(재시도): 01 APPLICATION_ERROR, 02 DB_ERROR, 04 HTTP_ERROR, 05 SERVICETIMEOUT_ERROR, 99 UNKNOWN_ERROR
# 그 밖(10 파라미터 오류, 12 서비스 없음, 20 접근 거부, 22 일일 한도 초과, 30 미등록 키, 31 기한 만료, 32 미등록 IP)은 즉시 실패
_OK, _NODATA = "0", "3"
TRANSIENT_CODES = {"1", "2", "4", "5", "99"}


class TourApiError(RuntimeError):
    """TourAPI 오류 응답. 빈 페이지와 구분해 수집이 조용히 멈추지 않게 한다."""

    def __init__(self, code: str | None, msg: str, op: str = ""):
        self.code, self.msg, self.op = code, msg, op
        self.transient = _norm(code) in TRANSIENT_CODES
        super().__init__(f"TourAPI {op or '호출'} 실패 (resultCode={code}): {msg}")


def _norm(code) -> str:
    return (str(code).strip().lstrip("0") or "0") if code is not None else ""


def _get(url: str, timeout: int = 20) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def decode_response(raw, op: str = "") -> dict:
    """bytes/str/dict 응답 → JSON dict. XML 오류 봉투(OpenAPI_ServiceResponse)나 resultCode 오류면 TourApiError."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("<"):
            _raise_xml(text, op)
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            raise TourApiError(None, f"JSON 아님: {text[:120]!r}", op) from None
    if not isinstance(raw, dict):
        raise TourApiError(None, f"예상 밖 응답 형식: {type(raw).__name__}", op)
    resp = raw.get("response")
    header = (resp or {}).get("header") if isinstance(resp, dict) else None
    # 게이트웨이 오류는 최상위 {resultCode, resultMsg}로 오기도 한다
    src = header if isinstance(header, dict) else raw
    code = src.get("resultCode")
    if code is None and not isinstance(resp, dict):
        raise TourApiError(None, f"response 없음: {json.dumps(raw, ensure_ascii=False)[:120]}", op)
    if code is not None and _norm(code) not in (_OK, _NODATA):
        raise TourApiError(str(code), str(src.get("resultMsg") or ""), op)
    return raw


def _raise_xml(text: str, op: str):
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise TourApiError(None, f"XML 해석 실패: {text[:120]!r}", op) from None
    def f(tag):
        el = root.find(f".//{tag}")
        return el.text.strip() if el is not None and el.text else None
    code = f("returnReasonCode") or f("resultCode")
    msg = " / ".join(x for x in (f("returnAuthMsg"), f("errMsg"), f("resultMsg")) if x) or "XML 응답"
    raise TourApiError(code, msg, op)


def items_of(raw: dict) -> list[dict]:
    """response.body.items.item → 항목 목록 (단건 dict·빈 문자열도 처리)."""
    items = ((raw.get("response") or {}).get("body") or {}).get("items") or {}
    items = items.get("item", []) if isinstance(items, dict) else []
    return [items] if isinstance(items, dict) else list(items)


def build_url(op: str, service_key: str, app_name: str = "PhotoSpot", **params) -> str:
    base = {"serviceKey": service_key, "MobileOS": "ETC", "MobileApp": app_name, "_type": "json"}
    return f"{BASE_URL}/{op}?{urllib.parse.urlencode({**base, **{k: v for k, v in params.items() if v is not None}})}"


def _transient_http(e: Exception) -> bool:
    if isinstance(e, urllib.error.HTTPError):
        return e.code == 429 or e.code >= 500
    return isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError))


def request(op: str, service_key: str, *, http_get=_get, app_name: str = "PhotoSpot", retries: int = 3,
            backoff: float = 1.0, sleep=time.sleep, **params) -> dict:
    """공통 호출: URL 조립 → 받기 → 오류 확인. 일시 오류는 1·2·4초… 간격으로 재시도한다."""
    url = build_url(op, service_key, app_name, **params)
    for attempt in range(retries + 1):
        try:
            return decode_response(http_get(url), op)
        except TourApiError as e:
            if not e.transient or attempt == retries:
                raise
        except Exception as e:
            if not _transient_http(e) or attempt == retries:
                raise
        sleep(backoff * 2 ** attempt)
    raise AssertionError("unreachable")


def _http_json_default(url: str) -> dict:
    return decode_response(_get(url))


def fetch_detail_images(service_key: str, content_id: str, app_name: str = "PhotoSpot", http_get=_get) -> list[dict]:
    raw = request("detailImage2", service_key, http_get=http_get, app_name=app_name,
                  contentId=content_id, numOfRows=50, pageNo=1)
    return usable_images(raw, content_id)


def usable_images(raw: dict, content_id: str) -> list[dict]:
    out = []
    for it in items_of(raw):
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
