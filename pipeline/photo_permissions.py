"""Operations allowed on photos already present in the SQLite catalog."""

import re

TYPE1 = "https://www.kogl.or.kr/info/licenseType1.do"
TYPE3 = "https://www.kogl.or.kr/info/licenseType3.do"
CC = re.compile(
    # Accept only supported, published versions; a syntactically plausible URL
    # (for example /9.9/) is not evidence of a license grant.
    r"https://creativecommons\.org/licenses/(by|by-sa|by-nd)/(?:1\.0|2\.0|2\.5|3\.0|4\.0)(?:/[a-z]{2})?(?:/deed\.[a-z-]+)?/?",
    re.I,
)
PUBLIC_DOMAIN = re.compile(
    r"https://creativecommons\.org/publicdomain/(?:zero|mark)/1\.0(?:/deed\.[a-z-]+)?/?"
)
GFDL = re.compile(
    r"https://www\.gnu\.org/licenses/(?:old-licenses/)?fdl(?:-1\.[123])?(?:\.html)?/?"
)


def allowed(photo, *, modify=False):
    url = (photo.get("license_url") or "").strip()
    label = (photo.get("license") or "").casefold()
    if "by-nc" in label or "비영리" in label:
        return False
    cc = CC.fullmatch(url)
    if modify and (
        url == TYPE3
        or (cc and cc[1].casefold() == "by-nd")
        or re.search(r"by-nd|변경\s*금지|제?\s*3\s*유형|type\s*3|kogl_type3", label)
    ):
        return False
    return bool(
        cc
        or PUBLIC_DOMAIN.fullmatch(url)
        or GFDL.fullmatch(url)
        or url in {TYPE1, TYPE3}
    )
