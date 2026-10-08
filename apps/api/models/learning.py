from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from db import Base


class StudyProgress(Base):
    __tablename__ = "study_progress"
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), primary_key=True)
    read_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    draft_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    draft_answers: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_seq: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), index=True)
    generation_revision: Mapped[int] = mapped_column(Integer)
    quiz_token: Mapped[str] = mapped_column(String(64))
    quiz_snapshot: Mapped[str] = mapped_column(Text)
    answers: Mapped[str] = mapped_column(Text)
    correct: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (UniqueConstraint("chapter_id", "quiz_token", "question_index"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), index=True)
    quiz_token: Mapped[str] = mapped_column(String(64))
    question_index: Mapped[int] = mapped_column(Integer)
    question_snapshot: Mapped[str] = mapped_column(Text)
    selected_answer: Mapped[int] = mapped_column(Integer)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
