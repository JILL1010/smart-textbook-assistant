from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class GenerationTask(Base):
    __tablename__ = "generation_tasks"
    __table_args__ = (Index("one_active_task_per_chapter", "chapter_id", unique=True,
                           sqlite_where=text("status IN ('queued', 'running')")),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    revision: Mapped[int] = mapped_column(Integer)
    parameters: Mapped[str] = mapped_column(Text)
    source_text: Mapped[str] = mapped_column(Text)
    chapter_title: Mapped[str] = mapped_column(Text)
    completed_parts: Mapped[int] = mapped_column(Integer, default=0)
    total_parts: Mapped[int] = mapped_column(Integer)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
