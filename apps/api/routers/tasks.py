from typing import Literal
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from db import get_db
from models.generation_task import GenerationTask
from routers.learning import get_chapter
from services.tasks import TaskManager, get_manager, serialize_task, ACTIVE

router = APIRouter()
PATH = "/textbooks/{textbook_id}/chapters/{chapter_id}/tasks"


class TaskRequest(BaseModel):
    kind: Literal["lecture", "quiz", "graph"]
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    style: Literal["teacher", "concise", "story"] = "teacher"
    num_questions: int = Field(default=5, ge=1, le=20)


@router.get(PATH)
def list_tasks(textbook_id: int, chapter_id: int, db: Session = Depends(get_db)):
    get_chapter(db, textbook_id, chapter_id)
    tasks = db.query(GenerationTask).filter_by(chapter_id=chapter_id).order_by(GenerationTask.created_at.desc()).limit(20).all()
    return [serialize_task(task) for task in tasks]


@router.post(PATH, status_code=202)
def start_task(textbook_id: int, chapter_id: int, body: TaskRequest, db: Session = Depends(get_db), manager: TaskManager = Depends(get_manager)):
    chapter = get_chapter(db, textbook_id, chapter_id)
    return manager.start(db, chapter, body.kind, body.model_dump(exclude={"kind"}))


def find_task(db, textbook_id, chapter_id, task_id):
    get_chapter(db, textbook_id, chapter_id)
    task = db.query(GenerationTask).filter_by(id=task_id, chapter_id=chapter_id).first()
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


@router.post(PATH + "/{task_id}/cancel")
def cancel_task(textbook_id: int, chapter_id: int, task_id: str, db: Session = Depends(get_db)):
    task = find_task(db, textbook_id, chapter_id, task_id)
    if task.status in ACTIVE:
        db.execute(update(GenerationTask).where(GenerationTask.id == task_id, GenerationTask.status.in_(ACTIVE)).values(cancel_requested=True))
        db.execute(update(GenerationTask).where(GenerationTask.id == task_id, GenerationTask.status == "queued").values(status="cancelled", finished_at=datetime.utcnow()))
        db.commit()
        db.refresh(task)
    return serialize_task(task)


@router.post(PATH + "/{task_id}/retry", status_code=202)
def retry_task(textbook_id: int, chapter_id: int, task_id: str, db: Session = Depends(get_db), manager: TaskManager = Depends(get_manager)):
    task = find_task(db, textbook_id, chapter_id, task_id)
    if task.status not in ("failed", "cancelled", "interrupted"):
        raise HTTPException(409, "只有失败、停止或中断的任务可以重试")
    chapter = get_chapter(db, textbook_id, chapter_id)
    if chapter.generation_revision != task.revision:
        raise HTTPException(409, "章节已更新，请基于当前内容重新生成")
    return manager.start(db, chapter, task.kind, json.loads(task.parameters))
