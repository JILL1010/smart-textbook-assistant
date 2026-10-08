import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
from models.chapter import Chapter
from services.generator import generate_knowledge_graph
from services.artifacts import save_artifact

router = APIRouter()


@router.post("/textbooks/{textbook_id}/chapters/{chapter_id}/knowledge-graph")
def generate_knowledge_graph_endpoint(
    textbook_id: int,
    chapter_id: int,
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
        graph = generate_knowledge_graph(
            chapter_title=chapter.title,
            chapter_text=source_text,
        )
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    save_artifact(db, chapter, revision, knowledge_graph_data=json.dumps(graph, ensure_ascii=False))

    return {"status": "ok", "data": graph}
