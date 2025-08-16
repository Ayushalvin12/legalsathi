from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from dotenv import load_dotenv
import os
from auth.routes import router as auth_router
from rag_pipeline.extraction.routes import router as extraction_router

load_dotenv()
print(f"GOOGLE_CLIENT_ID in main.py: {os.getenv('GOOGLE_CLIENT_ID')}")
print(f"GOOGLE_CLIENT_SECRET in main.py: {os.getenv('GOOGLE_CLIENT_SECRET')}")

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY"),
    session_cookie="legalsathi_session",
    max_age=3600,
    same_site="lax",
    domain="127.0.0.1"
)

BASE_DIR = Path(__file__).resolve().parent / "auth"
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")))

print("Loading auth_router and extraction_router")  # Debug
app.include_router(auth_router)  # No prefix
app.include_router(extraction_router)  # No prefix
print("Routers loaded successfully")  # Debug