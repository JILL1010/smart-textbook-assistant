import os
import re
import json

import fitz  # PyMuPDF
from docx import Document as DocxDocument
from sqlalchemy.orm import Session

from models.textbook import Textbook
from models.chapter import Chapter


def parse_document(filepath: str, filename: str, db: Session, title: str | None = None) -> Textbook:
    """Parse a PDF or DOCX document and store its structure in the database."""
    title = title or filename.rsplit(".", 1)[0].strip() or "未命名课本"
    ext = os.path.splitext(filepath)[1].lower()

    textbook = Textbook(title=title, filename=filename)
    db.add(textbook)
    db.flush()

    if ext == ".docx":
        _parse_docx(filepath, textbook.id, db)
    else:
        _parse_pdf(filepath, textbook.id, db)

    db.commit()
    db.refresh(textbook)
    return textbook


# ─── PDF parsing ──────────────────────────────────────────────────────────────

def _parse_pdf(filepath: str, textbook_id: int, db: Session):
    # A failed native file open can retain a Windows handle until traceback GC.
    # Own and close the Python file before calling the native parser.
    with open(filepath, "rb") as source:
        data = source.read()
    with fitz.open(stream=data, filetype="pdf") as doc:
        toc = doc.get_toc()
        if toc and len(toc) > 0:
            _parse_from_toc(doc, toc, textbook_id, db)
        else:
            _parse_by_pages(doc, textbook_id, db)


def _parse_from_toc(doc: fitz.Document, toc: list, textbook_id: int, db: Session):
    pages = [None]
    for page in doc:
        pages.append(page.get_text())

    chapter_entries = [(i, entry) for i, entry in enumerate(toc) if entry[0] <= 2]

    for idx, (i, (level, title, start_page)) in enumerate(chapter_entries):
        if idx + 1 < len(chapter_entries):
            end_page = next((entry[2] for _, entry in chapter_entries[idx + 1:] if entry[2] > start_page), len(doc) + 1)
        else:
            end_page = len(doc) + 1

        text_parts = []
        sources = []
        for p in range(max(1, start_page), min(end_page, len(pages))):
            if pages[p]:
                text_parts.append(pages[p].strip())
                sources.append({"text": pages[p].strip(), "page": p})

        content = "\n\n".join(text_parts) if text_parts else None
        db.add(Chapter(
            textbook_id=textbook_id,
            title=title.strip(),
            order=idx + 1,
            content=content,
            source_data=json.dumps(sources, ensure_ascii=False),
        ))


def _parse_by_pages(doc: fitz.Document, textbook_id: int, db: Session):
    chapter_order = 0
    current_title: str | None = None
    current_text: list[str] = []
    current_sources: list[dict] = []

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        page_text = page.get_text().strip()
        if not page_text:
            continue

        first_line = page_text.split("\n")[0].strip()
        is_chapter_start = _looks_like_chapter_title(first_line, blocks)

        if is_chapter_start:
            if current_title:
                chapter_order += 1
                db.add(Chapter(
                    textbook_id=textbook_id,
                    title=current_title,
                    order=chapter_order,
                    content="\n\n".join(current_text) if current_text else None,
                    source_data=json.dumps(current_sources, ensure_ascii=False),
                ))
            current_title = first_line
            current_text = [page_text]
            current_sources = [{"text": page_text, "page": page.number + 1}]
        else:
            if current_title is None:
                current_title = f"第 {chapter_order + 1} 部分"
            current_text.append(page_text)
            current_sources.append({"text": page_text, "page": page.number + 1})

    if current_title:
        chapter_order += 1
        db.add(Chapter(
            textbook_id=textbook_id,
            title=current_title,
            order=chapter_order,
            content="\n\n".join(current_text) if current_text else None,
            source_data=json.dumps(current_sources, ensure_ascii=False),
        ))


def _looks_like_chapter_title(line: str, blocks: list) -> bool:
    if re.match(r"^(第[一二三四五六七八九十\d]+[章节部篇]|Chapter\s*\d+|Part\s*\d+)", line):
        return True
    if len(line) <= 30 and len(line) >= 2:
        text_blocks = [b for b in blocks if b["type"] == 0]
        if text_blocks:
            first_size = None
            body_sizes = []
            for b in text_blocks:
                for span in b.get("lines", []):
                    for s in span.get("spans", []):
                        sz = s.get("size", 0)
                        if first_size is None:
                            first_size = sz
                        else:
                            body_sizes.append(sz)
            if body_sizes and first_size:
                avg_body = sum(body_sizes) / len(body_sizes)
                if first_size > avg_body * 1.15:
                    return True
    return False


# ─── DOCX parsing ─────────────────────────────────────────────────────────────

def _parse_docx(filepath: str, textbook_id: int, db: Session):
    """Parse DOCX using heading styles to detect chapter boundaries."""
    doc = DocxDocument(filepath)

    # Collect paragraphs with their heading level
    entries: list[dict] = []  # {level, title, paragraphs}
    current: dict | None = None

    for paragraph, para in enumerate(doc.paragraphs, 1):
        text = para.text.strip()
        if not text:
            if current is not None:
                current["paragraphs"].append("")
            continue

        heading_level = _get_heading_level(para)
        if heading_level is not None and heading_level <= 2:
            if current is not None:
                entries.append(current)
            current = {"level": heading_level, "title": text, "paragraphs": [], "sources": []}
        elif current is not None:
            current["paragraphs"].append(text)
            current["sources"].append({"text": text, "paragraph": paragraph})
        else:
            # Text before any heading — start an implicit chapter
            current = {"level": 0, "title": text[:50], "paragraphs": [text], "sources": [{"text": text, "paragraph": paragraph}]}

    if current is not None:
        entries.append(current)

    # If no structured headings found, try font-size heuristics
    if not entries:
        _parse_docx_flat(doc, textbook_id, db)
        return

    for idx, entry in enumerate(entries):
        body = "\n\n".join(entry["paragraphs"]) if entry["paragraphs"] else None
        db.add(Chapter(
            textbook_id=textbook_id,
            title=entry["title"],
            order=idx + 1,
            content=body,
            source_data=json.dumps(entry["sources"], ensure_ascii=False),
        ))


def _parse_docx_flat(doc: DocxDocument, textbook_id: int, db: Session):
    """Fallback: treat entire document as one chapter."""
    all_text = []
    for para in doc.paragraphs:
        t = para.text.strip()
        if t:
            all_text.append(t)

    if not all_text:
        db.add(Chapter(
            textbook_id=textbook_id,
            title="全文",
            order=1,
            content=None,
        ))
        return

    title = all_text[0][:80]
    db.add(Chapter(
        textbook_id=textbook_id,
        title=title,
        order=1,
        content="\n\n".join(all_text),
    ))


def _get_heading_level(para) -> int | None:
    """Return heading level (1-9) if the paragraph is a heading, else None."""
    style_name = para.style.name if para.style else ""
    # Match built-in "Heading 1", "Heading 2", etc.
    m = re.match(r"^[Hh]eading\s+(\d+)$", style_name)
    if m:
        return int(m.group(1))
    # Match Chinese heading styles "标题 1", "标题1"
    m = re.match(r"^标题\s*(\d+)$", style_name)
    if m:
        return int(m.group(1))
    # Check if it looks like a heading based on bold + larger font
    if para.runs:
        run = para.runs[0]
        if run.bold and len(para.text.strip()) <= 80:
            return 2  # treat bold short lines as Heading 2
    return None
