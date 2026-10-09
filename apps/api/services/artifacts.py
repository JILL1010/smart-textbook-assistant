"""Persist derived content only while its source revision is still current."""
import logging
import json
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from config import settings
from models.chapter import Chapter


def remove_audio(filename: str | None) -> None:
    if not filename or Path(filename).name != filename:
        return
    audio = Path(settings.audio_dir) / filename
    for path in (audio, audio.with_suffix(".json")):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).warning("Could not remove obsolete audio: %s", path)


def save_artifact(db: Session, chapter: Chapter, revision: int, **values) -> None:
    result = db.execute(
        update(Chapter)
        .where(Chapter.id == chapter.id, Chapter.generation_revision == revision)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "章节讲解已更新，请根据新讲解重新生成")
    db.commit()


def save_lecture(db: Session, chapter: Chapter, revision: int, generated: str, metadata: dict) -> None:
    old_audio = chapter.audio_filename
    result = db.execute(update(Chapter).where(Chapter.id == chapter.id, Chapter.generation_revision == revision).values(
        generated_content=generated, generation_metadata=json.dumps(metadata, ensure_ascii=False),
        generation_revision=revision + 1, audio_filename=None, quiz_data=None, knowledge_graph_data=None,
    ).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "章节已更新，请刷新后重新生成")
    db.commit()
    remove_audio(old_audio)
