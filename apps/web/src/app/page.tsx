"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { listTextbooks, uploadTextbook, deleteTextbook, type Textbook } from "@/lib/api";

function formatDate(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function Home() {
  const [textbooks, setTextbooks] = useState<Textbook[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleDelete(id: number, e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("确定要删除这本课本吗？所有章节和生成的内容将被清除。")) return;
    setDeleting(id);
    try {
      await deleteTextbook(id);
      setTextbooks((prev) => prev.filter((tb) => tb.id !== id));
    } catch {
      setError("删除失败");
    } finally {
      setDeleting(null);
    }
  }

  useEffect(() => {
    listTextbooks().then(setTextbooks).catch(() => {});
  }, []);

  async function handleUpload(file: File) {
    const filename = file.name.toLowerCase();
    if (!filename.endsWith(".pdf") && !filename.endsWith(".docx")) {
      setError("仅支持 PDF 和 DOCX 文件");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await uploadTextbook(file);
      const data = await listTextbooks();
      setTextbooks(data);
      // Reset file input so the same file can be re-uploaded
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败，请检查后端是否启动");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-12">
      <h1 className="text-3xl font-bold tracking-tight mb-2">智能课本助手</h1>
      <p className="text-zinc-500 dark:text-zinc-400 mb-8">
        上传 PDF 或 DOCX 课本，生成讲解、语音和练习题
      </p>

      {/* Upload zone */}
      <div
        className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors mb-8 dark:border-zinc-700 ${
          dragOver
            ? "border-blue-500 bg-blue-50 dark:bg-blue-950 dark:border-blue-400"
            : "border-zinc-300 hover:border-zinc-400 dark:hover:border-zinc-600"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files[0];
          if (file) handleUpload(file);
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx"
          className="hidden"
          id="file-upload"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleUpload(file);
          }}
        />
        <label
          htmlFor="file-upload"
          className="cursor-pointer text-zinc-500"
        >
          {uploading ? (
            <span className="text-blue-600 dark:text-blue-400">上传解析中...</span>
          ) : (
            <>
              <p className="text-lg font-medium mb-1 text-zinc-700 dark:text-zinc-200">
                拖拽 PDF 或 DOCX 文件到此处
              </p>
              <p className="text-sm dark:text-zinc-400">或点击选择文件</p>
            </>
          )}
        </label>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg p-3 mb-6 text-sm">
          {error}
        </div>
      )}

      {/* Textbook list */}
      <h2 className="text-xl font-semibold mb-4">已上传的课本</h2>
      {textbooks.length === 0 ? (
        <p className="text-zinc-400 dark:text-zinc-500">暂无课本，上传一本开始学习</p>
      ) : (
        <div className="grid gap-3">
          {textbooks.map((tb) => {
            const progress = tb.chapter_count > 0
              ? Math.round((tb.generated_count / tb.chapter_count) * 100)
              : 0;
            return (
              <Link
                key={tb.id}
                href={`/textbook/${tb.id}`}
                className="block bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg p-4 hover:shadow transition-shadow group"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{tb.title}</div>
                    <div className="text-sm text-zinc-400 dark:text-zinc-500 mt-1">
                      {tb.chapter_count} 个章节
                      {tb.generated_count > 0 && (
                        <span className="text-green-600 dark:text-green-400 ml-2">
                          已生成 {tb.generated_count} 个
                        </span>
                      )}
                      {" · "}
                      {formatDate(tb.created_at)}
                    </div>
                    {/* Progress bar */}
                    {tb.chapter_count > 0 && (
                      <div className="mt-2 w-full bg-zinc-100 dark:bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                        <div
                          className="h-full bg-green-500 rounded-full transition-all duration-500"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    )}
                  </div>
                  <button
                    onClick={(e) => handleDelete(tb.id, e)}
                    disabled={deleting === tb.id}
                    className="text-xs text-zinc-300 dark:text-zinc-600 hover:text-red-500 dark:hover:text-red-400 transition-colors shrink-0 mt-1 opacity-0 group-hover:opacity-100"
                  >
                    {deleting === tb.id ? "删除中..." : "删除"}
                  </button>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
