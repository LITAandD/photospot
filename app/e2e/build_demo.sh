#!/bin/bash
set -e
cd /home/claude/photospot/app
rm -rf dist-web
EXPO_PUBLIC_DEMO=1 EXPO_PUBLIC_API_BASE_URL=https://demo.invalid EXPO_NO_TELEMETRY=1 npx expo export --platform web --output-dir dist-web > /tmp/export.log 2>&1
python3 - << 'PY'
import re, pathlib
html = pathlib.Path("dist-web/index.html").read_text()
js = pathlib.Path(next(pathlib.Path("dist-web/_expo/static/js/web").glob("*.js"))).read_text()
head_extra = '''
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <link rel="icon" href="data:," />
    <style>
      :root { box-sizing: border-box; padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }
      html { scroll-padding-top: env(safe-area-inset-top, 0px); }
      body { background: #F6F3EE; margin: 0; }
      #root { max-width: 430px; margin: 0 auto; box-shadow: 0 0 0 1px #E3DDD3; }
    </style>
    <script>
      try { if (location.pathname !== "/") history.replaceState(null, "", "/"); } catch (e) {}
    </script>'''
html = html.replace('<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no" />', head_extra).replace('<html lang="en">', '<html lang="ko">')
html = re.sub(r'<script src="[^"]+" defer></script>', lambda m: "<script>\n" + js.replace("</script", "<\\/script") + "\n</script>", html)
pathlib.Path("/mnt/user-data/outputs/photospot_demo.html").write_text(html)
print(round(len(html) / 1e6, 2), "MB")
PY
cp /mnt/user-data/outputs/photospot_demo.html /tmp/serve/deep/path/app.html
