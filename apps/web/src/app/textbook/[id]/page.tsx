"use client";

import { useState, useEffect, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getTextbook, deleteTextbook } from "@/lib/api";

function formatDate(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

interface Chapter {
  id: number;
  textbook_id: number;
  title: string;
  order: number;
  content: string | null;
  generated_content: string | null;
}

interface Textbook {
  id: number;
  title: string;
  filename: string;
  chapter_count: number;
  generated_count: number;
  created_at: string;
  chapters: Chapter[];
}

export default function TextbookPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const [textbook, setTextbook] = useState<Textbook | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    getTextbook(Number(id))
      .then(setTextbook)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  async function handleDelete() {
    if (!confirm("确定要删除这本课本吗？所有章节和生成的内容将被清除。")) return;
    setDeleting(true);
    try {
      await deleteTextbook(Number(id));
      router.push("/");
    } catch {
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12 text-zinc-400 dark:text-zinc-500">
        加载中...
      </div>
    );
  }

  if (!textbook) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12">
        <h1 className="text-2xl font-bold mb-4">课本不存在</h1>
        <Link href="/" className="text-blue-600 dark:text-blue-400 hover:underline">
          返回首页
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-12">
      <Link href="/" className="text-sm text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300 mb-4 inline-block">
        ← 返回首页
      </Link>

      <div className="flex items-start justify-between gap-4 mb-6">
        <div className="flex-1">
          <h1 className="text-2xl font-bold mb-2">{textbook.title}</h1>
          <p className="text-zinc-500 dark:text-zinc-400 text-sm">
            共 {textbook.chapter_count} 个章节
            {textbook.generated_count > 0 && (
              <span className="text-green-600 dark:text-green-400 ml-2">
                已生成 {textbook.generated_count} / {textbook.chapter_count}
              </span>
            )}
            {" · "}
            {formatDate(textbook.created_at)}
          </p>
          {/* Progress bar */}
          {textbook.chapter_count > 0 && (
            <div className="mt-3 w-full max-w-md bg-zinc-100 dark:bg-zinc-800 rounded-full h-2 overflow-hidden">
              <div
                className="h-full bg-green-500 rounded-full transition-all duration-500"
                style={{
                  width: `${Math.round((textbook.generated_count / textbook.chapter_count) * 100)}%`,
                }}
              />
            </div>
          )}
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="text-sm text-zinc-400 dark:text-zinc-500 hover:text-red-500 dark:hover:text-red-400 transition-colors border border-zinc-200 dark:border-zinc-700 rounded-lg px-3 py-1.5 hover:border-red-200 dark:hover:border-red-800 shrink-0"
        >
          {deleting ? "删除中..." : "删除课本"}
        </button>
      </div>

      {/* Chapter list */}
      <Link href={`/textbook/${id}/reviews`} className="inline-block mb-4 text-blue-600 dark:text-blue-400 underline">打开课本错题本</Link>
      <div className="space-y-2">
        {textbook.chapters.map((ch) => (
          <Link
            key={ch.id}
            href={`/textbook/${textbook.id}/chapter/${ch.id}`}
            className="block bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg p-4 hover:shadow transition-shadow"
          >
            <div className="flex items-center gap-3">
              <span className="text-zinc-300 dark:text-zinc-600 text-sm w-8 text-right">
                {ch.order}
              </span>
              <span className="font-medium">{ch.title}</span>
              {ch.generated_content && (
                <span className="text-xs text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950 px-2 py-0.5 rounded">
                  已生成
                </span>
              )}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
