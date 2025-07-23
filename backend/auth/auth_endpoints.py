from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2AuthorizationCodeBearer
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.requests import Request
from starlette.responses import RedirectResponse
from dotenv import load_dotenv
import os
from backend.auth.auth_db import get_db_cursor  # Corrected import path
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pathlib import Path

# Create a router for modularity
router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

load_dotenv()

# OAuth2 configuration
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

# OAuth2 scheme
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl='https://accounts.google.com/o/oauth2/auth',
    tokenUrl='https://oauth2.googleapis.com/token',
    refreshUrl='https://oauth2.googleapis.com/token',
    scheme_name='google_oauth',
    auto_error=True
)

# Dependency to get current user
async def get_current_user(request: Request):
    user_info = request.session.get('user')
    if not user_info:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, name, email, user_role, access_token, refresh_token, created_at FROM users WHERE email = %s", (user_info['email'],))
        user = cursor.fetchone()
        if not user:
            cursor.execute(
                "INSERT INTO users (name, email, user_role, access_token, refresh_token, created_at) VALUES (%s, %s, %s, %s, %s, NOW()) RETURNING id, name, email, user_role, access_token, refresh_token, created_at",
                (user_info.get('name', 'Unknown'), user_info['email'], user_info.get('user_role', 'client'), user_info.get('access_token', ''), user_info.get('refresh_token', ''))
            )
            user = cursor.fetchone()
        return {
            "id": user[0], "name": user[1], "email": user[2], "role": user[3],
            "access_token": user[4], "refresh_token": user[5], "created_at": user[6]
        }

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user_info = request.session.get("user")
    return templates.TemplateResponse("home.html", {"request": request, "user": user_info})

@router.get("/signup", response_class=HTMLResponse)
async def signup(request: Request):
    user_info = request.session.get("user")
    return templates.TemplateResponse("signup.html", {"request": request, "user": user_info})

@router.get("/signin", response_class=HTMLResponse)
async def signin(request: Request):
    user_info = request.session.get("user")
    return templates.TemplateResponse("signin.html", {"request": request, "user": user_info})

@router.get("/auth/login")
async def login(request: Request):
    redirect_uri = 'http://127.0.0.1:8000/auth/callback'
    response = await oauth.google.authorize_redirect(request, redirect_uri)
    print(f"Session after login: {request.session}")
    return response

@router.get("/auth/callback")
async def auth_callback(request: Request):
    print(f"Session before callback: {request.session}")
    try:
        token = await oauth.google.authorize_access_token(request)
        print(f"Token: {token}")
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
                        "INSERT INTO users (name, email, user_role, access_token, refresh_token, created_at) VALUES (%s, %s, %s, %s, %s, NOW()) RETURNING id",
                        (user_info.get('name', 'Unknown'), user_info['email'], 'client', token['access_token'], token.get('refresh_token'))
                    )
                else:
                    cursor.execute(
                        "UPDATE users SET access_token = %s, refresh_token = %s WHERE email = %s",
                        (token['access_token'], token.get('refresh_token'), user_info['email'])
                    )
        return RedirectResponse(url='/')
    except Exception as e:
        print(f"Callback error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

@router.get("/logout")
async def logout(request: Request):
    request.session.pop('user', None)
    return RedirectResponse(url='/')

@router.get("/protected", response_class=HTMLResponse)
async def protected_route(request: Request, current_user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("protected.html", {"request": request, "user": current_user})

@router.get("/debug-session")
async def debug_session(request: Request):
    return {"session": request.session}

@router.get("/favicon.ico")
async def favicon():
    return {"message": "No favicon"}