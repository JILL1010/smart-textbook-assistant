import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db import init_db
from routers import upload, textbooks, chapters, generation, qa, tts, quiz, knowledge_graph, learning, tasks
from services import tasks as task_service
from db import SessionLocal


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.upload_dir, exist_ok=True)
    os.makedirs(settings.audio_dir, exist_ok=True)
    init_db()
    task_service.manager = task_service.TaskManager(SessionLocal)
    task_service.manager.recover()
    try:
        yield
    finally:
        task_service.manager.close()
        task_service.manager = None


app = FastAPI(title="智能课本助手 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, prefix="/api", tags=["Upload"])
app.include_router(textbooks.router, prefix="/api", tags=["Textbooks"])
app.include_router(chapters.router, prefix="/api", tags=["Chapters"])
app.include_router(generation.router, prefix="/api", tags=["Generation"])
app.include_router(qa.router, prefix="/api", tags=["Q&A"])
app.include_router(tts.router, prefix="/api", tags=["TTS"])
app.include_router(quiz.router, prefix="/api", tags=["Quiz"])
app.include_router(knowledge_graph.router, prefix="/api", tags=["KnowledgeGraph"])
app.include_router(learning.router, prefix="/api", tags=["Learning"])
app.include_router(tasks.router, prefix="/api", tags=["Generation tasks"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
