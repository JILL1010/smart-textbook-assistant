"""One local worker, persistent progress, and transactional result publication."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from threading import Event
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import update, case
from sqlalchemy.exc import IntegrityError

from models.chapter import Chapter
from models.generation_task import GenerationTask
from services import generator
from services.artifacts import save_artifact, save_lecture

ACTIVE = ("queued", "running")


class TaskStopped(Exception):
    pass


def serialize_task(task):
    return {"id": task.id, "chapter_id": task.chapter_id, "kind": task.kind, "status": task.status,
            "revision": task.revision, "parameters": json.loads(task.parameters),
            "completed_parts": task.completed_parts, "total_parts": task.total_parts,
            "cancel_requested": task.cancel_requested, "error": task.error,
            "created_at": task.created_at.isoformat() + "Z",
            "finished_at": task.finished_at.isoformat() + "Z" if task.finished_at else None}


def ensure_no_active_task(db, chapter_id):
    if db.query(GenerationTask).filter(GenerationTask.chapter_id == chapter_id, GenerationTask.status.in_(ACTIVE)).first():
        raise HTTPException(409, "本章已有生成任务，请等待完成或停止任务")


class TaskManager:
    def __init__(self, sessions):
        self.sessions = sessions
        self.stopping = Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="textbook-generation")

    def recover(self):
        # The previous process cannot continue its network request. Never claim resume.
        with self.sessions() as db:
            db.query(GenerationTask).filter(GenerationTask.status.in_(ACTIVE)).update({
                "status": "interrupted", "finished_at": datetime.utcnow(),
                "error": "服务已重启，任务中断；已有内容保留，可从头重试。",
            }, synchronize_session=False)
            db.commit()

    def close(self):
        self.stopping.set()
        self.recover()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def start(self, db, chapter, kind, parameters):
        if self.stopping.is_set():
            raise HTTPException(503, "生成服务正在关闭")
        existing = db.query(GenerationTask).filter(GenerationTask.chapter_id == chapter.id, GenerationTask.status.in_(ACTIVE)).first()
        if existing:
            if existing.kind != kind:
                raise HTTPException(409, "本章已有其他生成任务，请等待完成或停止任务")
            return serialize_task(existing)
        source = chapter.content if kind == "lecture" else chapter.generated_content
        if not source or not source.strip():
            raise HTTPException(400, "章节原文为空" if kind == "lecture" else "请先生成章节讲解内容")
        total = len(generator.chapter_segments(source))
        if total > 40:
            raise HTTPException(400, "内容超过 40 个片段，请先按小节导入")
        task = GenerationTask(id=str(uuid4()), chapter_id=chapter.id, kind=kind,
                              revision=chapter.generation_revision, parameters=json.dumps(parameters),
                              source_text=source, chapter_title=chapter.title, total_parts=total)
        db.add(task)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.query(GenerationTask).filter(GenerationTask.chapter_id == chapter.id, GenerationTask.status.in_(ACTIVE)).first()
            if existing and existing.kind == kind:
                return serialize_task(existing)
            raise HTTPException(409, "本章已有生成任务")
        result = serialize_task(task)
        self.executor.submit(self.run, task.id)
        return result

    def _progress(self, task_id, completed, total):
        if self.stopping.is_set():
            raise TaskStopped()
        with self.sessions() as db:
            task = db.get(GenerationTask, task_id)
            if not task or task.status != "running" or task.cancel_requested:
                raise TaskStopped()
            chapter = db.get(Chapter, task.chapter_id)
            if not chapter or chapter.generation_revision != task.revision:
                raise HTTPException(409, "章节已更新，任务结果失效，请重新开始")
            result = db.execute(update(GenerationTask).where(
                GenerationTask.id == task_id, GenerationTask.status == "running",
                GenerationTask.cancel_requested.is_(False),
            ).values(completed_parts=completed, total_parts=total))
            if result.rowcount != 1:
                raise TaskStopped()
            db.commit()

    def _finish(self, task_id, status, error=None):
        with self.sessions() as db:
            db.execute(update(GenerationTask).where(GenerationTask.id == task_id, GenerationTask.status.in_(ACTIVE)).values(
                status=case((GenerationTask.cancel_requested.is_(True), "cancelled"), else_=status),
                error=error, finished_at=datetime.utcnow(),
            ))
            db.commit()

    def run(self, task_id):
        try:
            with self.sessions() as db:
                claimed = db.execute(update(GenerationTask).where(
                    GenerationTask.id == task_id, GenerationTask.status == "queued",
                    GenerationTask.cancel_requested.is_(False),
                ).values(status="running"))
                db.commit()
                if claimed.rowcount != 1:
                    return
                task = db.get(GenerationTask, task_id)
                kind, source, title, parameters, revision = task.kind, task.source_text, task.chapter_title, json.loads(task.parameters), task.revision
            progress = lambda completed, total: self._progress(task_id, completed, total)
            if kind == "lecture":
                result = generator.generate_chapter_content(title, source, parameters["difficulty"], parameters["style"], progress=progress)
            elif kind == "quiz":
                result = generator.generate_quiz(title, source, parameters["difficulty"], parameters["num_questions"], progress=progress)
            else:
                result = generator.generate_knowledge_graph(title, source, progress=progress)
            # Cancellation and result publication compete for the same SQLite write lock.
            with self.sessions() as db:
                task = db.get(GenerationTask, task_id)
                if not task:
                    return
                published = db.execute(update(GenerationTask).where(
                    GenerationTask.id == task_id, GenerationTask.status == "running",
                    GenerationTask.cancel_requested.is_(False),
                ).values(status="succeeded", completed_parts=task.total_parts, finished_at=datetime.utcnow()))
                if published.rowcount != 1 or self.stopping.is_set():
                    db.rollback()
                    raise TaskStopped()
                chapter = db.get(Chapter, task.chapter_id)
                if not chapter:
                    db.rollback()
                    raise TaskStopped()
                if kind == "lecture":
                    metadata = generator.generation_metadata(source, parameters["difficulty"], parameters["style"])
                    save_lecture(db, chapter, revision, result, metadata)
                else:
                    field = "quiz_data" if kind == "quiz" else "knowledge_graph_data"
                    save_artifact(db, chapter, revision, **{field: json.dumps(result, ensure_ascii=False)})
        except TaskStopped:
            self._finish(task_id, "cancelled")
        except HTTPException as error:
            self._finish(task_id, "failed", str(error.detail))
        except Exception:
            # Model exceptions can contain request details; keep those out of task responses.
            self._finish(task_id, "failed", "生成失败；已有内容保留。请检查模型设置后重试。")


manager = None


def get_manager():
    if manager is None:
        raise HTTPException(503, "生成服务尚未启动")
    return manager
