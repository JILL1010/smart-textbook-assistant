"""Opt-in live evaluation. The original database is opened read-only and copied."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--database", type=Path, required=True)
parser.add_argument("--uploads", type=Path, required=True)
parser.add_argument("--chapter-id", type=int, required=True)
parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--live", action="store_true", help="Allow model API calls and associated costs")
args = parser.parse_args()
if not args.live:
    parser.error("Pass --live explicitly to allow model calls")
root = Path(__file__).resolve().parents[3]
output = args.output.resolve()
if not output.is_relative_to((root / "data" / "evaluation").resolve()):
    parser.error("Output must be under this project's ignored data/evaluation/")
output.mkdir(parents=True, exist_ok=False)
original = args.database.resolve()
before = hashlib.sha256(original.read_bytes()).hexdigest()
copy = output / "snapshot.db"
with sqlite3.connect(original.as_uri() + "?mode=ro", uri=True) as source, sqlite3.connect(copy) as destination:
    source.backup(destination)
os.environ["DATABASE_URL"] = "sqlite:///" + copy.as_posix()
os.environ["UPLOAD_DIR"] = str(args.uploads.resolve())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import init_db, SessionLocal
from models.chapter import Chapter
from services.retrieval import retrieve_sources
from services.cited_qa import answer_with_sources
from services import generator
from config import settings

init_db()
if not settings.llm_api_key or "your-key" in settings.llm_api_key:
    parser.error("Configure a real LLM_API_KEY before live evaluation")
record = {"created_at": datetime.now(timezone.utc).isoformat(), "model": settings.llm_model,
          "settings": {"max_tokens": settings.llm_max_tokens, "timeout_seconds": settings.llm_timeout_seconds,
                       "reasoning_effort": settings.llm_reasoning_effort or "provider_default"},
          "chapter_id": args.chapter_id, "questions": [], "lectures": [], "quiz": None,
          "manual_review": "pending; keyword hits do not measure answer correctness"}

def save():
    (output / "results.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

with SessionLocal() as db:
    chapter = db.get(Chapter, args.chapter_id)
    if not chapter:
        parser.error("Chapter does not exist")
    record["source_characters"] = len(chapter.content or "")
    for case in json.loads(args.cases.read_text(encoding="utf-8")):
        evidence = retrieve_sources(db, chapter, case["question"])
        hit = any(term.casefold() in item["text"].casefold() for term in case["evidence_terms"] for item in evidence)
        result = {**case, "retrieval_keyword_hit": hit, "retrieved_sources": evidence,
                  "support_verified": None, "answer_correct": None}
        try:
            result.update(answer_with_sources(case["question"], [], evidence))
        except Exception as error:
            result.update(status="error", error_type=type(error).__name__,
                          cause_type=type(error.__cause__).__name__ if error.__cause__ else None)
        record["questions"].append(result)
        save()
        print(case["id"], result["status"], "keyword_hit=" + str(hit), flush=True)
    source = chapter.content or ""
    # Inspect teaching quality at three locations; this is explicitly excerpt evaluation.
    for number, start in enumerate([0, max(0, len(source)//2 - 600), max(0, len(source) - 1200)], 1):
        excerpt = source[start:start + 1200]
        result = {"part": number, "offset": start, "source": excerpt, "completeness_verified": None}
        try:
            result["content"] = generator.generate_chapter_content(f"教材验收节选 {number}", excerpt, "medium", "concise")
        except Exception as error:
            result.update(error_type=type(error).__name__, cause_type=type(error.__cause__).__name__ if error.__cause__ else None)
        record["lectures"].append(result)
        save()
        print("lecture-excerpt", number, "ok=" + str("content" in result), flush=True)
    lecture = "\n\n".join(item.get("content", "") for item in record["lectures"])
    if lecture:
        try:
            record["quiz"] = {"questions": generator.generate_quiz("真实教材节选验收", lecture, num_questions=10),
                              "unique_correct_answers_verified": None}
        except Exception as error:
            record["quiz"] = {"error_type": type(error).__name__, "cause_type": type(error.__cause__).__name__ if error.__cause__ else None}
    record["original_database_unchanged"] = before == hashlib.sha256(original.read_bytes()).hexdigest()
    save()
    print("Saved private evaluation results:", output, flush=True)
