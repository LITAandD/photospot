"""TourAPI 공통 호출(오류 코드·재시도)과 쉬는 날 해석 테스트. 네트워크 없이 가짜 HTTP만 쓴다."""
import json
import os
import sys
import urllib.error
import urllib.parse

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline.import_tourapi import TourApi, parse_rest_days      # noqa: E402
from pipeline.tourapi import TourApiError, decode_response, fetch_detail_images, items_of, request   # noqa: E402
from pipeline.tourapi_bulk import Stats, import_items, iter_area   # noqa: E402


@pytest.mark.parametrize("text,days", [
    ("매주 월요일", [1]),
    ("월요일", [1]),
    ("매주 월,화요일", [1, 2]),
    ("월요일 휴관", [1]),
    ("매주 월요일 휴관일", [1]),
    ("월요일, 화요일 휴무", [1, 2]),
    ("월·화요일 휴무", [1, 2]),
    ("일요일", [0]),
    ("매주 일요일 휴무", [0]),
    ("토·일요일", [0, 6]),
    ("토,일", [0, 6]),
    ("휴무(월)", [1]),
    ("<br>매주 화요일<br>", [2]),
    ("연중무휴", []),
    ("없음", []),
    (None, []),
])
def test_parse_rest_days(text, days):
    got, note = parse_rest_days(text)
    assert got == days and note is None


@pytest.mark.parametrize("text", ["매월 둘째 월요일", "월요일(공휴일인 경우 다음날)", "설·추석 당일", "매일 개방"])
def test_parse_rest_days_needs_review(text):
    got, note = parse_rest_days(text)
    assert got == [] and note and note.startswith("쉬는 날 확인 필요")


# --- 응답 해석 ---------------------------------------------------------------
OK = {"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                   "body": {"items": {"item": {"contentid": "1"}}, "totalCount": 1}}}
QUOTA_XML = (b"<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
             b"<returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg>"
             b"<returnReasonCode>22</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")


def test_decode_ok_and_single_item():
    raw = decode_response(json.dumps(OK).encode())
    assert items_of(raw) == [{"contentid": "1"}]
    assert items_of({"response": {"body": {"items": ""}}}) == []
    nodata = {"response": {"header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"}, "body": {"items": ""}}}
    assert items_of(decode_response(nodata)) == []


def test_decode_xml_quota_error():
    with pytest.raises(TourApiError) as ei:
        decode_response(QUOTA_XML, "areaBasedList2")
    assert ei.value.code == "22" and not ei.value.transient and "LIMITED_NUMBER" in str(ei.value)


@pytest.mark.parametrize("raw,code", [
    ({"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}}, "30"),
    ({"resultCode": "10", "resultMsg": "INVALID_REQUEST_PARAMETER_ERROR"}, "10"),
    (b"<response><header><resultCode>11</resultCode><resultMsg>NO_MANDATORY</resultMsg></header></response>", "11"),
])
def test_decode_error_codes(raw, code):
    with pytest.raises(TourApiError) as ei:
        decode_response(raw)
    assert ei.value.code == code


def test_decode_garbage_is_clear():
    with pytest.raises(TourApiError, match="JSON 아님"):
        decode_response(b"Unexpected errors")


# --- 재시도 -------------------------------------------------------------------
class Flaky:
    def __init__(self, *responses):
        self.responses, self.urls = list(responses), []

    def __call__(self, url):
        self.urls.append(url)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_request_retries_transient_then_succeeds():
    sleeps = []
    http = Flaky(urllib.error.URLError("timeout"),
                 {"response": {"header": {"resultCode": "05", "resultMsg": "SERVICETIMEOUT_ERROR"}}},
                 json.dumps(OK).encode())
    raw = request("detailImage2", "KEY", http_get=http, sleep=sleeps.append, contentId="1", pageNo=1)
    assert items_of(raw) and sleeps == [1.0, 2.0]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(http.urls[0]).query)
    assert q["serviceKey"] == ["KEY"] and q["_type"] == ["json"] and q["MobileOS"] == ["ETC"] and q["contentId"] == ["1"]


def test_request_gives_up_after_retries():
    sleeps = []
    http = Flaky(*[urllib.error.HTTPError("u", 503, "x", None, None)] * 3)
    with pytest.raises(urllib.error.HTTPError):
        request("areaBasedList2", "K", http_get=http, retries=2, sleep=sleeps.append)
    assert len(http.urls) == 3 and sleeps == [1.0, 2.0]


def test_request_does_not_retry_quota():
    http = Flaky(QUOTA_XML)
    with pytest.raises(TourApiError):
        request("areaBasedList2", "K", http_get=http, sleep=lambda s: pytest.fail("재시도하면 안 됨"))
    assert len(http.urls) == 1


def test_bulk_iter_area_raises_on_quota_instead_of_stopping():
    with pytest.raises(TourApiError, match="resultCode=22"):
        list(iter_area("K", 1, 12, Flaky(QUOTA_XML)))


def test_import_items_stops_on_fatal_error():
    class Conn:
        def rollback(self):
            pass
    def bad_items():
        yield {"contentid": "1"}
        raise TourApiError("30", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR")
    with pytest.raises(TourApiError):
        import_items(Conn(), bad_items(), None, Stats())


def test_tourapi_class_and_detail_images_share_helper():
    api = TourApi("K", http_json=Flaky(OK, QUOTA_XML), pause=0)
    assert api.call("searchKeyword2", keyword="온실") == [{"contentid": "1"}]
    with pytest.raises(TourApiError):
        api.call("searchKeyword2", keyword="온실")
    img = {"response": {"header": {"resultCode": "0000"}, "body": {"items": {"item": [
        {"originimgurl": "http://x/a.jpg", "cpyrhtDivCd": "Type1", "serialnum": "1"}]}}}}
    assert [i["license"] for i in fetch_detail_images("K", "9", http_get=Flaky(json.dumps(img).encode()))] == ["kogl_type1"]
