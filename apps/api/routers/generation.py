from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal
from sqlalchemy.orm import Session

from db import get_db
from models.chapter import Chapter
from services.generator import generate_chapter_content, generation_metadata
from services.artifacts import save_lecture
from services.tasks import ensure_no_active_task

router = APIRouter()


class GenerateRequest(BaseModel):
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    style: Literal["teacher", "concise", "story"] = "teacher"


@router.post("/textbooks/{textbook_id}/chapters/{chapter_id}/generate")
def generate(
    textbook_id: int,
    chapter_id: int,
    body: GenerateRequest = GenerateRequest(),
    db: Session = Depends(get_db),
):
    chapter = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.textbook_id == textbook_id)
        .first()
    )
    if not chapter:
        raise HTTPException(404, "章节不存在")
    ensure_no_active_task(db, chapter.id)

    revision = chapter.generation_revision
    try:
        generated = generate_chapter_content(
            chapter_title=chapter.title,
            chapter_text=chapter.content,
            difficulty=body.difficulty,
            style=body.style,
        )
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    db.refresh(chapter)
    metadata = generation_metadata(chapter.content, body.difficulty, body.style)
    save_lecture(db, chapter, revision, generated, metadata)

    return {"status": "ok", "content": chapter.content, "generated_content": generated,
            "generation_metadata": metadata}
