import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from services import cited_qa, generator


class ModelOptionsTests(unittest.TestCase):
    def test_provider_default_is_preserved_and_opt_in_applies_to_every_request(self):
        with patch.object(generator.settings, "llm_reasoning_effort", ""):
            self.assertEqual(generator.model_options(), {})
        calls = []
        responses = iter([
            "完整讲解",
            json.dumps([{"question": "题目", "options": ["A", "B", "C", "D"], "answer": 0, "explanation": "解释"}]),
            json.dumps({"nodes": [{"id": "a", "label": "概念", "category": "definition"}, {"id": "b", "label": "方法", "category": "method"}], "edges": [{"source": "a", "target": "b", "label": "应用"}]}),
            json.dumps({"textbook_answer": "依据 [s]", "supplement": "", "evidence_ids": ["s"]}),
        ])
        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=next(responses)))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.object(generator.settings, "llm_reasoning_effort", "none"), patch.object(generator, "get_client", return_value=client), patch.object(cited_qa, "get_client", return_value=client):
            generator.generate_chapter_content("章", "原文")
            generator.generate_quiz("章", "讲解", num_questions=1)
            generator.generate_knowledge_graph("章", "讲解")
            cited_qa.answer_with_sources("问题", [], [{"id": "s", "chapter_title": "章", "location": "位置", "text": "依据"}])
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(call["reasoning_effort"] == "none" for call in calls))
