from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal
import json
from sqlalchemy import update
from sqlalchemy.orm import Session

from db import get_db
from models.chapter import Chapter
from services.generator import generate_chapter_content, generation_metadata
from services.artifacts import remove_audio

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
    old_audio = chapter.audio_filename
    metadata = generation_metadata(chapter.content, body.difficulty, body.style)
    result = db.execute(
        update(Chapter)
        .where(Chapter.id == chapter_id, Chapter.generation_revision == revision)
        .values(
            generated_content=generated,
            generation_metadata=json.dumps(metadata, ensure_ascii=False),
            generation_revision=revision + 1,
            audio_filename=None,
            quiz_data=None,
            knowledge_graph_data=None,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "章节已被重新生成，请刷新后重试")
    db.commit()
    remove_audio(old_audio)

    return {"status": "ok", "content": chapter.content, "generated_content": generated,
            "generation_metadata": metadata}
