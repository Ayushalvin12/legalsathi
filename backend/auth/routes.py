from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from dotenv import load_dotenv
from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.config import Config
from fastapi.security import OAuth2AuthorizationCodeBearer
import os
from datetime import datetime
from auth.db import get_db_cursor

load_dotenv(dotenv_path="E:/legal_sathi/backend/.env")
print(f"GOOGLE_CLIENT_ID: {os.getenv('GOOGLE_CLIENT_ID')}")
print(f"GOOGLE_CLIENT_SECRET: {os.getenv('GOOGLE_CLIENT_SECRET')}")

router = APIRouter()

print("Initializing auth router")  # Debug

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

config = Config(environ={
    "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID"),
    "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET")
})
oauth = OAuth(config)
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
    redirect_uri='http://127.0.0.1:8000/auth/callback'
)

oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl='https://accounts.google.com/o/oauth2/auth',
    tokenUrl='https://oauth2.googleapis.com/token',
    refreshUrl='https://oauth2.googleapis.com/token',
    scheme_name='google_oauth',
    auto_error=True
)

async def get_current_user(request: Request):
    user_info = request.session.get('user')
    if not user_info:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, username, email, user_role, access_token, refresh_token, created_at FROM users WHERE email = %s", (user_info['email'],))
        user = cursor.fetchone()
        if not user:
            cursor.execute(
                "INSERT INTO users (username, email, user_role, access_token, refresh_token, created_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, username, email, user_role, access_token, refresh_token, created_at",
                (user_info['name'], user_info['email'], user_info.get('user_role', 'client'), user_info.get('access_token'), user_info.get('refresh_token'), datetime.now())
            )
            user = cursor.fetchone()
        return {
            "id": user[0], "username": user[1], "email": user[2], "role": user[3],
            "access_token": user[4], "refresh_token": user[5], "created_at": user[6]
        }

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user_info = request.session.get("user")
    print(f"Root endpoint hit, user_info: {user_info}")  # Debug
    return templates.TemplateResponse("home.html", {"request": request, "user": user_info})

@router.get("/signup", response_class=HTMLResponse)
async def signup(request: Request, redirected: bool = False):
    print("Signup endpoint hit")  # Debug
    return templates.TemplateResponse(
        "signup.html",
        {"request": request, "redirected": redirected}
    )

@router.get("/questions", response_class=HTMLResponse)
async def questions(request: Request):
    user_info = request.session.get("user")
    print(f"Questions endpoint hit, user_info: {user_info}")  # Debug
    return templates.TemplateResponse("questions.html", {"request": request, "user": user_info})

@router.get("/signin", response_class=HTMLResponse)
async def signin(request: Request):
    user_info = request.session.get("user")
    print(f"Signin endpoint hit, user_info: {user_info}")  # Debug
    return templates.TemplateResponse("signin.html", {"request": request, "user": user_info})

@router.get("/chatapp", response_class=HTMLResponse)
async def chatapp(request: Request):
    user_info = request.session.get("user")
    print(f"Chatapp endpoint hit, user_info: {user_info}")  # Debug
    if not user_info:
        return RedirectResponse(url="/signup?redirected=true", status_code=status.HTTP_302_FOUND)
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT id, username, email, user_role, access_token, refresh_token, created_at FROM users WHERE email = %s", (user_info['email'],))
            user = cursor.fetchone()
            if not user:
                cursor.execute(
                    "INSERT INTO users (username, email, user_role, access_token, refresh_token, created_at) VALUES (%s, %s, %s, %s, %s, NOW()) RETURNING id, username, email, user_role, access_token, refresh_token, created_at",
                    (user_info['name'], user_info['email'], 'client', user_info.get('access_token'), user_info.get('refresh_token'))
                )
                user = cursor.fetchone()
            current_user = {
                "id": user[0], "username": user[1], "email": user[2], "role": user[3],
                "access_token": user[4], "refresh_token": user[5], "created_at": user[6]
            }
        return templates.TemplateResponse("chat.html", {"request": request, "user": current_user})
    except Exception as e:
        print(f"Error in chatapp: {str(e)}")
        return RedirectResponse(url="/signup?redirected=true", status_code=status.HTTP_302_FOUND)

@router.get("/auth")
async def login(request: Request):
    redirect_uri = 'http://127.0.0.1:8000/auth/callback'
    print(f"Login endpoint hit, redirecting to Google OAuth, redirect_uri: {redirect_uri}")  # Debug
    try:
        return await oauth.google.authorize_redirect(request, redirect_uri, prompt="select_account")
    except OAuthError as e:
        print(f"OAuth error during login: {str(e)}")  # Debug
        raise HTTPException(status_code=400, detail=f"OAuth error: {str(e)}")

@router.get("/auth/callback")
async def auth_callback(request: Request):
    print(f"Session before callback: {request.session}")  # Debug
    try:
        token = await oauth.google.authorize_access_token(request)
        print(f"Token: {token}")  # Debug
        user_info = token.get('userinfo')
        if user_info:
            user_info['access_token'] = token['access_token']
            user_info['refresh_token'] = token.get('refresh_token')
            request.session['user'] = dict(user_info)
            with get_db_cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE email = %s", (user_info['email'],))
                user = cursor.fetchone()
                if not user:
                    cursor.execute(
                        "INSERT INTO users (username, email, user_role, access_token, refresh_token, created_at) VALUES (%s, %s, %s, %s, %s, NOW()) RETURNING id",
                        (user_info['name'], user_info['email'], 'client', token['access_token'], token.get('refresh_token'))
                    )
                else:
                    cursor.execute(
                        "UPDATE users SET access_token = %s, refresh_token = %s WHERE email = %s",
                        (token['access_token'], token.get('refresh_token'), user_info['email'])
                    )
        print(f"Callback set session: {user_info}")  # Debug
        return RedirectResponse(url='/chatapp')
    except OAuthError as e:
        print(f"OAuth error during callback: {str(e)}")  # Debug
        raise HTTPException(status_code=400, detail=f"OAuth error: {str(e)}")

@router.get("/logout")
async def logout(request: Request):
    print("Logout endpoint hit")  # Debug
    request.session.pop('user', None)
    return RedirectResponse(url='/')

@router.get("/protected", response_class=HTMLResponse)
async def protected_route(request: Request, current_user: dict = Depends(get_current_user)):
    print(f"Protected endpoint hit, user: {current_user}")  # Debug
    return templates.TemplateResponse("protected.html", {"request": request, "user": current_user})

@router.get("/debug-session")
async def debug_session(request: Request):
    print(f"Debug-session endpoint hit, session: {request.session}")  # Debug
    return {"session": request.session}

@router.get("/favicon.ico")
async def favicon():
    print("Favicon endpoint hit")  # Debug
    return {"message": "No favicon"}