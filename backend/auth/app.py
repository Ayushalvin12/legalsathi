from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.security import OAuth2AuthorizationCodeBearer
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import os
from auth.db import get_db_cursor
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pathlib import Path
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


app = FastAPI()
load_dotenv()
# Serve static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR/"static")))

# Session middleware with explicit settings
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY"),
    session_cookie="legalsathi_session",
    max_age=3600,
    same_site="lax",
    domain="127.0.0.1"  
)

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
        cursor.execute("SELECT id, username, email, user_role,  access_token, refresh_token, created_at FROM users WHERE email = %s", (user_info['email'],))
        user = cursor.fetchone()
        if not user:
            cursor.execute(
                "INSERT INTO users (username, email, user_role, access_token, refresh_token created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id, name, email, user_role,  access_token, refresh_token, created_at",
                (user_info['name'], user_info['email'], user_info['user_role'], user_info.get('access_token'), user_info.get('refresh_token'))
            )
            user = cursor.fetchone()
        return {
            "id": user[0], "name": user[1], "email": user[2], "role": user[3],
             "access_token": user[4], "refresh_token": user[5], "created_at": user[6]
        }
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user_info = request.session.get("user")
    return templates.TemplateResponse("home.html", {"request": request, "user": user_info})

@app.get("/signup", response_class=HTMLResponse)
async def signup(request: Request, redirected: bool = False):
    return templates.TemplateResponse(
        "signup.html",
        {"request": request, "redirected": redirected}
    )

# route to questios page
@app.get("/questions", response_class=HTMLResponse)
async def home(request: Request):
    user_info = request.session.get("user")
    return templates.TemplateResponse("questions.html", {"request": request, "user": user_info})

@app.get("/signin", response_class=HTMLResponse)
async def home(request: Request):
    user_info = request.session.get("user")
    return templates.TemplateResponse("signin.html", {"request": request, "user": user_info})

@app.get("/chatapp", response_class=HTMLResponse)
async def chatapp(request: Request):
    user_info = request.session.get("user")
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
                "id": user[0], "name": user[1], "email": user[2], "role": user[3],
                "access_token": user[4], "refresh_token": user[5], "created_at": user[6]
            }
        return templates.TemplateResponse("chat.html", {"request": request, "user": current_user})
    except Exception as e:
        print(f"Error in chatapp: {str(e)}")
        return RedirectResponse(url="/signup?redirected=true", status_code=status.HTTP_302_FOUND)
                                
@app.get("/auth")
async def login(request: Request):
    redirect_uri = 'http://127.0.0.1:8000/auth/callback'
    response = await oauth.google.authorize_redirect(request, redirect_uri, prompt="select_account")
    print(f"Session after login: {request.session}")
    return response

@app.get("/auth/callback")
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
                        "INSERT INTO users (username,email, user_role, access_token, refresh_token, created_at) VALUES (%s, %s, %s, %s, %s, NOW()) RETURNING id",
                        (user_info['name'], user_info['email'], 'client', token['access_token'], token.get('refresh_token'))
                    )
                else:
                    cursor.execute(
                        "UPDATE users SET access_token = %s, refresh_token = %s WHERE email = %s",
                        (token['access_token'], token.get('refresh_token'), user_info['email'])
                    )
        return RedirectResponse(url='/chatapp')
    except Exception as e:
        print(f"Callback error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

@app.get("/logout")
async def logout(request: Request):
    request.session.pop('user', None)
    return RedirectResponse(url='/')

@app.get("/protected", response_class=HTMLResponse)
async def protected_route(request: Request, current_user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("protected.html", {"request": request, "user": current_user})

@app.get("/debug-session")
async def debug_session(request: Request):
    return {"session": request.session}

@app.get("/favicon.ico")
async def favicon():
    return {"message": "No favicon"}