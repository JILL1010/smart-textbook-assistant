"""Disposable browser-test API. All AI responses and audio are local fixtures."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, required=True)
args = parser.parse_args()

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    os.environ.update({
        "DATABASE_URL": f"sqlite:///{root.as_posix()}/app.db",
        "UPLOAD_DIR": str(root / "uploads"),
        "AUDIO_DIR": str(root / "audio"),
        "LLM_API_KEY": "",
        "MAX_UPLOAD_SIZE_MB": "1",
    })
    import uvicorn
    from db import init_db, SessionLocal
    from main import app
    from models.textbook import Textbook
    from models.chapter import Chapter
    from routers import tts
    from services import generator
    import fitz

    root.joinpath("audio").mkdir()
    root.joinpath("uploads").mkdir()
    with fitz.open() as pdf:
        for text in ["Chapter one", "End of chapter one", "Chapter two"]:
            pdf.new_page().insert_text((72, 72), text)
        pdf.save(root / "uploads" / "fixture.pdf")
    root.joinpath("audio", "saved.mp3").write_bytes(b"mock-audio")
    subtitles = [{"start": 0, "end": 1, "text": "已保存的字幕"}]
    root.joinpath("audio", "saved.json").write_text(json.dumps(subtitles), encoding="utf-8")
    questions = [{"question": "测试选择题", "options": ["A", "B", "C", "D"], "answer": 0, "explanation": "测试解析"}]
    graph = {
        "nodes": [
            {"id": "definition", "label": "测试定义", "category": "definition"},
            {"id": "method", "label": "测试方法", "category": "method"},
        ],
        "edges": [{"source": "definition", "target": "method", "relation": "prerequisite"}],
    }
    init_db()
    with SessionLocal() as session:
        book = Textbook(title="浏览器测试教材", filename="fixture.pdf")
        session.add(book)
        session.flush()
        session.add_all([
            Chapter(textbook_id=book.id, title="第一章", order=1, content="第一章原文。" * 1200 + "\n\n整章末尾知识", source_data=json.dumps([{"page": 1, "text": "第一章原文。" * 1200}, {"page": 2, "text": "整章末尾知识"}]), generated_content="## 已保存的讲解", audio_filename="saved.mp3", quiz_data=json.dumps(questions), knowledge_graph_data=json.dumps(graph)),
            Chapter(textbook_id=book.id, title="第二章", order=2, content="跨章检索概念是本章独有的定义。", source_data=json.dumps([{"page": 3, "text": "跨章检索概念是本章独有的定义。"}]), generated_content="## 第二章讲解"),
        ])
        session.commit()

    def explain(title, text, difficulty, style):
        time.sleep(2)
        tail = "\n\n整章末尾知识" if "整章末尾知识" in text else ""
        return f"## 新讲解\n\n风格：{style}；难度：{difficulty}\n\n" + "示例内容。" * 900 + tail

    def quiz_part(title, text, difficulty, count):
        label = "末尾知识练习" if "整章末尾知识" in text else "前段知识练习"
        return [{**questions[0], "question": f"{label} {index + 1}"} for index in range(count)]

    def graph_part(title, text):
        label = "末尾方法" if "整章末尾知识" in text else "前段方法"
        return {"nodes": [{**graph["nodes"][0]}, {**graph["nodes"][1], "label": label}], "edges": [dict(graph["edges"][0])]}

    async def audio(content, output):
        Path(output).write_bytes(b"mock-audio")
        Path(output).with_suffix(".json").write_text(json.dumps(subtitles), encoding="utf-8")
        return output, subtitles

    generator._generate_chapter_part = explain
    tts.generate_audio = audio
    generator._generate_quiz_part = quiz_part
    generator._generate_graph_part = graph_part
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
