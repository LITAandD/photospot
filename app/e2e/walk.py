import sys
from playwright.sync_api import sync_playwright
step = sys.argv[1] if len(sys.argv) > 1 else "all"
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                        geolocation={"latitude": 37.5796, "longitude": 126.977}, permissions=["geolocation"], locale="ko-KR")
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "favicon" not in m.text else None)
    shot = lambda name: (pg.wait_for_timeout(600), pg.screenshot(path=f"/tmp/shots/{name}.png"), print("📸", name))
    vis = lambda loc: loc.locator("visible=true").last          # 이전 화면이 아직 DOM에 남아 있어도 보이는 것만
    tap = lambda text: vis(pg.get_by_text(text, exact=True)).click()
    fill = lambda label, value: vis(pg.get_by_label(label)).fill(value)
    def go(text, url_part, tries=3):
        """버튼을 누르고 URL이 바뀔 때까지 기다린다. 이미 이동했으면 다시 누르지 않는다"""
        for _ in range(tries):
            if url_part in pg.url:
                return
            tap(text)
            for _ in range(40):
                pg.wait_for_timeout(200)
                if url_part in pg.url:
                    pg.wait_for_timeout(500); return
        raise RuntimeError(f"{text} → {url_part} 이동 실패 (현재 {pg.url})")
    pg.goto("http://localhost:8081", wait_until="domcontentloaded", timeout=120000)
    pg.locator("text=시작하기").last.wait_for(timeout=60000)
    shot("01_welcome")
    tap("시작하기")
    pg.locator("text=체험용 로그인").last.wait_for(timeout=60000); shot("02_login")
    go("체험용 로그인", "onboarding/basic")
    pg.locator("text=기본 정보를 알려주세요").last.wait_for(timeout=60000)
    tap("여성")
    fill("출생연도", "1998")
    fill("키", "162")
    shot("03_basic")
    go("다음", "onboarding/style")
    pg.locator("text=퍼스널컬러와 체형").last.wait_for(timeout=60000)
    tap("여름 쿨")
    tap("라이트")
    tap("웨이브")
    shot("04_style")
    go("다음", "onboarding/traits")
    pg.locator("text=성향을 더해볼까요").last.wait_for(timeout=60000)
    for letter in ["I", "N", "F", "P"]:
        pg.get_by_text(letter, exact=True).click()
    vis(pg.get_by_role("switch")).click()
    fill("생년월일", "1998-05-14")
    fill("태어난 시간 (모르면 비워두세요)", "14:30")
    vis(pg.get_by_role("checkbox")).click()
    shot("05_traits")
    go("추천 받기", "result")
    pg.locator("text=나를 살리는 빛").last.wait_for(timeout=60000); shot("06_result")
    go("추천 장소 보기", "home")
    pg.locator("text=창경궁 대온실").last.wait_for(timeout=60000); shot("07_home")
    go("창경궁 대온실", "place/")
    pg.locator("text=나와 맞는 이유").last.wait_for(timeout=60000); shot("08_place")
    go("다녀왔어요", "feedback/")
    pg.locator("text=사진은 잘 나왔나요?").last.wait_for(timeout=60000)
    vis(pg.get_by_label("5점")).click()
    vis(pg.get_by_text("생각보다 붐볐어요")).click()
    shot("09_feedback")
    go("보내기", "home")
    pg.locator("text=오늘 어디서 찍을까요").last.wait_for(timeout=60000); shot("10_home_after")
    print("done; errors:", errors[:5] if errors else "none")
    b.close()
