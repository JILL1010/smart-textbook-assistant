import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_reliability as reliability
import fitz
from models.chapter import Chapter
from models.textbook import Textbook
from services import cited_qa
from services import generator
from services.learning import quiz_token
from services.retrieval import chapter_sources, retrieve_sources


class LearningFeatureTests(unittest.TestCase):
    setUp = reliability.APIReliabilityTests.setUp
    tearDown = reliability.APIReliabilityTests.tearDown
    chapter = reliability.APIReliabilityTests.chapter

    def test_retrieval_reaches_late_content_and_other_chapters_only_in_same_book(self):
        with self.sessions() as db:
            chapter = db.get(Chapter, self.chapter_id)
            chapter.content = "普通内容。" * 2000 + "光合作用将光能转化为化学能。"
            chapter.source_data = json.dumps([{"text": chapter.content, "page": 9}])
            db.add(Chapter(textbook_id=self.book_id, title="前置知识", order=2, content="叶绿体包含叶绿素。", source_data=json.dumps([{"text": "叶绿体包含叶绿素。", "page": 2}])))
            other = Textbook(title="其他教材", filename="other.pdf")
            db.add(other)
            db.flush()
            db.add(Chapter(textbook_id=other.id, title="隔离", order=1, content="隔离秘密术语内容"))
            db.commit()
            late = retrieve_sources(db, chapter, "光合作用")
            self.assertIn("光合作用", late[0]["text"])
            self.assertEqual(late[0]["page"], 9)
            cross = retrieve_sources(db, chapter, "叶绿体")
            self.assertEqual(cross[0]["chapter_title"], "前置知识")
            self.assertEqual(retrieve_sources(db, chapter, "隔离秘密术语"), [])

    def test_source_link_is_stable_and_book_scoped(self):
        with self.sessions() as db:
            source = chapter_sources(db.get(Chapter, self.chapter_id))[0]
        response = self.client.get(self.path + "/sources/" + source["id"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "原文内容")
        self.assertIsNone(response.json()["page"])
        self.assertEqual(self.client.get(f"/api/textbooks/999/chapters/{self.chapter_id}/sources/{source['id']}").status_code, 404)

    def test_legacy_pdf_recovers_real_file_page(self):
        self.uploads.mkdir(exist_ok=True)
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), "Introduction")
            document.new_page().insert_text((72, 72), "Unique photosynthesis evidence")
            content = document[1].get_text().strip()
            document.save(self.uploads / "source.pdf")
        with self.sessions() as db:
            chapter = db.get(Chapter, self.chapter_id)
            chapter.content = content
            db.commit()
            self.assertEqual(chapter_sources(chapter)[0]["page"], 2)

    def test_answer_separates_supplement_and_rejects_invented_citations(self):
        source = {"id": "valid", "chapter_title": "前置章节", "location": "PDF 第 2 页", "text": "教材原文"}
        def client_for(result):
            return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))]))))
        with patch.object(cited_qa, "get_client", return_value=client_for({"textbook_answer": "教材回答 [valid]", "supplement": "额外的例子", "evidence_ids": ["valid"]})):
            result = cited_qa.answer_with_sources("问题", [], [source])
            self.assertIn("## 补充说明", result["answer"])
            self.assertEqual(result["citations"], [source])
        with patch.object(cited_qa, "get_client", return_value=client_for({"textbook_answer": "伪造", "supplement": "", "evidence_ids": ["invented"]})):
            with self.assertRaises(RuntimeError):
                cited_qa.answer_with_sources("问题", [], [source])
        with patch.object(cited_qa, "get_client", return_value=client_for({"textbook_answer": "没有来源的断言", "supplement": "有标注的补充", "evidence_ids": []})):
            result = cited_qa.answer_with_sources("问题", [], [])
            self.assertEqual(result["status"], "insufficient_evidence")
            self.assertNotIn("没有来源的断言", result["answer"])

    def test_unconfigured_model_is_explicit_retrieval_mode(self):
        response = self.client.post(self.path + "/ask", json={"question": "原文内容"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "retrieval_only")
        self.assertTrue(response.json()["citations"])

    def set_valid_quiz(self):
        questions = [{"question": "第一题", "options": ["A", "B", "C", "D"], "answer": 0, "explanation": "A 正确"},
                     {"question": "第二题", "options": ["A", "B", "C", "D"], "answer": 1, "explanation": "B 正确"}]
        with self.sessions() as db:
            chapter = db.get(Chapter, self.chapter_id)
            chapter.quiz_data = json.dumps(questions)
            db.commit()
        return quiz_token(json.dumps(questions))

    def test_drafts_read_status_and_server_scores_persist(self):
        token = self.set_valid_quiz()
        response = self.client.post(self.path + "/quiz/draft", json={"quiz_token": token, "answers": {"0": 2}, "sequence": 10})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(self.path + "/learning").json()["draft"]["answers"], {"0": 2})
        self.client.post(self.path + "/quiz/draft", json={"quiz_token": token, "answers": {"0": 1}, "sequence": 9})
        self.assertEqual(self.client.get(self.path + "/learning").json()["draft"]["answers"], {"0": 2})
        self.client.post(self.path + "/learning/read", json={"read_completed": True})
        response = self.client.post(self.path + "/quiz/submit", json={"quiz_token": token, "answers": [2, 1], "sequence": 11})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["correct"], 1)
        summary = self.client.get(self.path + "/learning").json()
        self.assertTrue(summary["read_completed"])
        self.assertIsNone(summary["draft"])
        self.assertEqual(summary["current_attempt"]["answers"], [2, 1])
        self.assertEqual(summary["pending_reviews"], 1)
        self.client.post(self.path + "/quiz/draft", json={"quiz_token": token, "answers": {"0": 2}, "sequence": 10})
        self.assertIsNone(self.client.get(self.path + "/learning").json()["draft"])

    def test_old_wrong_questions_survive_regeneration_and_can_be_reviewed(self):
        token = self.set_valid_quiz()
        self.client.post(self.path + "/quiz/submit", json={"quiz_token": token, "answers": [3, 1], "sequence": 2})
        with patch("routers.generation.generate_chapter_content", return_value="新版讲解"):
            self.client.post(self.path + "/generate", json={})
        summary = self.client.get(self.path + "/learning").json()
        self.assertIsNone(summary["current_attempt"])
        self.assertEqual(len(summary["attempts"]), 1)
        reviews = self.client.get(f"/api/textbooks/{self.book_id}/reviews").json()
        self.assertEqual(reviews[0]["question"]["question"], "第一题")
        result = self.client.post(f"/api/textbooks/{self.book_id}/reviews/{reviews[0]['id']}", json={"answer": 0})
        self.assertTrue(result.json()["correct"])
        self.assertEqual(self.client.get(self.path + "/learning").json()["pending_reviews"], 0)
        stale = self.client.post(self.path + "/quiz/submit", json={"quiz_token": token, "answers": [0, 1]})
        self.assertEqual(stale.status_code, 409)

    def test_submit_validates_answers_and_cannot_access_other_book_reviews(self):
        token = self.set_valid_quiz()
        self.assertEqual(self.client.post(self.path + "/quiz/submit", json={"quiz_token": token, "answers": [9, 1]}).status_code, 400)
        self.client.post(self.path + "/quiz/submit", json={"quiz_token": token, "answers": [3, 1]})
        review = self.client.get(f"/api/textbooks/{self.book_id}/reviews").json()[0]
        self.assertEqual(self.client.post(f"/api/textbooks/999/reviews/{review['id']}", json={"answer": 0}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/textbooks/{self.book_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/textbooks/{self.book_id}/reviews").json(), [])

    def test_complete_lecture_processes_every_segment_and_does_not_save_partial_output(self):
        source = "开头内容。" * 1500 + "\n\n末尾独有知识光合作用。" * 500
        self.assertEqual("".join(generator.chapter_segments(source)), source)
        calls = []
        def part(title, text, difficulty, style):
            calls.append(text)
            return "讲解：" + text[-40:]
        with patch.object(generator, "_generate_chapter_part", side_effect=part):
            result = generator.generate_chapter_content("整章", source, "hard", "story")
        self.assertEqual("".join(calls), source)
        self.assertIn("末尾独有知识光合作用", result)
        self.assertGreater(len(calls), 1)
        with self.sessions() as db:
            chapter = db.get(Chapter, self.chapter_id)
            chapter.content = source
            db.commit()
        with patch.object(generator, "_generate_chapter_part", side_effect=["第一部分", RuntimeError("第二部分失败")]):
            response = self.client.post(self.path + "/generate", json={})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.chapter()["generated_content"], "旧讲解")

    def test_template_mode_keeps_late_text_and_invalid_quiz_answers_are_rejected(self):
        source = "普通内容" * 2000 + "最后的独有内容"
        result = generator.generate_chapter_content("整章", source)
        self.assertIn("最后的独有内容", result)
        self.assertIn("模板模式", result)
        with self.assertRaises(RuntimeError):
            generator._validate_quiz([{"question": "题", "options": ["A", "B", "C", "D"], "answer": 99}])
