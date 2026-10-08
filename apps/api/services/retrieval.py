"""Inspectable lexical retrieval with stable, original-text evidence locations."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

import fitz
from docx import Document
from sqlalchemy.orm import Session

from config import settings
from models.chapter import Chapter


def text_parts(text: str, size: int = 900, overlap: int = 100):
    for start in range(0, len(text), size - overlap):
        yield start, text[start:start + size]
        if start + size >= len(text):
            break


def _recover_sources(chapter: Chapter) -> list[dict]:
    """Recover exact legacy locations only when chapter text has a unique match."""
    filename = chapter.textbook.filename
    path = Path(settings.upload_dir) / Path(filename).name
    if not path.is_file():
        return []
    try:
        if path.suffix.lower() == ".pdf":
            with fitz.open(path) as document:
                units = [{"text": page.get_text().strip(), "page": page.number + 1} for page in document]
        else:
            units = [{"text": para.text.strip(), "paragraph": i} for i, para in enumerate(Document(path).paragraphs, 1)]
    except Exception:
        return []
    units = [unit for unit in units if unit["text"]]
    combined = "\n\n".join(unit["text"] for unit in units)
    content = re.sub(r"\n{3,}", "\n\n", chapter.content or "").strip()
    start = combined.find(content) if content else -1
    if start < 0 or combined.find(content, start + 1) >= 0:
        return []
    end, cursor, recovered = start + len(content), 0, []
    for unit in units:
        unit_end = cursor + len(unit["text"])
        if cursor < end and unit_end > start:
            local_start = max(0, start - cursor)
            recovered.append({**unit, "text": unit["text"][local_start:min(len(unit["text"]), end - cursor)], "base_offset": local_start})
        cursor = unit_end + 2
    return recovered


def chapter_sources(chapter: Chapter) -> list[dict]:
    try:
        units = json.loads(chapter.source_data) if chapter.source_data else []
        if not isinstance(units, list):
            units = []
    except (ValueError, TypeError):
        units = []
    if not units:
        units = _recover_sources(chapter)
    if not units:
        # Existing books remain usable, but never invent page numbers.
        units = [{"text": chapter.content or "", "location": "章节原文（原始页码未恢复）"}]
    sources = []
    for unit_index, unit in enumerate(units):
        if not isinstance(unit, dict) or not isinstance(unit.get("text"), str):
            continue
        for offset, excerpt in text_parts(unit["text"]):
            if not excerpt.strip():
                continue
            digest = hashlib.sha256(f"{chapter.id}:{unit_index}:{offset}:{excerpt}".encode()).hexdigest()[:16]
            page, paragraph = unit.get("page"), unit.get("paragraph")
            location = f"PDF 第 {page} 页（文件页序）" if page else f"DOCX 第 {paragraph} 段" if paragraph else unit.get("location", "章节原文")
            sources.append({
                "id": digest, "chapter_id": chapter.id, "chapter_title": chapter.title,
                "textbook_id": chapter.textbook_id, "page": page, "paragraph": paragraph,
                "location": location, "offset": unit.get("base_offset", 0) + offset, "text": excerpt,
            })
    return sources


def _tokens(text: str) -> list[str]:
    tokens = []
    for word in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
        if re.search(r"[\u4e00-\u9fff]", word):
            tokens.extend(word[i:i + 2] for i in range(max(1, len(word) - 1)))
        else:
            tokens.append(word)
    return tokens


def retrieve_sources(db: Session, chapter: Chapter, question: str, limit: int = 6) -> list[dict]:
    chapters = db.query(Chapter).filter(Chapter.textbook_id == chapter.textbook_id).order_by(Chapter.order).all()
    sources = [source for candidate in chapters for source in chapter_sources(candidate)]
    query = set(_tokens(question))
    if not sources or not query:
        return []
    documents = [Counter(_tokens(source["text"] + " " + source["chapter_title"])) for source in sources]
    frequencies = Counter(token for document in documents for token in document)
    average = sum(sum(document.values()) for document in documents) / len(documents) or 1
    ranked = []
    for source, document in zip(sources, documents):
        score = 0
        length = sum(document.values())
        for token in query & document.keys():
            frequency = document[token]
            idf = math.log(1 + (len(documents) - frequencies[token] + 0.5) / (frequencies[token] + 0.5))
            score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / average))
        if score:
            if source["chapter_id"] == chapter.id:
                score *= 1.2
            ranked.append((score, source))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [source for _, source in ranked[:limit]]
