"""KorService2 v4.4 classification and legal district filters.

Legacy area numbers remain the input to the two existing PostGIS CLIs.
Only legal district codes are sent over HTTP.
"""

CLI_REGIONS = dict(
    zip(
        (1, 2, 3, 4, 5, 6, 7, 8, 31, 32, 33, 34, 35, 36, 37, 38, 39),
        (11, 28, 30, 27, 29, 26, 31, 36, 41, 51, 43, 44, 47, 48, 52, 46, 50),
        strict=True,
    )
)
CAFE = {"lclsSystm1": "FD", "lclsSystm2": "FD05", "lclsSystm3": "FD050100"}


def filters(*, region=None, district=None, cafe=False):
    if district and not region:
        raise ValueError("A legal district requires its parent region")
    params = CAFE.copy() if cafe else {}
    if region:
        params["lDongRegnCd"] = str(region)
    if district:
        params["lDongSignguCd"] = str(district)
    return params


def matches_filters(row, params):
    return all(str(row.get(key) or "") == str(value) for key, value in params.items())
