import json
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from string import Template
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from .config import SETTINGS_PATH


SCOPES = ['https://www.googleapis.com/auth/drive.file']
CLIENT_SECRETS_FILE = SETTINGS_PATH / 'client_secret_17520064084-tgmob015qji3cn1stsv2ener7grq27ck.apps.googleusercontent.com.json'
token_file_path = SETTINGS_PATH / 'token1.json'
redirect_uri = 'https://friendly-space-halibut-rvgjgr4p6j354vr-8000.app.github.dev/oauth2callback'

google_picker_html_path  = Path(__file__).parent.joinpath('google_file_pikle.html')

app = FastAPI()



@app.get("/")
def index():
    return HTMLResponse('<a href="/auth">Авторизоваться</a>')


@app.get("/auth")
def auth():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    return RedirectResponse(authorization_url)


@app.route("/oauth2callback")
def oauth2callback(request:Request):

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

    flow.fetch_token(authorization_response=str(request.url))

    credentials = flow.credentials

    token_file_path.write_text(credentials.to_json())

    return RedirectResponse("/select-file")

@app.get("/files")
def get_files():
    creds = Credentials.from_authorized_user_file(token_file_path, SCOPES)

    # Создаём Google Drive API клиент
    service = build('drive', 'v3', credentials=creds)

    # Пример: получить список файлов, к которым есть доступ (будут только те, что вы разрешили)
    results = service.files().list(pageSize=50, fields="files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        print('Нет доступных файлов.')
    else:
        print('Файлы:')
        for item in items:
            print(f"{item['name']} ({item['id']})")


@app.get("/select-file")
def picker():
    if not token_file_path.exists():
        return RedirectResponse("/auth")
    creds_data = json.loads(token_file_path.read_text())
    template = Template(google_picker_html_path.read_text())
    res = template.substitute(
        app_id='17520064084',
        app_key=app_key,
        accessToken=creds_data["token"], 
        )
    return HTMLResponse(res)

@app.post("/select-file")
def picker(data: dict):
    fileId = data.get("fileId")
    print(f"Выбран файл с ID: {fileId}")
    main()
    return 'ok'

def main():
    creds = Credentials.from_authorized_user_file(token_file_path, SCOPES)

    # Создаём Google Drive API клиент
    service = build('drive', 'v3', credentials=creds)

    # Пример: получить список файлов, к которым есть доступ (будут только те, что вы разрешили)
    results = service.files().list(pageSize=50, fields="files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        print('Нет доступных файлов.')
    else:
        print('Файлы:')
        for item in items:
            print(f"{item['name']} ({item['id']})")


if __name__ == '__main__':
    main()