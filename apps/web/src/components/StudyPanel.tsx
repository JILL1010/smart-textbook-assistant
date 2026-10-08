"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getLearning, setReadCompleted, type LearningSummary } from "@/lib/api";

export default function StudyPanel({ textbookId, chapterId, refresh }: { textbookId: number; chapterId: number; refresh: number }) {
  const [summary, setSummary] = useState<LearningSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    getLearning(textbookId, chapterId).then((value) => { if (active) setSummary(value); }).catch((reason) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [textbookId, chapterId, refresh]);
  async function toggleRead() {
    if (!summary) return;
    setBusy(true);
    setError("");
    try {
      const result = await setReadCompleted(textbookId, chapterId, !summary.read_completed);
      setSummary({ ...summary, read_completed: result.read_completed });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败"); }
    finally { setBusy(false); }
  }
  return (
    <section className="mb-5 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
      <h2 className="font-semibold mb-2">学习记录</h2>
      {error && <p role="alert" className="text-red-600 text-sm">{error}</p>}
      {summary && <>
        <div className="flex flex-wrap gap-4 items-center text-sm">
          <button disabled={busy} onClick={toggleRead} className="rounded border border-zinc-300 dark:border-zinc-700 px-3 py-1.5 disabled:opacity-50">{summary.read_completed ? "已读完 · 撤销标记" : "标记本章已读完"}</button>
          <Link href={`/textbook/${textbookId}/reviews`} className="text-blue-600 dark:text-blue-400 underline">本章待复习错题：{summary.pending_reviews} · 打开课本错题本</Link>
        </div>
        {summary.attempts.length > 0 && <details className="mt-3 text-sm">
          <summary className="cursor-pointer">最近作答记录（最多 20 次）</summary>
          <ul className="mt-2 space-y-1">{summary.attempts.map((attempt) => <li key={attempt.id}>{new Date(attempt.created_at + (attempt.created_at.endsWith("Z") ? "" : "Z")).toLocaleString()} · 得分 {attempt.correct}/{attempt.total} · 讲解版本 {attempt.generation_revision}</li>)}</ul>
        </details>}
      </>}
    </section>
  );
}
