import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from models.chapter import Chapter
from services.generator import generate_quiz
from services.artifacts import save_artifact
from services.learning import quiz_token

router = APIRouter()


class QuizRequest(BaseModel):
    num_questions: int = Field(default=5, ge=1, le=20)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    style: Literal["teacher", "concise", "story"] = "teacher"


@router.post("/textbooks/{textbook_id}/chapters/{chapter_id}/quiz")
def generate_quiz_endpoint(
    textbook_id: int,
    chapter_id: int,
    body: QuizRequest = QuizRequest(),
    db: Session = Depends(get_db),
):
    chapter = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.textbook_id == textbook_id)
        .first()
    )
    if not chapter:
        raise HTTPException(404, "章节不存在")

    if not chapter.generated_content:
        raise HTTPException(400, "请先生成章节讲解内容")

    source_text = chapter.generated_content or chapter.content or ""
    revision = chapter.generation_revision

    try:
        quiz = generate_quiz(
            chapter_title=chapter.title,
            chapter_text=source_text,
            difficulty=body.difficulty,
            num_questions=body.num_questions,
        )
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    save_artifact(db, chapter, revision, quiz_data=json.dumps(quiz, ensure_ascii=False))

    return {"status": "ok", "quiz": quiz, "quiz_token": quiz_token(json.dumps(quiz, ensure_ascii=False))}
