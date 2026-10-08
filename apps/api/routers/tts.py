import json
import os
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from config import settings
from db import get_db
from models.chapter import Chapter
from services.tts import generate_audio
from services.artifacts import remove_audio, save_artifact

router = APIRouter()


def _clean_for_tts(text: str) -> str:
    """Strip markdown formatting for cleaner TTS input."""
    # Remove headers, code fences, horizontal rules, blockquotes
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"^---+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # Remove inline formatting chars
    text = text.replace("**", "").replace("*", "").replace("`", "").replace("_", "")
    # Collapse blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@router.post("/textbooks/{textbook_id}/chapters/{chapter_id}/tts")
async def generate_tts(
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

    text = chapter.generated_content or chapter.content
    if not text:
        raise HTTPException(400, "章节无内容，请先生成讲解")

    clean_text = _clean_for_tts(text)
    if not clean_text:
        raise HTTPException(400, "章节没有可朗读的文本")
    revision = chapter.generation_revision

    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(settings.audio_dir, filename)

    try:
        _, subtitles = await generate_audio(clean_text, filepath)
        db.refresh(chapter)
        old_audio = chapter.audio_filename
        save_artifact(db, chapter, revision, audio_filename=filename)
    except HTTPException:
        remove_audio(filename)
        raise
    except Exception as exc:
        db.rollback()
        remove_audio(filename)
        raise HTTPException(502, "语音生成失败，请稍后重试") from exc
    remove_audio(old_audio)

    return {
        "status": "ok",
        "audio_url": f"/api/audio/{filename}",
        "subtitle_url": f"/api/subtitles/{filename.rsplit('.', 1)[0]}.json",
        "subtitles": subtitles,
    }


@router.get("/audio/{filename}")
def serve_audio(filename: str):
    if os.path.basename(filename) != filename or not filename.endswith(".mp3"):
        raise HTTPException(404, "音频文件不存在")
    filepath = os.path.join(settings.audio_dir, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(404, "音频文件不存在")
    return FileResponse(filepath, media_type="audio/mpeg")


@router.get("/subtitles/{filename}")
def serve_subtitles(filename: str):
    if os.path.basename(filename) != filename or not filename.endswith(".json"):
        raise HTTPException(404, "字幕文件不存在")
    filepath = os.path.join(settings.audio_dir, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(404, "字幕文件不存在")
    with open(filepath, "r", encoding="utf-8") as f:
        return JSONResponse(json.load(f))
