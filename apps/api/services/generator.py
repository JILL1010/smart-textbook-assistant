from openai import OpenAI
from datetime import datetime, timezone

from config import settings


def get_client() -> OpenAI | None:
    """Get OpenAI client if configured, otherwise None."""
    api_key = settings.llm_api_key
    if not api_key:
        return None
    return OpenAI(
        api_key=api_key,
        base_url=settings.llm_base_url or "https://api.openai.com/v1",
    )


SYSTEM_PROMPT = """你是一位经验丰富的教师，擅长将课本知识转化为生动易懂的讲解。

根据用户指定的难度和风格讲解，保持知识准确，例子与章节内容相关。

请使用 Markdown 格式输出，包含以下结构：
## 本节导入
## 核心概念讲解
## 例题分析
## 常见误区
## 本节要点速记"""

STYLE_HINTS = {
    "teacher": "采用教师讲解风格：逐步解释，使用生活化例子和引导语，强调重点并配例题。",
    "concise": "采用简洁概述风格：用短句和要点列表，保留关键定义、公式和一个简短例题，避免铺垫和重复。",
    "story": "采用故事引导风格：以一个连贯的生活场景引入，再把情节与概念逐一对应；故事不能替代准确的定义和推理。",
}


def chapter_segments(text: str, size: int = 6500) -> list[str]:
    """Cover every source character once, preferring paragraph boundaries."""
    parts, cursor = [], 0
    while cursor < len(text):
        end = min(cursor + size, len(text))
        if end < len(text):
            boundary = text.rfind("\n\n", cursor + size // 2, end)
            if boundary >= 0:
                end = boundary + 2
        parts.append(text[cursor:end])
        cursor = end
    return parts or [""]


def generation_metadata(text: str | None, difficulty: str, style: str) -> dict:
    return {"source_characters": len(text or ""), "parts": len(chapter_segments(text or "")),
            "difficulty": difficulty, "style": style, "mode": "ai" if settings.llm_api_key else "template",
            "created_at": datetime.now(timezone.utc).isoformat()}


def generate_chapter_content(chapter_title: str, chapter_text: str | None = None, difficulty: str = "medium", style: str = "teacher") -> str:
    parts = chapter_segments(chapter_text or "")
    if len(parts) > 40:
        raise RuntimeError("章节超过 40 个讲解片段，请先按小节导入；本次未生成或覆盖讲解")
    explanations = []
    for index, part in enumerate(parts, 1):
        title = chapter_title if len(parts) == 1 else f"{chapter_title}（第 {index}/{len(parts)} 部分，按原文顺序）"
        explanation = _generate_chapter_part(title, part, difficulty, style)
        explanations.append(explanation if len(parts) == 1 else f"# 第 {index} 部分 / 共 {len(parts)} 部分\n\n{explanation}")
    return "\n\n---\n\n".join(explanations)


def _generate_chapter_part(
    chapter_title: str,
    chapter_text: str | None = None,
    difficulty: str = "medium",
    style: str = "teacher",
) -> str:
    """
    Generate explanation content for a chapter using LLM.
    Falls back to template if no LLM configured.
    """
    client = get_client()

    if client is None:
        return _fallback_content(chapter_title, chapter_text)

    difficulty_hint = {
        "easy": "请用最浅显的语言讲解，适合零基础的初学者。",
        "medium": "请用适中的难度讲解，假设学习者有一定基础。",
        "hard": "请用较高难度讲解，引入更多推导和深度分析。",
    }.get(difficulty, "")

    style_hint = STYLE_HINTS[style]
    user_prompt = f"请讲解以下章节内容。\n\n章节标题：{chapter_title}\n{difficulty_hint}\n{style_hint}\n"

    if chapter_text:
        user_prompt += f"\n本部分原文（请覆盖其中各项知识，章节之间不要凭空补全）：\n{chapter_text}\n"

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        if getattr(response.choices[0], "finish_reason", None) == "length":
            raise RuntimeError("模型输出达到长度上限，本次讲解未保存，请调整输出设置后重试")
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError("模型未返回讲解，本次内容未保存")
        return content
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败: {e}") from e


def _fallback_content(title: str, text: str | None = None) -> str:
    """Generate template content when LLM is unavailable."""
    preview = ""
    if text:
        preview = text

    return f"""# {title}

> 当前为模板模式，以下保留本部分完整原文；没有生成 AI 讲解。

## 本节导入

同学们好！今天我们来学习"{title}"。在开始之前，大家可以先思考一个问题：这个知识点与我们日常生活中哪些场景有关？

{preview if preview else "（本章节原文将在此展示）"}

## 核心概念讲解

本节的核心知识点如下：

1. **基本概念** — 理解定义是学习的第一步
2. **原理分析** — 不仅要知道"是什么"，还要知道"为什么"
3. **应用场景** — 理论知识如何在实际中运用

## 例题分析

### 例题 1

> 此处将在接入 LLM 后自动生成针对性例题

## 常见误区

学习本节时，同学们容易在以下几个方面产生困惑：

- 概念混淆：注意区分相似概念
- 过度记忆：理解比死记硬背更重要

## 本节要点速记

- 核心定义要记牢
- 原理和应用两手抓
- 遇到问题善用对比分析

---
> 💡 提示：配置 LLM_API_KEY 后可获得 AI 生成的个性化讲解内容
"""


QUIZ_SYSTEM_PROMPT = """你是一位出题老师，需要根据章节内容生成高质量的选择题。

要求：
1. 题目必须覆盖章节的核心知识点
2. 每道题4个选项，仅1个正确答案
3. 错误选项要有迷惑性（常见误解或易混淆概念）
4. 解析要简洁明了，指出正确选项的推理过程

输出严格的 JSON 数组，不要有任何其他文字，格式如下：
[
  {
    "question": "题目内容",
    "options": ["A. 选项一", "B. 选项二", "C. 选项三", "D. 选项四"],
    "answer": 0,
    "explanation": "解题思路和答案分析"
  }
]

注意：answer 是正确选项的索引（0-3），从0开始计数。只输出 JSON 数组，不要用 ```json 包裹。"""


def generate_quiz(
    chapter_title: str,
    chapter_text: str,
    difficulty: str = "medium",
    num_questions: int = 5,
) -> list[dict]:
    """Process the full lecture and distribute the requested quiz across it."""
    if type(num_questions) is not int or not 1 <= num_questions <= 20:
        raise RuntimeError("练习题数量必须为 1 到 20")
    parts = _artifact_parts(chapter_text)
    questions = []
    for index, part in enumerate(parts):
        count = max(1, num_questions // len(parts) + (index < num_questions % len(parts)))
        title = f"{chapter_title}（讲解片段 {index + 1}/{len(parts)}）"
        batch = _generate_quiz_part(title, part, difficulty, count)
        if len(batch) != count:
            raise RuntimeError("模型返回的题目数量与要求不符，本次练习未保存，请重试")
        questions.extend({**question, "source_part": index + 1, "source_parts_total": len(parts)} for question in batch)
    if len(questions) > num_questions:
        # All parts were processed. A short quiz samples evenly, including the end.
        positions = [len(questions) // 2] if num_questions == 1 else [
            round(index * (len(questions) - 1) / (num_questions - 1)) for index in range(num_questions)
        ]
        questions = [questions[position] for position in positions]
    return questions


def _artifact_parts(text: str) -> list[str]:
    if not text.strip():
        raise RuntimeError("讲解内容为空，无法生成练习或图谱")
    parts = chapter_segments(text)
    if len(parts) > 40:
        raise RuntimeError("讲解超过 40 个片段，请先按小节导入；本次未生成或覆盖内容")
    return parts


def _generate_quiz_part(chapter_title: str, chapter_text: str, difficulty: str, num_questions: int) -> list[dict]:
    client = get_client()
    if client is None:
        raise RuntimeError("未配置 LLM API Key，无法生成练习题")

    difficulty_hint = {
        "easy": "请出基础概念题，适合零基础的初学者。",
        "medium": "请出适中的题目，包含理解和应用。",
        "hard": "请出高难度题目，包含分析和推导。",
    }.get(difficulty, "")

    user_prompt = f"""请根据以下章节内容生成 {num_questions} 道选择题。

章节标题：{chapter_title}
{difficulty_hint}

章节内容：
{chapter_text}

请严格按照 JSON 数组格式输出 {num_questions} 道题目。"""

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        if getattr(response.choices[0], "finish_reason", None) == "length":
            raise RuntimeError("模型题目输出达到长度上限，本次练习未保存")
        raw = response.choices[0].message.content or ""
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败: {e}") from e

    return _parse_quiz_json(raw)


def _parse_quiz_json(raw: str) -> list[dict]:
    """Parse LLM response into quiz list, with robust fallback parsing."""
    import json as _json
    import re

    # Strip markdown code fences
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    # Try direct parse
    try:
        result = _json.loads(cleaned)
        if isinstance(result, list):
            return _validate_quiz(result)
    except _json.JSONDecodeError:
        pass

    # Try to extract JSON array with regex
    m = re.search(r"\[[\s\S]*\]", cleaned)
    if m:
        try:
            result = _json.loads(m.group())
            if isinstance(result, list):
                return _validate_quiz(result)
        except _json.JSONDecodeError:
            pass

    raise RuntimeError("无法解析 LLM 返回的练习题数据")


def _validate_quiz(quiz: list) -> list[dict]:
    """Validate and normalize quiz structure."""
    validated = []
    for i, q in enumerate(quiz):
        if not isinstance(q, dict):
            continue
        question = q.get("question", "")
        options = q.get("options", [])
        answer = q.get("answer")
        explanation = q.get("explanation", "")

        if not isinstance(question, str) or not question.strip() or not isinstance(options, list) or len(options) != 4 or any(not isinstance(option, str) or not option.strip() for option in options):
            continue
        if type(answer) is not int or answer < 0 or answer > 3 or not isinstance(explanation, str):
            continue

        validated.append({
            "question": question,
            "options": options,
            "answer": answer,
            "explanation": explanation,
        })

    if not validated:
        raise RuntimeError("LLM 未返回有效的练习题数据")

    return validated


KNOWLEDGE_GRAPH_PROMPT = """你是一位知识图谱构建专家，需要从章节内容中提取关键概念及其关系。

要求：
1. 提取 8-20 个关键概念作为节点（nodes）
2. 每个节点：id（英文简短标识符）、label（中文名称）、category（类别）
3. category 必须是以下之一："definition"（定义）、"theorem"（定理/公式）、"method"（方法/技巧）、"application"（应用/例子）
4. 提取概念之间的关系作为边（edges）
5. 每条边：source（源节点id）、target（目标节点id）、relation（关系类型）
6. relation 必须是以下之一："prerequisite"（前置知识）、"generalization"（泛化/推广）、"application"（应用）、"related"（相关）

输出严格的 JSON 对象，不要有任何其他文字：
{"nodes": [{"id": "...", "label": "...", "category": "..."}], "edges": [{"source": "...", "target": "...", "relation": "..."}]}"""


def generate_knowledge_graph(
    chapter_title: str,
    chapter_text: str,
) -> dict:
    """Extract every lecture part and merge identical concept labels/categories."""
    parts = _artifact_parts(chapter_text)
    nodes, edges, concepts, seen_edges = [], [], {}, set()
    for index, part in enumerate(parts, 1):
        graph = _generate_graph_part(f"{chapter_title}（讲解片段 {index}/{len(parts)}）", part)
        mapping = {}
        for node in graph["nodes"]:
            key = (" ".join(node["label"].split()), node["category"])
            if key not in concepts:
                merged = {**node, "id": f"concept-{len(nodes) + 1}", "source_parts": [index]}
                concepts[key] = merged
                nodes.append(merged)
            else:
                merged = concepts[key]
                if index not in merged["source_parts"]:
                    merged["source_parts"].append(index)
            mapping[node["id"]] = merged["id"]
        for edge in graph["edges"]:
            source, target = mapping[edge["source"]], mapping[edge["target"]]
            key = (source, target, edge["relation"])
            if source != target and key not in seen_edges:
                edges.append({**edge, "source": source, "target": target})
                seen_edges.add(key)
    return {"nodes": nodes, "edges": edges, "coverage": {"source_characters": len(chapter_text), "parts": len(parts)}}


def _generate_graph_part(chapter_title: str, chapter_text: str) -> dict:
    client = get_client()
    if client is None:
        raise RuntimeError("未配置 LLM API Key，无法生成知识图谱")

    user_prompt = f"""请从以下章节内容中提取关键概念和关系，构建知识图谱。

章节标题：{chapter_title}

章节内容：
{chapter_text}

请严格按照 JSON 格式输出，仅输出 JSON 对象。"""

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": KNOWLEDGE_GRAPH_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        if getattr(response.choices[0], "finish_reason", None) == "length":
            raise RuntimeError("模型图谱输出达到长度上限，本次图谱未保存")
        raw = response.choices[0].message.content or ""
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败: {e}") from e

    return _parse_graph_json(raw)


def _parse_graph_json(raw: str) -> dict:
    """Parse LLM response into graph dict, with robust fallback parsing."""
    import json as _json
    import re

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        result = _json.loads(cleaned)
        if isinstance(result, dict):
            return _validate_graph(result)
    except _json.JSONDecodeError:
        pass

    m = re.search(r"\{[\s\S]*\}", cleaned)
    if m:
        try:
            result = _json.loads(m.group())
            if isinstance(result, dict):
                return _validate_graph(result)
        except _json.JSONDecodeError:
            pass

    raise RuntimeError("无法解析 LLM 返回的知识图谱数据")


def _validate_graph(graph: dict) -> dict:
    """Validate and normalize graph structure."""
    VALID_CATEGORIES = {"definition", "theorem", "method", "application"}
    VALID_RELATIONS = {"prerequisite", "generalization", "application", "related"}

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise RuntimeError("知识图谱数据格式无效")

    # Deduplicate nodes by id
    seen_ids: set[str] = set()
    valid_nodes = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id", "")
        label = n.get("label", "")
        category = n.get("category", "")
        if not isinstance(nid, str) or not nid.strip() or not isinstance(label, str) or not label.strip():
            continue
        if nid in seen_ids:
            continue
        if not isinstance(category, str) or category not in VALID_CATEGORIES:
            category = "definition"
        seen_ids.add(nid)
        valid_nodes.append({"id": nid, "label": label, "category": category})

    if len(valid_nodes) < 2:
        raise RuntimeError("提取的概念数量不足（至少需要2个）")

    # Filter edges to only valid node references, deduplicate
    seen_edges: set[tuple] = set()
    valid_edges = []
    for e in edges:
        if not isinstance(e, dict):
            continue
        src = e.get("source", "")
        tgt = e.get("target", "")
        rel = e.get("relation", "")
        if not isinstance(src, str) or not isinstance(tgt, str) or not src or not tgt:
            continue
        if src not in seen_ids or tgt not in seen_ids:
            continue
        if not isinstance(rel, str) or rel not in VALID_RELATIONS:
            rel = "related"
        key = (src, tgt, rel)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        valid_edges.append({"source": src, "target": tgt, "relation": rel})

    return {"nodes": valid_nodes, "edges": valid_edges}

