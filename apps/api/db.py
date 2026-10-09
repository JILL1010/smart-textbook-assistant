from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from models.textbook import Textbook  # noqa: F401
    from models.chapter import Chapter  # noqa: F401
    from models.learning import StudyProgress, QuizAttempt, ReviewItem  # noqa: F401
    from models.generation_task import GenerationTask  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Migrations: add columns if missing
    from sqlalchemy import text, inspect
    insp = inspect(engine)
    if insp.has_table("chapters"):
        cols = {c["name"] for c in insp.get_columns("chapters")}
        migrations = [
            ("generated_content", "TEXT"),
            ("generation_metadata", "TEXT"),
            ("source_data", "TEXT"),
            ("generation_revision", "INTEGER NOT NULL DEFAULT 0"),
            ("audio_filename", "VARCHAR(500)"),
            ("quiz_data", "TEXT"),
            ("knowledge_graph_data", "TEXT"),
        ]
        with engine.connect() as conn:
            for col_name, col_type in migrations:
                if col_name not in cols:
                    conn.execute(text(f"ALTER TABLE chapters ADD COLUMN {col_name} {col_type}"))
            conn.commit()
