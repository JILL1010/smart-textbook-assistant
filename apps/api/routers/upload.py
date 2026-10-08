import os
import uuid
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from db import get_db
from services.parser import parse_document

router = APIRouter()


@router.post("/upload")
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".docx"):
        raise HTTPException(400, "仅支持 PDF 和 DOCX 格式")

    os.makedirs(settings.upload_dir, exist_ok=True)

    unique_name = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(settings.upload_dir, unique_name)

    limit = settings.max_upload_size_mb * 1024 * 1024
    size = 0
    try:
        with open(filepath, "wb") as destination:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"文件大小不能超过 {settings.max_upload_size_mb} MB")
                destination.write(chunk)
        if size == 0:
            raise HTTPException(400, "文件不能为空")
        textbook = parse_document(
            filepath, unique_name, db,
            title=file.filename.rsplit(".", 1)[0].strip() or "未命名课本",
        )
    except Exception as exc:
        db.rollback()
        if os.path.isfile(filepath):
            os.remove(filepath)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(400, "文件解析失败，请上传有效的 PDF 或 DOCX 文件") from exc
    finally:
        file.file.close()

    return {
        "id": textbook.id,
        "title": textbook.title,
        "filename": textbook.filename,
        "chapter_count": len(textbook.chapters),
        "created_at": textbook.created_at.isoformat(),
    }
