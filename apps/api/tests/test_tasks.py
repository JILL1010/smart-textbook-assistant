import json
from threading import Event
import time
import unittest
from unittest.mock import patch

import test_reliability as reliability
from main import app
from models.chapter import Chapter
from models.generation_task import GenerationTask
from services import generator
from services.tasks import TaskManager, get_manager


class TaskTests(unittest.TestCase):
    def setUp(self):
        reliability.APIReliabilityTests.setUp(self)
        self.manager = TaskManager(self.sessions)
        app.dependency_overrides[get_manager] = lambda: self.manager
        self.started, self.release = Event(), Event()

    def tearDown(self):
        self.release.set()
        self.manager.executor.shutdown(wait=True)
        reliability.APIReliabilityTests.tearDown(self)

    def wait_task(self, task_id, terminal=True):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            values = self.client.get(self.path + "/tasks").json()
            task = next(value for value in values if value["id"] == task_id)
            if not terminal or task["status"] not in ("queued", "running"):
                return task
            time.sleep(0.02)
        self.fail("Task did not finish")

    def start(self, kind="lecture", **parameters):
        result = self.client.post(self.path + "/tasks", json={"kind": kind, **parameters})
        self.assertEqual(result.status_code, 202, result.text)
        return result.json()

    def blocking_part(self, *args):
        self.started.set()
        if not self.release.wait(5):
            raise RuntimeError("test wait expired")
        return "新讲解"

    def test_acknowledgement_deduplication_progress_and_cancel_preserve_old_content(self):
        with self.sessions() as db:
            db.get(Chapter, self.chapter_id).content = "原" * 13000
            db.commit()
        with patch.object(generator, "_generate_chapter_part", side_effect=self.blocking_part) as model:
            task = self.start()
            self.assertTrue(self.started.wait(2))
            duplicate = self.start(style="story")
            self.assertEqual(duplicate["id"], task["id"])
            progress = self.wait_task(task["id"], terminal=False)
            self.assertEqual(progress["total_parts"], 2)
            self.assertEqual(progress["completed_parts"], 0)
            self.assertEqual(self.client.post(self.path + "/tasks", json={"kind": "quiz"}).status_code, 409)
            self.assertEqual(self.client.post(self.path + "/generate", json={}).status_code, 409)
            self.client.post(self.path + f"/tasks/{task['id']}/cancel")
            self.release.set()
            self.assertEqual(self.wait_task(task["id"])["status"], "cancelled")
            self.assertEqual(model.call_count, 1)
        self.assertEqual(self.client.get(self.path).json()["generated_content"], "旧讲解")

    def test_failure_records_part_and_retry_publishes_only_complete_result(self):
        with self.sessions() as db:
            db.get(Chapter, self.chapter_id).content = "原" * 13000
            db.commit()
        with patch.object(generator, "_generate_chapter_part", side_effect=["第一段", RuntimeError("secret request details")]):
            task = self.start()
            failed = self.wait_task(task["id"])
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["completed_parts"], 1)
            self.assertNotIn("secret request", failed["error"])
        self.assertEqual(self.client.get(self.path).json()["generated_content"], "旧讲解")
        with patch.object(generator, "_generate_chapter_part", return_value="重试成功"):
            retry = self.client.post(self.path + f"/tasks/{task['id']}/retry")
            self.assertEqual(retry.status_code, 202)
            self.assertNotEqual(retry.json()["id"], task["id"])
            self.assertEqual(self.wait_task(retry.json()["id"])["status"], "succeeded")
        saved = self.client.get(self.path).json()
        self.assertIn("重试成功", saved["generated_content"])
        self.assertIsNone(saved["quiz_data"])
        self.assertIsNone(saved["audio_filename"])

    def test_revision_conflict_and_deletion_prevent_late_publication(self):
        with patch.object(generator, "_generate_chapter_part", side_effect=self.blocking_part):
            task = self.start()
            self.assertTrue(self.started.wait(2))
            with self.sessions() as db:
                chapter = db.get(Chapter, self.chapter_id)
                chapter.generation_revision += 1
                chapter.generated_content = "另一个版本"
                db.commit()
            self.release.set()
            self.assertEqual(self.wait_task(task["id"])["status"], "failed")
        self.assertEqual(self.client.get(self.path).json()["generated_content"], "另一个版本")
        self.assertEqual(self.client.post(self.path + f"/tasks/{task['id']}/retry").status_code, 409)
        self.started.clear()
        self.release.clear()
        with patch.object(generator, "_generate_chapter_part", side_effect=self.blocking_part):
            self.start()
            self.assertTrue(self.started.wait(2))
            self.assertEqual(self.client.delete(f"/api/textbooks/{self.book_id}").status_code, 200)
            self.release.set()
            self.manager.executor.shutdown(wait=True)
        with self.sessions() as db:
            self.assertEqual(db.query(GenerationTask).count(), 0)

    def test_recovery_marks_interrupted_and_scope_is_enforced(self):
        with patch.object(self.manager.executor, "submit"):
            task = self.start()
        self.manager.recover()
        self.assertEqual(self.wait_task(task["id"])["status"], "interrupted")
        self.assertEqual(self.client.get(f"/api/textbooks/999/chapters/{self.chapter_id}/tasks").status_code, 404)
        self.assertEqual(self.client.post(self.path + "/tasks", json={"kind": "quiz", "num_questions": 21}).status_code, 422)
        with patch.object(generator, "_generate_chapter_part", return_value="恢复后重新开始"):
            retry = self.client.post(self.path + f"/tasks/{task['id']}/retry")
            self.assertEqual(self.wait_task(retry.json()["id"])["status"], "succeeded")

    def test_quiz_and_graph_tasks_save_coverage_and_preserve_old_attempts(self):
        questions = [{"question": "练习", "options": ["A", "B", "C", "D"], "answer": 1, "explanation": "解析"} for _ in range(5)]
        with patch.object(generator, "_generate_quiz_part", return_value=questions):
            task = self.start("quiz")
            self.assertEqual(self.wait_task(task["id"])["status"], "succeeded")
        saved = self.client.get(self.path).json()
        self.client.post(self.path + "/quiz/submit", json={"quiz_token": saved["quiz_token"], "answers": [0] * 5})
        graph = {"nodes": [{"id": "a", "label": "A", "category": "definition"}, {"id": "b", "label": "B", "category": "method"}], "edges": []}
        with patch.object(generator, "_generate_graph_part", return_value=graph):
            task = self.start("graph")
            self.assertEqual(self.wait_task(task["id"])["status"], "succeeded")
        saved = self.client.get(self.path).json()
        self.assertEqual(json.loads(saved["knowledge_graph_data"])["coverage"]["parts"], 1)
        self.assertEqual(len(self.client.get(self.path + "/learning").json()["attempts"]), 1)
