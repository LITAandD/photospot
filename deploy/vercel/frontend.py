"""Known SPA deep links are real routes; unknown paths retain HTTP 404."""
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

SPA_ROUTES = (
    '/home', '/saju', '/result', '/saved', '/settings', '/support', '/privacy',
    '/login', '/accounts', '/admin', '/feedback', '/feedback/{rec_id}', '/place/{place_id}',
    '/diagnosis/personal-color', '/diagnosis/body-type', '/onboarding/basic',
    '/onboarding/style', '/onboarding/traits', '/oauth/naver',
)


def register_spa_routes(app, entry_file: Path):
    def entry():
        if not entry_file.is_file():
            raise HTTPException(503, '웹 화면을 준비하고 있어요. 잠시 후 다시 확인해 주세요.')
        return FileResponse(entry_file, media_type='text/html')

    for path in SPA_ROUTES:
        app.add_api_route(path, entry, methods=['GET', 'HEAD'], include_in_schema=False)
