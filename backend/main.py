"""Sermon Study API. Run locally with:  uvicorn main:app --reload"""
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai import embeddings_available, model_name
from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.routes.ask import router as ask_router
from app.routes.bible import router as bible_router
from app.routes.churches import router as churches_router
from app.routes.jobs import router as jobs_router
from app.routes.public import router as public_router
from app.routes.sermons import router as sermons_router
from app.routes.studyguide import router as studyguide_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Sermon Study API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # auth uses a bearer token, not cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sermons_router, prefix="/sermons", tags=["Sermons"])
app.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
app.include_router(ask_router, prefix="/ask", tags=["Ask"])
app.include_router(bible_router, prefix="/bible", tags=["Bible"])
app.include_router(churches_router, prefix="/churches", tags=["Churches"])
app.include_router(studyguide_router, prefix="/studyguide", tags=["Study Guide"])
app.include_router(public_router, prefix="/public", tags=["Public"])


@app.get("/")
def root():
    return {"status": "Sermon Study API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def public_config():
    """What the frontend needs to know: which AI models are set up, and whether semantic search is on."""
    models = settings.available_models()
    return {
        "models": [{"id": m, "name": model_name(m)} for m in models],
        "default_model": settings.default_model if settings.default_model in models else (models[0] if models else None),
        "semantic_search": embeddings_available(),
        "audio_transcription": bool(settings.groq_api_key or settings.openai_api_key),
        "monthly_sermon_limit": settings.monthly_sermon_limit,
        "max_upload_mb": settings.max_upload_mb,
    }


@app.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}
