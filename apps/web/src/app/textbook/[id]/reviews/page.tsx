"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { listReviews, reviewQuestion, type ReviewItem } from "@/lib/api";

export default function ReviewsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [results, setResults] = useState<Record<number, { correct: boolean; explanation: string; answer: number }>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    listReviews(Number(id)).then((values) => { if (active) setItems(values); }).catch((reason) => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);
  async function submit(item: ReviewItem) {
    setBusy(item.id);
    setError("");
    try {
      const result = await reviewQuestion(Number(id), item.id, answers[item.id]);
      setResults((previous) => ({ ...previous, [item.id]: result }));
      setItems((previous) => previous.map((value) => value.id === item.id ? { ...value, resolved: result.correct, review_count: value.review_count + 1 } : value));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败"); }
    finally { setBusy(null); }
  }
  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Link href={`/textbook/${id}`} className="text-blue-600 dark:text-blue-400">← 返回课本</Link>
      <h1 className="text-2xl font-bold my-4">课本错题本</h1>
      <p className="text-zinc-500 mb-6">待复习 {items.filter((item) => !item.resolved).length} 题。答对后标记为已复习；题目更新后，原来的错题仍保留。</p>
      {error && <p role="alert" className="text-red-600">{error}</p>}
      {loading ? <p>正在加载…</p> : items.length === 0 ? <p>暂无错题，完成章节练习后可在这里复习。</p> : <div className="space-y-4">{items.map((item) => (
        <article key={item.id} className="border border-zinc-300 dark:border-zinc-700 rounded-xl p-5">
          <p className="text-sm text-zinc-500 mb-2">{item.chapter_title} · {item.resolved ? "已复习" : "待复习"} · 复习 {item.review_count} 次</p>
          {item.question.source_part && <p className="text-xs text-zinc-500 mb-2">出题时来源：讲解片段 {item.question.source_part}/{item.question.source_parts_total}</p>}
          <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{item.question.question}</ReactMarkdown>
          <div className="my-3 space-y-2">{item.question.options.map((option, index) => <label key={index} className="flex gap-2 items-center border border-zinc-300 dark:border-zinc-700 rounded p-2">
            <input type="radio" name={`review-${item.id}`} checked={answers[item.id] === index} onChange={() => setAnswers((previous) => ({ ...previous, [item.id]: index }))} />
            <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{option}</ReactMarkdown>
          </label>)}</div>
          <button onClick={() => submit(item)} disabled={busy !== null || answers[item.id] === undefined} className="bg-blue-600 text-white rounded px-4 py-2 disabled:opacity-40">{busy === item.id ? "保存中…" : "检查并保存复习结果"}</button>
          {results[item.id] && <div role="status" className="mt-3"><p>{results[item.id].correct ? "回答正确，已记录本次复习。" : `回答有误，正确选项是 ${"ABCD"[results[item.id].answer]}。`}</p><ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{results[item.id].explanation}</ReactMarkdown></div>}
        </article>
      ))}</div>}
    </div>
  );
}
