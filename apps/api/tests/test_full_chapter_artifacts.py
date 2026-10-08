"""Full lecture processing, graph merging, and atomic artifact replacement."""
import json
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_reliability as reliability
from models.chapter import Chapter
from services import generator


def model_response(value, finish_reason="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=json.dumps(value, ensure_ascii=False)), finish_reason=finish_reason,
    )])


def model_client(create):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def question(text="题目"):
    return {"question": text, "options": ["A", "B", "C", "D"], "answer": 0, "explanation": "解析"}


class FullChapterArtifactTests(unittest.TestCase):
    setUp = reliability.APIReliabilityTests.setUp
    tearDown = reliability.APIReliabilityTests.tearDown
    chapter = reliability.APIReliabilityTests.chapter

    def test_quiz_sends_every_character_and_distributes_requested_count(self):
        source = "首" * 6500 + "中" * 6500 + "末尾的独有知识"
        received = []

        def create(**kwargs):
            prompt = kwargs["messages"][-1]["content"]
            text = prompt.split("章节内容：\n", 1)[1].rsplit("\n\n请严格", 1)[0]
            received.append(text)
            count = int(re.search(r"生成 (\d+) 道选择题", prompt).group(1))
            return model_response([question(text[-12:] + str(index)) for index in range(count)])

        with patch.object(generator, "get_client", return_value=model_client(create)):
            quiz = generator.generate_quiz("整章", source, num_questions=5)
        self.assertEqual("".join(received), source)
        self.assertEqual(len(quiz), 5)
        self.assertEqual([item["source_part"] for item in quiz], [1, 1, 2, 2, 3])
        self.assertTrue(all(item["source_parts_total"] == 3 for item in quiz))
        self.assertIn("末尾的独有知识", quiz[-1]["question"])

    def test_short_quiz_processes_all_parts_and_samples_front_and_end(self):
        received = []

        def generate(title, text, difficulty, count):
            received.append(text)
            return [question(title) for _ in range(count)]

        source = "原" * (6500 * 4)
        with patch.object(generator, "_generate_quiz_part", side_effect=generate):
            quiz = generator.generate_quiz("整章", source, num_questions=2)
        self.assertEqual("".join(received), source)
        self.assertEqual([item["source_part"] for item in quiz], [1, 4])
        with patch.object(generator, "_generate_quiz_part", side_effect=generate):
            self.assertEqual(len(generator.generate_quiz("整章", source, num_questions=1)), 1)

    def test_graph_preserves_late_nodes_and_maps_colliding_local_ids(self):
        source = "首" * 6500 + "中" * 6500 + "末尾概念"
        received = []

        def create(**kwargs):
            prompt = kwargs["messages"][-1]["content"]
            text = prompt.split("章节内容：\n", 1)[1].rsplit("\n\n请严格", 1)[0]
            received.append(text)
            return model_response({
                "nodes": [{"id": "same", "label": "共同概念", "category": "definition"},
                          {"id": "local", "label": text[-6:], "category": "method"}],
                "edges": [{"source": "same", "target": "local", "relation": "application"}],
            })

        with patch.object(generator, "get_client", return_value=model_client(create)):
            graph = generator.generate_knowledge_graph("整章", source)
        self.assertEqual("".join(received), source)
        self.assertEqual(graph["coverage"], {"parts": 3, "source_characters": len(source)})
        self.assertEqual(len(graph["nodes"]), 4)
        common = next(node for node in graph["nodes"] if node["label"] == "共同概念")
        self.assertEqual(common["source_parts"], [1, 2, 3])
        self.assertIn("末尾概念", [node["label"] for node in graph["nodes"]])
        self.assertEqual(len(graph["edges"]), 3)
        node_ids = {node["id"] for node in graph["nodes"]}
        self.assertTrue(all(edge["source"] == common["id"] and edge["target"] in node_ids for edge in graph["edges"]))

    def test_partial_failures_preserve_saved_quiz_and_graph(self):
        with self.sessions() as db:
            db.get(Chapter, self.chapter_id).generated_content = "讲" * 13000
            db.commit()
        before = self.chapter()
        graph = {"nodes": [{"id": "a", "label": "A", "category": "definition"},
                           {"id": "b", "label": "B", "category": "method"}], "edges": []}
        with patch.object(generator, "_generate_quiz_part", side_effect=[[question() for _ in range(3)], RuntimeError("第二段失败")]):
            self.assertEqual(self.client.post(self.path + "/quiz", json={}).status_code, 500)
        with patch.object(generator, "_generate_graph_part", side_effect=[graph, RuntimeError("第二段失败")]):
            self.assertEqual(self.client.post(self.path + "/knowledge-graph").status_code, 500)
        after = self.chapter()
        self.assertEqual(after["quiz_data"], before["quiz_data"])
        self.assertEqual(after["knowledge_graph_data"], before["knowledge_graph_data"])

    def test_graph_keeps_case_sensitive_labels_and_distinct_categories(self):
        for label, category in [("x", "definition"), ("X", "theorem")]:
            with self.subTest(label=label, category=category):
                graphs = [{"nodes": [{"id": "local", "label": "X", "category": "definition"}], "edges": []},
                          {"nodes": [{"id": "local", "label": label, "category": category}], "edges": []}]
                with patch.object(generator, "_generate_graph_part", side_effect=graphs):
                    graph = generator.generate_knowledge_graph("章", "正文" * 6500)
                self.assertEqual(len(graph["nodes"]), 2)
                self.assertEqual([node["source_parts"] for node in graph["nodes"]], [[1], [2]])

    def test_invalid_counts_missing_answers_and_truncated_output_fail_explicitly(self):
        with patch.object(generator, "_generate_quiz_part", return_value=[question()]):
            with self.assertRaisesRegex(RuntimeError, "数量"):
                generator.generate_quiz("章", "正文", num_questions=5)
        invalid = question()
        del invalid["answer"]
        with self.assertRaises(RuntimeError):
            generator._validate_quiz([invalid])
        for generate, value in [(lambda: generator.generate_quiz("章", "正文"), [question()]),
                                (lambda: generator.generate_knowledge_graph("章", "正文"), {})]:
            with patch.object(generator, "get_client", return_value=model_client(lambda **kwargs: model_response(value, "length"))):
                with self.assertRaisesRegex(RuntimeError, "长度上限"):
                    generate()

    def test_limits_and_api_validation_reject_before_model_requests(self):
        with patch.object(generator, "get_client") as client:
            for body in [{"num_questions": 0}, {"num_questions": 21}, {"difficulty": "unknown"}, {"style": "unknown"}]:
                self.assertEqual(self.client.post(self.path + "/quiz", json=body).status_code, 422)
            for source in ["", "原" * (6500 * 40 + 1)]:
                with self.assertRaises(RuntimeError):
                    generator.generate_quiz("章", source)
                with self.assertRaises(RuntimeError):
                    generator.generate_knowledge_graph("章", source)
            client.assert_not_called()

    def test_graph_parser_handles_invalid_types_without_type_errors(self):
        result = generator._validate_graph({"nodes": [
            {"id": [], "label": "无效"},
            {"id": "a", "label": "A", "category": []},
            {"id": "b", "label": "B", "category": "method"},
        ], "edges": [{"source": [], "target": "b"}, {"source": "a", "target": "b", "relation": []}]})
        self.assertEqual(len(result["nodes"]), 2)
        self.assertEqual(result["edges"][0]["relation"], "related")
