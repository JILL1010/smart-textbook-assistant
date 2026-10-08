from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.orm import Session

from db import get_db
from models.chapter import Chapter
from services.cited_qa import answer_with_sources
from services.retrieval import retrieve_sources

router = APIRouter()

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=12000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    messages: list[ChatMessage] = Field(default_factory=list, max_length=20)


@router.post("/textbooks/{textbook_id}/chapters/{chapter_id}/ask")
def ask_question(
    textbook_id: int,
    chapter_id: int,
    body: AskRequest,
    db: Session = Depends(get_db),
):
    chapter = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.textbook_id == textbook_id)
        .first()
    )
    if not chapter:
        raise HTTPException(404, "章节不存在")

    question = body.question.strip()
    if not question:
        raise HTTPException(400, "问题不能为空")
    history = [message.model_dump() for message in body.messages[-10:]]
    query = question
    if any(word in question.lower() for word in ("它", "这个", "上述", "this", "that")):
        previous = next((message["content"] for message in reversed(history) if message["role"] == "user"), "")
        query += " " + previous[-1000:]
    sources = retrieve_sources(db, chapter, query)
    try:
        return answer_with_sources(question, history, sources)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
