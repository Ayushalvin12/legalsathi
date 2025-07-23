# backend/main.py

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv
import os
import logging

# === Load environment variables ===
load_dotenv()

# === Configure base directories ===
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# === Create FastAPI app ===
app = FastAPI(
    title="LegalSathi Backend",
    version="1.0.0",
    description="FastAPI backend for LegalSathi legal assistant with chat, auth, and document embedding",
    docs_url="/docs",
    redoc_url="/redoc"
)

# === Logger setup ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("legalsathi")

# === Mount static and templates ===
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# === Middleware: Session ===
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "fallback-dev-key"),
    session_cookie="legalsathi_session",
    max_age=3600,
    same_site="lax"
)

# === Middleware: CORS (optional) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Include Routers ===
try:
    from backend.auth import auth_endpoints
    from backend.rag_pipeline.retriever import retriever_endpoints
    from backend.rag_pipeline.extraction import extraction_endpoints

    app.include_router(auth_endpoints.router, prefix="/auth", tags=["Auth"])
    app.include_router(retriever_endpoints.router, prefix="/chat", tags=["Chat"])
    app.include_router(extraction_endpoints.router, prefix="/extract", tags=["Embedding"])

    logger.info("✅ Routers registered successfully.")

except ImportError as e:
    logger.error(f"❌ Failed to import routers: {e}")
    raise

# === Root health check ===
@app.get("/", tags=["Health"])
async def health_check():
    return {"status": "ok", "message": "LegalSathi API is up and running 🎉"}

# === Global Exception Handler ===
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"🔥 Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again later."}
    )
