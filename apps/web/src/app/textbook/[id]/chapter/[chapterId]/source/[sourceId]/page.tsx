"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { API_BASE, getSource, type Citation } from "@/lib/api";

export default function SourcePage({ params }: { params: Promise<{ id: string; chapterId: string; sourceId: string }> }) {
  const { id, chapterId, sourceId } = use(params);
  const [source, setSource] = useState<Citation | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    getSource(Number(id), Number(chapterId), sourceId).then((value) => { if (active) setSource(value); }).catch((reason) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [id, chapterId, sourceId]);
  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Link className="text-blue-600 dark:text-blue-400" href={`/textbook/${id}/chapter/${chapterId}`}>← 返回章节</Link>
      <h1 className="text-2xl font-bold my-4">教材原文依据</h1>
      {error && <p role="alert">{error}</p>}
      {source ? (
        <article className="rounded-xl border border-zinc-300 dark:border-zinc-700 p-6">
          <h2 className="font-semibold">{source.chapter_title} · {source.location}</h2>
          <p className="text-sm text-zinc-500 mt-2">原文片段起点：该页或段落第 {source.offset + 1} 个字符。PDF 页码按文件页序计算。</p>
          <blockquote className="whitespace-pre-wrap border-l-4 border-blue-400 pl-4 my-6">{source.text}</blockquote>
          <a className="text-blue-600 dark:text-blue-400 underline" target="_blank" rel="noreferrer" href={`${API_BASE}/api/textbooks/${id}/file${source.page ? `#page=${source.page}` : ""}`}>打开原始教材{source.page ? `第 ${source.page} 页` : "文件"}</a>
        </article>
      ) : !error && <p>正在加载原文…</p>}
    </div>
  );
}
