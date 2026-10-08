from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    textbook_id: Mapped[int] = mapped_column(Integer, ForeignKey("textbooks.id"))
    title: Mapped[str] = mapped_column(String(500))
    order: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    audio_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quiz_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge_graph_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    textbook = relationship("Textbook", back_populates="chapters")
