import datetime
import json
import uuid
from pathlib import Path
from string import Template

from aiohttp import web
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import GoogleAuthConfig
from database import get_session, save_access_token_for_user, get_access_token_for_user

google_picker_html_path = Path(__file__).parent.joinpath('google_file_pikle.html')

app = web.Application()
google_auth_config = GoogleAuthConfig()  # noqa


async def index(request: web.Request) -> web.Response:
    html = '<a href="/auth">Авторизоваться</a>'
    return web.Response(text=html, content_type="text/html")


async def auth(request: web.Request) -> web.Response:
    flow = google_auth_config.get_flow()
    state = request.query.get('state')

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    resp = web.HTTPFound(authorization_url)
    # Аналог RedirectResponse
    return resp


async def oauth2callback(request: web.Request) -> web.Response:
    flow = google_auth_config.get_flow()

    user_id = uuid.UUID(request.query.get('state'))
    code = request.query.get('code')
    flow.fetch_token(code=code)

    credentials = flow.credentials
    async with  get_session() as session:
        await save_access_token_for_user(session, user_id, credentials)

    resp = web.HTTPFound("/select-file")
    resp.set_cookie(
        "user_id",
        user_id.hex,
        httponly=True,  # важно
        # secure=True,  # ставьте True в проде (https)
        samesite="Lax",  # или Strict/None по ситуации
        max_age=3600,
    )

    raise resp


async def get_files(user_id: str) -> web.Response:

    async with  get_session() as session:
        row = await get_access_token_for_user(session, user_id)


    creds = Credentials.from_authorized_user_info(info={
        'token': row.access_token,
        'refresh_token': row.refresh_token,
        'scopes': google_auth_config.scopes
    })

    service = build('drive', 'v3', credentials=creds)

    results = service.files().list(pageSize=50, fields="files(id, name)").execute()
    items = results.get('files', [])
    for item in items:
        yield item.get('id'), item.get('name')


async def picker_get(request: web.Request) -> web.Response:
    user_id = request.cookies.get('user_id')

    async with  get_session() as session:
        row = await get_access_token_for_user(session, user_id)

    template = Template(google_picker_html_path.read_text())
    res = template.substitute(
        app_id=GoogleAuthConfig().app_id,
        accessToken=row.access_token,
    )
    return web.Response(text=res, content_type="text/html")


async def picker_post(request: web.Request) -> web.Response:
    if request.content_type == "application/json":
        data = await request.json()
    else:
        data = await request.post()

    file_id = data.get("fileId")
    print(f"Выбран файл с ID: {file_id}")

    return web.Response(text="ok", content_type="application/json")



# Регистрация маршрутов — заменяет декораторы @app.get / @app.post
app.router.add_get("/", index)
app.router.add_get("/auth", auth)
app.router.add_get("/oauth2callback", oauth2callback)
app.router.add_get("/files", get_files)
app.router.add_get("/select-file", picker_get)
app.router.add_post("/select-file", picker_post)


def run():
    # Стартуем aiohttp-сервер (на 0.0.0.0:8080)
    web.run_app(app, host="localhost", port=3000)


if __name__ == "__main__":
    run()
