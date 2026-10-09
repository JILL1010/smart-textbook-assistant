import os
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from config import settings
from db import get_db
from models.textbook import Textbook
from models.chapter import Chapter
from services.artifacts import remove_audio
from models.learning import StudyProgress, QuizAttempt, ReviewItem
from models.generation_task import GenerationTask

router = APIRouter()


def _serialize_textbook_summary(tb: Textbook):
    generated = sum(1 for ch in tb.chapters if ch.generated_content)
    return {
        "id": tb.id,
        "title": tb.title,
        "filename": tb.filename,
        "chapter_count": len(tb.chapters),
        "generated_count": generated,
        "created_at": tb.created_at.isoformat(),
    }


def _serialize_textbook_detail(tb: Textbook):
    data = _serialize_textbook_summary(tb)
    data["chapters"] = [
        {
            "id": ch.id,
            "textbook_id": ch.textbook_id,
            "title": ch.title,
            "order": ch.order,
            "content": ch.content,
            "generated_content": ch.generated_content,
            "generation_metadata": json.loads(ch.generation_metadata) if ch.generation_metadata else None,
            "audio_filename": ch.audio_filename,
            "quiz_data": ch.quiz_data,
            "knowledge_graph_data": ch.knowledge_graph_data,
        }
        for ch in tb.chapters
    ]
    return data


@router.get("/textbooks")
def list_textbooks(db: Session = Depends(get_db)):
    textbooks = db.query(Textbook).order_by(Textbook.created_at.desc()).all()
    return [_serialize_textbook_summary(tb) for tb in textbooks]


@router.get("/textbooks/{textbook_id}")
def get_textbook(textbook_id: int, db: Session = Depends(get_db)):
    tb = db.query(Textbook).filter(Textbook.id == textbook_id).first()
    if not tb:
        raise HTTPException(404, "课本不存在")
    return _serialize_textbook_detail(tb)


@router.get("/textbooks/{textbook_id}/file")
def get_original_file(textbook_id: int, db: Session = Depends(get_db)):
    tb = db.query(Textbook).filter(Textbook.id == textbook_id).first()
    if not tb:
        raise HTTPException(404, "课本不存在")
    filepath = os.path.join(settings.upload_dir, os.path.basename(tb.filename))
    if not os.path.isfile(filepath):
        raise HTTPException(404, "原始教材文件不存在")
    is_pdf = tb.filename.lower().endswith(".pdf")
    return FileResponse(filepath, media_type="application/pdf" if is_pdf else "application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=tb.filename, content_disposition_type="inline" if is_pdf else "attachment")


@router.delete("/textbooks/{textbook_id}")
def delete_textbook(textbook_id: int, db: Session = Depends(get_db)):
    tb = db.query(Textbook).filter(Textbook.id == textbook_id).first()
    if not tb:
        raise HTTPException(404, "课本不存在")

    # Collect audio files to clean up
    chapters = db.query(Chapter).filter(Chapter.textbook_id == textbook_id).all()
    audio_files_to_remove = [ch.audio_filename for ch in chapters]

    # Delete uploaded file
    filepath = os.path.join(settings.upload_dir, tb.filename)
    if os.path.isfile(filepath):
        os.remove(filepath)

    # Delete audio and subtitle files
    for filename in audio_files_to_remove:
        remove_audio(filename)

    chapter_ids = [ch.id for ch in chapters]
    for model in (StudyProgress, QuizAttempt, ReviewItem, GenerationTask):
        db.query(model).filter(model.chapter_id.in_(chapter_ids)).delete(synchronize_session=False)
    db.query(Chapter).filter(Chapter.textbook_id == textbook_id).delete()
    db.delete(tb)
    db.commit()

    return {"status": "deleted"}
