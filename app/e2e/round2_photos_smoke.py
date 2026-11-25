"""Exercise the round-two copy with two local PhotoSpot web servers (baseline on 8796, staged on 8797)."""

import json
from pathlib import Path
from time import perf_counter
from playwright.sync_api import (
    expect,
    sync_playwright,
    TimeoutError as PlaywrightTimeout,
)

ROOT = Path(__file__).resolve().parents[2]


def serve():
    """Run one local copy with the deployed SPA routes and security headers."""
    import argparse
    import os
    import sys
    import uvicorn
    from tempfile import TemporaryDirectory
    import shutil

    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", type=int, choices=(8796, 8797), required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--dist", type=Path, default=ROOT / "app/dist")
    args = parser.parse_args()
    dist = args.dist.resolve(strict=True)
    with TemporaryDirectory(prefix="photospot-review-") as temp:
        db = Path(temp) / "places.sqlite3"
        shutil.copyfile(args.catalog, db)
        os.environ["PLACE_CATALOG_DB"] = str(db)
        os.environ.pop("PHOTO_LIKES_DATABASE_URL", None)
        os.environ.pop("DATABASE_URL", None)
        sys.path.insert(0, str(ROOT))
        from api.preview import app
        from deploy.vercel.frontend import register_seo_routes, register_spa_routes

        register_spa_routes(app, dist / "index.html")
        register_seo_routes(app)
        app.frontend("/", directory=dist, fallback="404.html", check_dir=True)
        rules = json.loads((ROOT / "vercel.json").read_text("utf8"))["headers"]
        headers = next(
            rule["headers"]
            for rule in rules
            if any(h["key"] == "Content-Security-Policy" for h in rule["headers"])
        )
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=args.serve,
            access_log=False,
            headers=[(h["key"], h["value"]) for h in headers],
        )


def check():
    OUT = ROOT / "artifacts/round2-ui"
    OUT.mkdir(parents=True, exist_ok=True)
    photos = json.loads((ROOT / "deploy/photo-round2/approved.json").read_text("utf8"))
    checks, pages = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        for width, height in [(390, 844), (1365, 900)]:
            for port in (8796, 8797):
                base = f"http://127.0.0.1:{port}"
                ctx = browser.new_context(
                    viewport={"width": width, "height": height},
                    locale="ko-KR",
                    has_touch=width == 390,
                )
                page = ctx.new_page()
                events = []
                page.on(
                    "request",
                    lambda req: (
                        events.append(req.url) if "/preview/events" in req.url else None
                    ),
                )
                for city in ("seoul", "busan", "gangneung", "jeju"):
                    page.goto(
                        f"{base}/browse?city={city}&date=2026-11-16&traffic=test",
                        wait_until="domcontentloaded",
                    )
                    cards = page.get_by_test_id("place-card").locator("visible=true")
                    expect(cards).to_have_count(12, timeout=30000)
                    count = 0
                    for card in cards.all():
                        card.scroll_into_view_if_needed()
                        if card.get_by_test_id("place-photo-image").count():
                            try:
                                page.wait_for_function(
                                    "c=>{let i=c.querySelector('img');return i?.complete&&i.naturalWidth>0}",
                                    arg=card.element_handle(),
                                    timeout=12000,
                                )
                                count += 1
                            except PlaywrightTimeout:
                                pass
                    pages.append(
                        dict(
                            width=width,
                            city=city,
                            catalog="base" if port == 8796 else "staged",
                            decoded=count,
                            cards=12,
                        )
                    )
                if port == 8797:
                    page.goto(base + "/login?traffic=test")
                    page.get_by_role("checkbox", name="모두 동의", exact=True).click()
                    page.get_by_role("button", name="추천 시작하기", exact=True).click()
                    page.get_by_role("button", name="다음", exact=True).first.wait_for()
                    for photo in photos:
                        start = perf_counter()
                        pid = photo["place"]["id"]
                        page.goto(
                            f"{base}/place/{pid}?date=2026-11-16&traffic=test",
                            wait_until="domcontentloaded",
                        )
                        u = photo["app_url"]
                        px = page.wait_for_function(
                            """u=>Array.from(document.querySelectorAll('[data-testid=pose-place-photo] img,img[data-testid=pose-place-photo]')).find(i=>i.getAttribute('src')===u&&i.complete&&i.naturalWidth)?.naturalWidth""",
                            arg=u,
                            timeout=22000,
                        ).json_value()
                        assert px == photo["app_size"][0]
                        credit = (
                            page.get_by_test_id("photo-credit")
                            .filter(has_text=photo["credit"])
                            .first
                        )
                        expect(credit).to_contain_text(photo["license"])
                        page.evaluate(
                            "window.open = url => {window.lastPhotoLink = url; return null}"
                        )
                        for label, field in [
                            ("사진 출처", "source"),
                            ("사진 이용 조건", "license_url"),
                            ("원본 사진", "original"),
                        ]:
                            credit.get_by_role("link", name=label, exact=True).click()
                            assert page.evaluate("window.lastPhotoLink") == photo[field]
                        if photo["file_id"] == "METADATA012264":
                            credit.scroll_into_view_if_needed()
                            page.screenshot(path=OUT / f"jagalchi-{width}.png")
                        checks.append(
                            dict(
                                width=width,
                                place_id=pid,
                                decoded_px=px,
                                credit_links=3,
                                seconds=round(perf_counter() - start, 2),
                            )
                        )
                assert not events
                ctx.close()
        browser.close()
    expected = {"base": [12, 8, 6, 4], "staged": [12, 10, 8, 5]}
    for width in (390, 1365):
        for catalog, counts in expected.items():
            assert [
                r["decoded"]
                for r in pages
                if r["width"] == width and r["catalog"] == catalog
            ] == counts
    (OUT / "results.json").write_text(
        json.dumps(dict(pages=pages, details=checks), ensure_ascii=False, indent=2)
        + "\n",
        "utf8",
    )
    print(pages)
    print(f"{len(checks)} image and credit checks passed")


if __name__ == "__main__":
    import sys

    if "--serve" in sys.argv:
        serve()
    else:
        check()
