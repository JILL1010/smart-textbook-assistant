from fastapi import APIRouter, Depends, HTTPException
import json
from sqlalchemy.orm import Session

from db import get_db
from models.textbook import Textbook
from models.chapter import Chapter
from services.retrieval import chapter_sources
from services.learning import quiz_token

router = APIRouter()


@router.get("/textbooks/{textbook_id}/chapters/{chapter_id}")
def get_chapter(textbook_id: int, chapter_id: int, db: Session = Depends(get_db)):
    chapter = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.textbook_id == textbook_id)
        .first()
    )
    if not chapter:
        raise HTTPException(404, "章节不存在")
    return {
        "id": chapter.id,
        "textbook_id": chapter.textbook_id,
        "title": chapter.title,
        "order": chapter.order,
        "content": chapter.content,
        "generated_content": chapter.generated_content,
        "generation_metadata": json.loads(chapter.generation_metadata) if chapter.generation_metadata else None,
        "audio_filename": chapter.audio_filename,
        "quiz_data": chapter.quiz_data,
        "quiz_token": quiz_token(chapter.quiz_data),
        "knowledge_graph_data": chapter.knowledge_graph_data,
    }


@router.get("/textbooks/{textbook_id}/chapters/{chapter_id}/sources/{source_id}")
def get_source(textbook_id: int, chapter_id: int, source_id: str, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.textbook_id == textbook_id).first()
    if not chapter:
        raise HTTPException(404, "章节不存在")
    source = next((item for item in chapter_sources(chapter) if item["id"] == source_id), None)
    if not source:
        raise HTTPException(404, "原文片段不存在")
    return source
