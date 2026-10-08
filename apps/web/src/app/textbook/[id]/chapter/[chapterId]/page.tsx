"use client";

import { useState, useEffect, use, useRef, useCallback, useMemo } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import StudyPanel from "@/components/StudyPanel";
import { API_BASE, getChapter, getTextbook, getSubtitles, getLearning, saveQuizDraft, submitQuiz, generateContent, generateTTS, askQuestion, generateQuiz, generateKnowledgeGraph, type GenerationMetadata, type Citation, type ChatMessage, type Subtitle, type QuizQuestion, type KnowledgeGraphNode, type KnowledgeGraphEdge } from "@/lib/api";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

interface Chapter {
  id: number;
  textbook_id: number;
  title: string;
  order: number;
  content: string | null;
  generated_content: string | null;
  generation_metadata?: GenerationMetadata | null;
  audio_filename: string | null;
  quiz_data: string | null;
  knowledge_graph_data: string | null;
}

interface ChatEntry {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  status?: string;
}

const DIFFICULTY_OPTIONS = [
  { value: "easy", label: "基础" },
  { value: "medium", label: "进阶" },
  { value: "hard", label: "深入" },
];

const STYLE_OPTIONS = [
  { value: "teacher", label: "教师讲解" },
  { value: "concise", label: "简洁概述" },
  { value: "story", label: "故事引导" },
];

function chatStorageKey(textbookId: number, chapterId: number) {
  return `chat_${textbookId}_${chapterId}`;
}

function loadChatHistory(textbookId: number, chapterId: number): ChatEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(chatStorageKey(textbookId, chapterId));
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveChatHistory(textbookId: number, chapterId: number, chat: ChatEntry[]) {
  if (typeof window === "undefined") return;
  try {
    if (chat.length > 0) {
      localStorage.setItem(chatStorageKey(textbookId, chapterId), JSON.stringify(chat));
    } else {
      localStorage.removeItem(chatStorageKey(textbookId, chapterId));
    }
  } catch { /* quota exceeded, ignore */ }
}

function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function fixMathDelimiters(text: string): string {
  return text
    .replace(/\\\[/g, "$$$$")
    .replace(/\\\]/g, "$$$$")
    .replace(/\\\(/g, "$")
    .replace(/\\\)/g, "$");
}

export default function ChapterPage({
  params,
}: {
  params: Promise<{ id: string; chapterId: string }>;
}) {
  const { id, chapterId } = use(params);
  return <ChapterContent key={`${id}:${chapterId}`} textbookId={Number(id)} cid={Number(chapterId)} />;
}

function ChapterContent({ textbookId, cid }: { textbookId: number; cid: number }) {

  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [chapters, setChapters] = useState<{ id: number; title: string; order: number; generated_content: string | null }[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [difficulty, setDifficulty] = useState("medium");
  const [style, setStyle] = useState("teacher");
  const [showOriginal, setShowOriginal] = useState(false);
  const [showGenerationOptions, setShowGenerationOptions] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [ttsGenerating, setTtsGenerating] = useState(false);
  const [subtitles, setSubtitles] = useState<Subtitle[]>([]);
  const [activeSub, setActiveSub] = useState(-1);
  const audioRef = useRef<HTMLAudioElement>(null);
  const subsContainerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  // Quiz state
  const [quizQuestions, setQuizQuestions] = useState<QuizQuestion[]>([]);
  const [quizGenerating, setQuizGenerating] = useState(false);
  const [userAnswers, setUserAnswers] = useState<Record<number, number>>({});
  const [quizSubmitted, setQuizSubmitted] = useState(false);
  const [quizScore, setQuizScore] = useState<{ correct: number; total: number } | null>(null);
  const [quizToken, setQuizToken] = useState("");
  const [quizSaving, setQuizSaving] = useState(false);
  const [learningLoaded, setLearningLoaded] = useState(false);
  const [draftStatus, setDraftStatus] = useState("");
  const [learningRefresh, setLearningRefresh] = useState(0);
  const draftSequence = useRef(0);

  // Knowledge graph state
  const [graphData, setGraphData] = useState<{ nodes: KnowledgeGraphNode[]; edges: KnowledgeGraphEdge[] } | null>(null);
  const [graphGenerating, setGraphGenerating] = useState(false);
  const [selectedNode, setSelectedNode] = useState<KnowledgeGraphNode | null>(null);
  const [isDark, setIsDark] = useState(false);
  const graphContainerRef = useRef<HTMLDivElement>(null);
  const [graphWidth, setGraphWidth] = useState(700);
  const renderGraphData = useMemo(() => graphData ? {
    nodes: graphData.nodes.map((node) => ({ ...node })),
    links: graphData.edges.map((edge) => ({ ...edge })),
  } : { nodes: [], links: [] }, [graphData]);

  useEffect(() => {
    const container = graphContainerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(([entry]) => {
      setGraphWidth(Math.max(1, entry.contentRect.width));
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [graphData, graphGenerating]);

  // Q&A state — loaded from localStorage via useEffect to avoid hydration mismatch
  const [chat, setChat] = useState<ChatEntry[]>([]);
  const [chatLoaded, setChatLoaded] = useState(false);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Load chapter data + textbook chapters for sidebar
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getChapter(textbookId, cid),
      getTextbook(textbookId),
      getLearning(textbookId, cid),
    ])
      .then(async ([ch, tb, learning]) => {
        if (cancelled) return;
        setChapter(ch);
        if (ch.generation_metadata) {
          setDifficulty(ch.generation_metadata.difficulty);
          setStyle(ch.generation_metadata.style);
        }
        setChapters(tb.chapters ?? []);
        setChat(loadChatHistory(textbookId, cid));
        setChatLoaded(true);
        setQuizToken(ch.quiz_token || "");
        if (learning.draft) {
          setUserAnswers(learning.draft.answers);
        } else if (learning.current_attempt) {
          setUserAnswers(Object.fromEntries(learning.current_attempt.answers.map((answer, index) => [index, answer])));
          setQuizSubmitted(true);
          setQuizScore({ correct: learning.current_attempt.correct, total: learning.current_attempt.total });
        }
        setLearningLoaded(true);
        // Restore quiz from DB if present
        if (ch.quiz_data) {
          try { setQuizQuestions(JSON.parse(ch.quiz_data)); } catch { /* ignore */ }
        }
        // Restore knowledge graph from DB if present
        if (ch.knowledge_graph_data) {
          try { setGraphData(JSON.parse(ch.knowledge_graph_data)); } catch { /* ignore */ }
        }
        if (ch.audio_filename) {
          try {
            const savedSubtitles = await getSubtitles(ch.audio_filename);
            if (!cancelled) setSubtitles(savedSubtitles);
          } catch {
            if (!cancelled) setError("字幕加载失败，可重新生成语音恢复字幕");
          }
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "章节加载失败");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [textbookId, cid]);

  useEffect(() => {
    if (!learningLoaded || !quizToken || quizSubmitted || quizSaving) return;
    let active = true;
    const timer = setTimeout(() => {
      draftSequence.current = Math.max(Date.now(), draftSequence.current + 1);
      setDraftStatus("正在保存作答…");
      saveQuizDraft(textbookId, cid, quizToken, userAnswers, draftSequence.current)
        .then(() => { if (active) setDraftStatus("作答已保存"); })
        .catch(() => { if (active) setDraftStatus("作答保存失败，请重试或提交"); });
    }, 400);
    return () => { active = false; clearTimeout(timer); };
  }, [userAnswers, quizToken, quizSubmitted, quizSaving, learningLoaded, textbookId, cid]);

  // Dark mode observer for graph canvas colors
  useEffect(() => {
    const check = () => setIsDark(document.documentElement.classList.contains("dark"));
    check();
    const obs = new MutationObserver(check);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  // Persist chat to localStorage on change
  useEffect(() => {
    if (chatLoaded) saveChatHistory(textbookId, cid, chat);
  }, [chat, chatLoaded, textbookId, cid]);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);

  const clearChat = useCallback(() => {
    setChat([]);
    saveChatHistory(textbookId, cid, []);
  }, [textbookId, cid]);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    setNotice(null);
    try {
      const result = await generateContent(textbookId, cid, difficulty, style);
      setChapter((prev) =>
        prev ? {
          ...prev, generated_content: result.generated_content, generation_metadata: result.generation_metadata,
          audio_filename: null, quiz_data: null, knowledge_graph_data: null,
        } : prev
      );
      audioRef.current?.pause();
      setSubtitles([]);
      setActiveSub(-1);
      setQuizQuestions([]);
      setQuizToken("");
      setDraftStatus("");
      setUserAnswers({});
      setQuizSubmitted(false);
      setQuizScore(null);
      setGraphData(null);
      setSelectedNode(null);
      setLearningRefresh((value) => value + 1);
      setChapters((prev) => prev.map((ch) => ch.id === cid ? { ...ch, generated_content: result.generated_content } : ch));
      setShowOriginal(false);
      setShowGenerationOptions(false);
      setNotice("讲解已更新，请基于新讲解重新生成语音、练习题和知识图谱。");
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setGenerating(false);
    }
  }

  async function handleGenerateTTS() {
    setTtsGenerating(true);
    setError(null);
    try {
      const result = await generateTTS(textbookId, cid);
      setChapter((prev) =>
        prev ? { ...prev, audio_filename: result.audio_url.split("/").pop()! } : prev
      );
      setSubtitles(result.subtitles);
      setActiveSub(-1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "语音生成失败");
    } finally {
      setTtsGenerating(false);
    }
  }

  async function handleAsk() {
    const q = question.trim();
    if (!q || asking) return;
    setQuestion("");
    setAsking(true);
    setError(null);

    const userEntry: ChatEntry = { role: "user", content: q };
    setChat((prev) => [...prev, userEntry]);

    try {
      const history: ChatMessage[] = chat.map((m) => ({
        role: m.role,
        content: m.content,
      }));
      const result = await askQuestion(textbookId, cid, q, history);
      setChat((prev) => [...prev, { role: "assistant", content: result.answer, citations: result.citations, status: result.status }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "提问失败");
    } finally {
      setAsking(false);
    }
  }

  async function handleGenerateQuiz() {
    setQuizGenerating(true);
    setError(null);
    try {
      const result = await generateQuiz(textbookId, cid, 5, difficulty, style);
      setQuizQuestions(result.quiz);
      setQuizToken(result.quiz_token);
      setUserAnswers({});
      setQuizSubmitted(false);
      setQuizScore(null);
      setChapter((prev) => prev ? { ...prev, quiz_data: JSON.stringify(result.quiz) } : prev);
      setLearningRefresh((value) => value + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成练习题失败");
    } finally {
      setQuizGenerating(false);
    }
  }

  async function handleGenerateGraph() {
    setGraphGenerating(true);
    setError(null);
    setSelectedNode(null);
    try {
      const result = await generateKnowledgeGraph(textbookId, cid);
      setGraphData(result.data);
      setChapter((prev) => prev ? { ...prev, knowledge_graph_data: JSON.stringify(result.data) } : prev);
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成知识图谱失败");
    } finally {
      setGraphGenerating(false);
    }
  }

  async function handleSubmitQuiz() {
    setQuizSaving(true);
    setError(null);
    draftSequence.current = Math.max(Date.now(), draftSequence.current + 1);
    try {
      const result = await submitQuiz(textbookId, cid, quizToken, quizQuestions.map((_, index) => userAnswers[index]), draftSequence.current);
      setQuizScore({ correct: result.correct, total: result.total });
      setQuizSubmitted(true);
      setDraftStatus("成绩与错题已保存");
      setLearningRefresh((value) => value + 1);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "提交失败"); }
    finally { setQuizSaving(false); }
  }

  function handleResetQuiz() {
    setUserAnswers({});
    setQuizSubmitted(false);
    setQuizScore(null);
  }

  function handleDownloadMarkdown() {
    if (!chapter?.generated_content) return;
    downloadBlob(
      chapter.generated_content,
      `${chapter.title}.md`,
      "text/markdown;charset=utf-8"
    );
  }

  function handleDownloadAudio() {
    if (!chapter?.audio_filename) return;
    const a = document.createElement("a");
    a.href = `${API_BASE}/api/audio/${chapter.audio_filename}`;
    a.download = `${chapter.title}.mp3`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function handleTimeUpdate() {
    const audio = audioRef.current;
    if (!audio || subtitles.length === 0) return;
    const t = audio.currentTime;
    const idx = subtitles.findIndex((s) => t >= s.start && t < s.end);
    setActiveSub(idx);
    if (idx >= 0 && subsContainerRef.current) {
      const el = subsContainerRef.current.children[idx] as HTMLElement | undefined;
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function handleSubtitleClick(start: number) {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = start;
    audio.play();
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12 text-center text-zinc-400 dark:text-zinc-500">
        加载中...
      </div>
    );
  }

  if (!chapter) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12">
        <h1 className="text-2xl font-bold mb-4">章节不存在</h1>
        {error && <p className="text-red-600 mb-4">{error}</p>}
        <Link href={`/textbook/${textbookId}`} className="text-blue-600 dark:text-blue-400 hover:underline">
          返回课本
        </Link>
      </div>
    );
  }

  const hasGenerated = !!chapter.generated_content;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      {/* Mobile sidebar toggle */}
      <div className="lg:hidden mb-4">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="text-sm text-zinc-500 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-700 rounded-lg px-3 py-1.5 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
        >
          {sidebarOpen ? "✕ 关闭目录" : "☰ 目录"}
        </button>
      </div>

      <div className="flex gap-8">
        {/* Sidebar — chapter outline */}
        <aside className={`${sidebarOpen ? "block" : "hidden"} lg:block w-full lg:w-56 shrink-0`}>
          <nav className="lg:sticky lg:top-20 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-3 max-h-[70vh] overflow-y-auto">
            <Link
              href={`/textbook/${textbookId}`}
              className="block text-sm font-medium text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300 mb-3 px-2 transition-colors"
            >
              ← 课本目录
            </Link>
            {chapters.map((ch) => (
              <Link
                key={ch.id}
                href={`/textbook/${textbookId}/chapter/${ch.id}`}
                className={`block px-2 py-1.5 rounded-md text-sm transition-colors mb-0.5 ${
                  ch.id === cid
                    ? "bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium"
                    : "text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800"
                }`}
              >
                <span className="text-zinc-300 dark:text-zinc-600 mr-1.5 text-xs">{ch.order}.</span>
                {ch.title}
                {ch.generated_content && (
                  <span className="ml-1.5 text-[10px] text-green-500">✓</span>
                )}
              </Link>
            ))}
          </nav>
        </aside>

        {/* Main content */}
        <div className="flex-1 min-w-0">
          <Link
            href={`/textbook/${textbookId}`}
            className="text-sm text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300 mb-4 inline-block"
          >
            ← 返回课本目录
          </Link>

          <div className="mb-8">
            <h1 className="text-2xl font-bold mb-1">{chapter.title}</h1>
            <p className="text-sm text-zinc-400 dark:text-zinc-500">第 {chapter.order} 章</p>
          </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg p-3 mb-6 text-sm">
          {error}
        </div>
      )}
      {notice && (
        <p role="status" className="mb-4 text-sm text-blue-600 dark:text-blue-400">{notice}</p>
      )}
      <StudyPanel textbookId={textbookId} chapterId={cid} refresh={learningRefresh} />

      {hasGenerated && !showGenerationOptions ? (
        /* Generated explanation */
        <article className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-8">
          {chapter.generation_metadata && (
            <p className="mb-4 text-sm text-zinc-500">
              {chapter.generation_metadata.mode === "template" ? "模板模式，尚未生成 AI 讲解" : "整章讲解"} · 原文 {chapter.generation_metadata.source_characters} 字符 · 共 {chapter.generation_metadata.parts} 部分
            </p>
          )}
          <div className="flex items-center gap-2 mb-6 pb-4 border-b border-zinc-200 dark:border-zinc-800 flex-wrap">
            {/* Tab toggle */}
            <div className="flex bg-zinc-100 dark:bg-zinc-800 rounded-lg p-0.5">
              <button
                onClick={() => setShowOriginal(false)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  !showOriginal
                    ? "bg-white dark:bg-zinc-700 text-zinc-800 dark:text-zinc-200 shadow-sm"
                    : "text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300"
                }`}
              >
                AI 讲解
              </button>
              <button
                onClick={() => setShowOriginal(true)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  showOriginal
                    ? "bg-white dark:bg-zinc-700 text-zinc-800 dark:text-zinc-200 shadow-sm"
                    : "text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300"
                }`}
              >
                原文
              </button>
            </div>

            <div className="flex items-center gap-2 ml-auto">
              {/* Download markdown */}
              <button
                onClick={handleDownloadMarkdown}
                className="text-xs text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300 border border-zinc-200 dark:border-zinc-700 rounded-md px-2 py-1 transition-colors"
              >
                导出 MD
              </button>
              <button
                onClick={() => setShowGenerationOptions(true)}
                disabled={ttsGenerating || quizGenerating || graphGenerating || quizSaving}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-40"
              >
                重新生成
              </button>
            </div>
          </div>
          <div className="prose prose-zinc max-w-none [&_h1]:text-2xl [&_h1]:font-bold [&_h1]:mb-4 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:mt-8 [&_h2]:mb-3 [&_h3]:text-lg [&_h3]:font-medium [&_h3]:mt-6 [&_h3]:mb-2 [&_p]:leading-relaxed [&_p]:mb-4 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6 [&_blockquote]:border-l-4 [&_blockquote]:border-blue-300 [&_blockquote]:pl-4 [&_blockquote]:italic [&_blockquote]:text-zinc-600 [&_code]:bg-zinc-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_pre]:bg-zinc-900 [&_pre]:text-zinc-100 [&_pre]:p-4 [&_pre]:rounded-lg [&_pre]:overflow-x-auto [&_strong]:font-bold [&_em]:italic [&_table]:w-full [&_table]:border-collapse [&_table]:mb-4 [&_th]:border [&_th]:border-zinc-300 [&_th]:bg-zinc-100 [&_th]:px-3 [&_th]:py-2 [&_th]:text-sm [&_td]:border [&_td]:border-zinc-300 [&_td]:px-3 [&_td]:py-2 [&_td]:text-sm [&_hr]:my-6 [&_hr]:border-zinc-200">
            {showOriginal ? (
              chapter.content ? (
                <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {chapter.content}
                </ReactMarkdown>
              ) : (
                <p className="text-zinc-400">本章无原文内容</p>
              )
            ) : (
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                {chapter.generated_content!}
              </ReactMarkdown>
            )}
          </div>
        </article>
      ) : (
        /* Not generated yet */
        <div className="space-y-4">
          <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-8 text-center">
            <div className="text-4xl mb-4">📖</div>
            <h2 className="text-lg font-semibold mb-2">生成 AI 讲解</h2>
            <p className="text-zinc-500 dark:text-zinc-400 text-sm mb-6">
              AI 将根据本章内容生成带例题和要点速记的讲解文案
            </p>
            <p className="text-xs text-zinc-500 mb-4">长章节会按原文顺序分部分处理，全部完成后保存；生成期间请保留页面。</p>

            {/* Difficulty selector */}
            <div className="flex items-center justify-center gap-2 mb-3">
              <span className="text-sm text-zinc-400 dark:text-zinc-500 w-12">难度：</span>
              {DIFFICULTY_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setDifficulty(opt.value)}
                  className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                    difficulty === opt.value
                      ? "border-blue-400 bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300"
                      : "border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 hover:border-zinc-300 dark:hover:border-zinc-600"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            {/* Style selector */}
            <div className="flex items-center justify-center gap-2 mb-6">
              <span className="text-sm text-zinc-400 dark:text-zinc-500 w-12">风格：</span>
              {STYLE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setStyle(opt.value)}
                  className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                    style === opt.value
                      ? "border-blue-400 bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300"
                      : "border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 hover:border-zinc-300 dark:hover:border-zinc-600"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            <button
              onClick={handleGenerate}
              disabled={generating || ttsGenerating || quizGenerating || graphGenerating || quizSaving}
              className="bg-blue-600 text-white px-8 py-2.5 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors font-medium"
            >
              {generating ? "AI 正在生成讲解..." : "生成讲解内容"}
            </button>
            {hasGenerated && (
              <button onClick={() => setShowGenerationOptions(false)} disabled={generating} className="ml-3 text-sm text-zinc-500 disabled:opacity-40">
                取消
              </button>
            )}
          </div>
        </div>
      )}

      {/* Audio player section */}
      {hasGenerated && (
        <div className="mt-4 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-5">
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium shrink-0">语音讲解</span>
            {chapter.audio_filename ? (
              <>
                <audio
                  ref={audioRef}
                  controls
                  className="flex-1 h-10"
                  src={`${API_BASE}/api/audio/${chapter.audio_filename}`}
                  onTimeUpdate={handleTimeUpdate}
                >
                  您的浏览器不支持音频播放
                </audio>
                <button
                  onClick={handleDownloadAudio}
                  className="text-xs text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300 border border-zinc-200 dark:border-zinc-700 rounded-md px-2 py-1 shrink-0 transition-colors"
                  title="下载 MP3"
                >
                  下载
                </button>
                <button
                  onClick={handleGenerateTTS}
                  disabled={ttsGenerating || generating}
                  className="text-xs text-blue-600 dark:text-blue-400 shrink-0 disabled:opacity-40"
                >
                  {ttsGenerating ? "生成中..." : "重新生成语音"}
                </button>
              </>
            ) : (
              <button
                onClick={handleGenerateTTS}
                disabled={ttsGenerating || generating}
                className="text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 border border-blue-200 dark:border-blue-800 rounded-lg px-4 py-2 hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-50 transition-colors"
              >
                {ttsGenerating ? "正在生成语音..." : "生成语音讲解"}
              </button>
            )}
          </div>

          {/* Subtitles */}
          {subtitles.length > 0 && (
            <div
              ref={subsContainerRef}
              className="mt-3 max-h-40 overflow-y-auto border-t border-zinc-100 dark:border-zinc-800 pt-3"
            >
              {subtitles.map((sub, i) => (
                <button
                  key={i}
                  onClick={() => handleSubtitleClick(sub.start)}
                  className={`block w-full text-left px-3 py-1.5 rounded text-sm leading-relaxed transition-colors ${
                    i === activeSub
                      ? "bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300"
                      : "text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800"
                  }`}
                >
                  {sub.text}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Quiz section */}
      {hasGenerated && (
        <div className="mt-4 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-6">
          <h2 className="font-semibold mb-4">练习题</h2>

          {/* No quiz yet — show generate button */}
          {quizQuestions.length === 0 && !quizGenerating && (
            <div className="text-center py-3">
              <p className="text-sm text-zinc-400 dark:text-zinc-500 mb-3">
                AI 会根据本章讲解内容自动出题，检验你的理解程度
              </p>
              <button
                onClick={handleGenerateQuiz}
                disabled={generating}
                className="bg-blue-600 text-white px-6 py-2.5 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors font-medium text-sm"
              >
                生成练习题
              </button>
            </div>
          )}

          {/* Generating */}
          {quizGenerating && (
            <div className="text-center py-6 text-zinc-400 dark:text-zinc-500 text-sm">
              AI 正在出题...
            </div>
          )}

          {/* Quiz loaded */}
          {quizQuestions.length > 0 && (
            <div className="space-y-5">
              {quizQuestions.map((q, qi) => {
                const isCorrect = quizSubmitted && userAnswers[qi] === q.answer;
                const isWrong = quizSubmitted && userAnswers[qi] !== undefined && userAnswers[qi] !== q.answer;
                let borderColor = "border-zinc-200 dark:border-zinc-700";
                if (quizSubmitted) {
                  if (isCorrect) borderColor = "border-green-300 dark:border-green-700";
                  else if (isWrong) borderColor = "border-red-300 dark:border-red-700";
                }

                return (
                  <div key={qi} className={`border ${borderColor} rounded-lg p-4`}>
                    <div className="font-medium mb-3 text-sm [&_p]:inline">
                      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                        {fixMathDelimiters(`${qi + 1}. ${q.question}`)}
                      </ReactMarkdown>
                    </div>
                    <div className="space-y-2">
                      {q.options.map((opt, oi) => {
                        const isSelected = userAnswers[qi] === oi;
                        const isCorrectOption = q.answer === oi;
                        let bgColor = "hover:bg-zinc-50 dark:hover:bg-zinc-800/50";
                        if (quizSubmitted) {
                          if (isCorrectOption) bgColor = "bg-green-50 dark:bg-green-950 border-green-300 dark:border-green-700";
                          else if (isSelected && !isCorrectOption) bgColor = "bg-red-50 dark:bg-red-950 border-red-300 dark:border-red-700";
                        } else if (isSelected) {
                          bgColor = "bg-blue-50 dark:bg-blue-950 border-blue-300 dark:border-blue-700";
                        }

                        return (
                          <label
                            key={oi}
                            className={`flex items-center gap-3 border rounded-lg px-3 py-2 cursor-pointer transition-colors text-sm ${bgColor}`}
                          >
                            <input
                              type="radio"
                              name={`quiz-q-${qi}`}
                              checked={isSelected}
                              onChange={() => !quizSubmitted && setUserAnswers((prev) => ({ ...prev, [qi]: oi }))}
                              disabled={quizSubmitted || quizSaving}
                              className="w-4 h-4 accent-blue-600"
                            />
                            <span className="flex-1 [&_p]:inline">
                              <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                                {fixMathDelimiters(opt)}
                              </ReactMarkdown>
                            </span>
                            {quizSubmitted && isCorrectOption && (
                              <span className="text-green-600 dark:text-green-400 text-xs font-medium">✓ 正确答案</span>
                            )}
                            {quizSubmitted && isSelected && !isCorrectOption && (
                              <span className="text-red-600 dark:text-red-400 text-xs font-medium">✗</span>
                            )}
                          </label>
                        );
                      })}
                    </div>
                    {quizSubmitted && (
                      <div className="mt-3 text-sm p-3 bg-zinc-50 dark:bg-zinc-800 rounded-lg leading-relaxed">
                        <span className="font-medium text-zinc-500 dark:text-zinc-400">解析：</span>
                        <span className="text-zinc-600 dark:text-zinc-300 [&_p]:inline">
                          <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                            {fixMathDelimiters(q.explanation)}
                          </ReactMarkdown>
                        </span>
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Action buttons */}
              <div className="flex items-center gap-3 pt-1">
                {!quizSubmitted ? (
                  <button
                    onClick={handleSubmitQuiz}
                    disabled={quizSaving || !quizToken || Object.keys(userAnswers).length < quizQuestions.length}
                    className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors text-sm font-medium"
                  >
                    {quizSaving ? "保存成绩中…" : `提交 (${Object.keys(userAnswers).length}/${quizQuestions.length})`}
                  </button>
                ) : (
                  <>
                    <div className="text-sm font-medium">
                      {quizScore ? `得分: ${quizScore.correct} / ${quizScore.total}` : ""}
                    </div>
                    <button
                      onClick={handleResetQuiz}
                      className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      重新作答
                    </button>
                  </>
                )}
                <button
                  onClick={handleGenerateQuiz}
                  disabled={quizGenerating || generating || quizSaving}
                  className="text-sm text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300 border border-zinc-200 dark:border-zinc-700 rounded-md px-3 py-1.5 ml-auto transition-colors"
                >
                  重新生成
                </button>
              </div>
              {draftStatus && <p role="status" className="text-xs text-zinc-500">{draftStatus}</p>}
            </div>
          )}
        </div>
      )}

      {/* Knowledge graph section */}
      {hasGenerated && (
        <div className="mt-4 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">知识图谱</h2>
            {graphData && (
              <button
                onClick={handleGenerateGraph}
                disabled={graphGenerating || generating}
                className="text-xs text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300 border border-zinc-200 dark:border-zinc-700 rounded-md px-2 py-1 transition-colors"
              >
                重新生成
              </button>
            )}
          </div>

          {/* Empty state */}
          {!graphData && !graphGenerating && (
            <div className="text-center py-3">
              <p className="text-sm text-zinc-400 dark:text-zinc-500 mb-3">
                AI 会从本章内容中提取关键概念，构建概念关系图谱
              </p>
              <button
                onClick={handleGenerateGraph}
                disabled={generating}
                className="bg-blue-600 text-white px-6 py-2.5 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors font-medium text-sm"
              >
                生成知识图谱
              </button>
            </div>
          )}

          {/* Loading */}
          {graphGenerating && (
            <div className="text-center py-6 text-zinc-400 dark:text-zinc-500 text-sm">
              AI 正在分析概念关系...
            </div>
          )}

          {/* Graph visualization */}
          {graphData && !graphGenerating && (
            <>
              {/* Legend */}
              <div className="flex flex-wrap gap-3 mb-3 text-xs">
                {[
                  { cat: "definition", label: "定义", color: isDark ? "#60a5fa" : "#3b82f6" },
                  { cat: "theorem", label: "定理/公式", color: isDark ? "#f472b6" : "#ec4899" },
                  { cat: "method", label: "方法/技巧", color: isDark ? "#34d399" : "#10b981" },
                  { cat: "application", label: "应用/例子", color: isDark ? "#fbbf24" : "#f59e0b" },
                ].map((item) => (
                  <span key={item.cat} className="flex items-center gap-1.5 text-zinc-500 dark:text-zinc-400">
                    <span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: item.color }} />
                    {item.label}
                  </span>
                ))}
              </div>

              {/* Graph canvas */}
              <div ref={graphContainerRef} className="w-full border border-zinc-200 dark:border-zinc-700 rounded-lg overflow-hidden" style={{ height: 400 }}>
                <ForceGraph2D
                  graphData={renderGraphData}
                  width={graphWidth}
                  height={400}
                  nodeLabel={(n: unknown) => (n as KnowledgeGraphNode).label || ""}
                  nodeColor={(n: unknown) => {
                    const cat = (n as KnowledgeGraphNode).category || "definition";
                    const colors: Record<string, string> = {
                      definition: isDark ? "#60a5fa" : "#3b82f6",
                      theorem: isDark ? "#f472b6" : "#ec4899",
                      method: isDark ? "#34d399" : "#10b981",
                      application: isDark ? "#fbbf24" : "#f59e0b",
                    };
                    return colors[cat] || colors.definition;
                  }}
                  linkColor={() => isDark ? "rgba(161,161,170,0.4)" : "rgba(113,113,122,0.3)"}
                  backgroundColor={isDark ? "#18181b" : "#ffffff"}
                  linkDirectionalArrowLength={4}
                  linkDirectionalArrowRelPos={1}
                  linkDirectionalArrowColor={() => isDark ? "rgba(161,161,170,0.6)" : "rgba(113,113,122,0.5)"}
                  nodeCanvasObject={(n: unknown, ctx: CanvasRenderingContext2D, globalScale: number) => {
                    const cn = n as KnowledgeGraphNode & { x: number; y: number };
                    const cat = cn.category || "definition";
                    const colors: Record<string, string> = {
                      definition: isDark ? "#60a5fa" : "#3b82f6",
                      theorem: isDark ? "#f472b6" : "#ec4899",
                      method: isDark ? "#34d399" : "#10b981",
                      application: isDark ? "#fbbf24" : "#f59e0b",
                    };
                    const label = cn.label || "";
                    const fontSize = 12 / globalScale;
                    ctx.font = `${fontSize}px sans-serif`;
                    const textWidth = ctx.measureText(label).width;
                    const padding = 4 / globalScale;
                    const nodeWidth = textWidth + padding * 2;
                    const nodeHeight = fontSize + padding * 2;

                    ctx.fillStyle = colors[cat] || colors.definition;
                    ctx.beginPath();
                    const rx = 4 / globalScale;
                    ctx.roundRect(cn.x - nodeWidth / 2, cn.y - nodeHeight / 2, nodeWidth, nodeHeight, rx);
                    ctx.fill();

                    ctx.fillStyle = "#ffffff";
                    ctx.textAlign = "center";
                    ctx.textBaseline = "middle";
                    ctx.fillText(label, cn.x, cn.y);
                  }}
                  nodePointerAreaPaint={(n: unknown, color: string, ctx: CanvasRenderingContext2D, globalScale: number) => {
                    const cn = n as KnowledgeGraphNode & { x: number; y: number };
                    const label = cn.label || "";
                    const fontSize = 12 / globalScale;
                    ctx.font = `${fontSize}px sans-serif`;
                    const textWidth = ctx.measureText(label).width;
                    const padding = 6 / globalScale;
                    const nodeWidth = textWidth + padding * 2;
                    const nodeHeight = fontSize + padding * 2;
                    ctx.fillStyle = color;
                    ctx.fillRect(cn.x - nodeWidth / 2, cn.y - nodeHeight / 2, nodeWidth, nodeHeight);
                  }}
                  onNodeClick={(n: unknown) => {
                    const node = n as KnowledgeGraphNode;
                    if (node.id && node.label) {
                      setSelectedNode({ id: node.id, label: node.label, category: node.category || "definition" });
                    }
                  }}
                  onBackgroundClick={() => setSelectedNode(null)}
                  enableZoomInteraction={true}
                  enableNodeDrag={true}
                  minZoom={0.3}
                  maxZoom={5}
                  cooldownTicks={50}
                />
              </div>

              {/* Selected node detail panel */}
              {selectedNode && (() => {
                const relatedEdges = graphData.edges.filter(
                  (e) => e.source === selectedNode.id || e.target === selectedNode.id
                );
                const relationLabel: Record<string, string> = {
                  prerequisite: "前置",
                  generalization: "泛化",
                  application: "应用",
                  related: "相关",
                };
                const categoryLabel: Record<string, string> = {
                  definition: "定义",
                  theorem: "定理/公式",
                  method: "方法/技巧",
                  application: "应用/例子",
                };
                return (
                  <div className="mt-3 p-3 bg-zinc-50 dark:bg-zinc-800 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <span className="font-medium text-sm">{selectedNode.label}</span>
                        <span className="ml-2 text-xs text-zinc-400 dark:text-zinc-500">
                          {categoryLabel[selectedNode.category] || selectedNode.category}
                        </span>
                      </div>
                      <button
                        onClick={() => setSelectedNode(null)}
                        className="text-xs text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300"
                      >
                        ✕
                      </button>
                    </div>
                    {relatedEdges.length > 0 && (
                      <div className="text-xs text-zinc-500 dark:text-zinc-400 space-y-1">
                        <span className="font-medium">关联概念：</span>
                        {relatedEdges.map((e, i) => {
                          const otherId = e.source === selectedNode.id ? e.target : e.source;
                          const otherNode = graphData.nodes.find((n) => n.id === otherId);
                          if (!otherNode) return null;
                          return (
                            <span key={i} className="inline-block mr-2 mb-1">
                              <button
                                onClick={() => {
                                  const node = graphData.nodes.find((n) => n.id === otherId);
                                  if (node) setSelectedNode(node);
                                }}
                                className="text-blue-600 dark:text-blue-400 hover:underline"
                              >
                                {otherNode.label}
                              </button>
                              <span className="text-zinc-400 dark:text-zinc-500 ml-0.5">
                                ({relationLabel[e.relation] || e.relation})
                              </span>
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })()}
            </>
          )}
        </div>
      )}

      {/* Q&A section */}
      <div className="mt-8 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">问答互动</h2>
          {chat.length > 0 && (
            <button
              onClick={clearChat}
              className="text-xs text-zinc-400 dark:text-zinc-500 hover:text-red-500 dark:hover:text-red-400 transition-colors"
            >
              清除对话
            </button>
          )}
        </div>

        {/* Chat messages */}
        {chat.length > 0 && (
          <div className="space-y-3 mb-4 max-h-96 overflow-y-auto">
            {chat.map((entry, i) => (
              <div
                key={i}
                className={`flex gap-2 ${
                  entry.role === "user" ? "justify-end" : ""
                }`}
              >
                {entry.role === "assistant" && (
                  <span className="text-sm mt-1">🤖</span>
                )}
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-2 text-sm leading-relaxed ${
                    entry.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200"
                  }`}
                >
                  <div className="text-sm leading-relaxed [&_code]:bg-zinc-200 dark:[&_code]:bg-zinc-700 [&_code]:px-1 [&_code]:rounded [&_strong]:font-bold [&_a]:text-blue-600 dark:[&_a]:text-blue-400 [&_a]:underline">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[rehypeKatex]}
                      components={{
                        p: ({ children }) => <span>{children}<br /></span>,
                      }}
                    >
                      {entry.content}
                    </ReactMarkdown>
                    {entry.citations && entry.citations.length > 0 && (
                      <div className="mt-3 border-t border-zinc-300 dark:border-zinc-600 pt-2 space-y-2">
                        <p className="font-medium">{entry.status === "retrieval_only" ? "检索到的原文" : "教材来源"}</p>
                        {entry.citations.map((source) => (
                          <details key={source.id} className="rounded border border-zinc-300 dark:border-zinc-600 p-2">
                            <summary className="cursor-pointer">{source.chapter_title} · {source.location}</summary>
                            <p className="mt-2 whitespace-pre-wrap">{source.text}</p>
                            <Link className="inline-block mt-2 text-blue-600 dark:text-blue-400 underline" href={`/textbook/${source.textbook_id}/chapter/${source.chapter_id}/source/${source.id}`}>查看原文位置</Link>
                          </details>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                {entry.role === "user" && (
                  <span className="text-sm mt-1">👤</span>
                )}
              </div>
            ))}
            {asking && (
              <div className="flex gap-2">
                <span className="text-sm mt-1">🤖</span>
                <div className="bg-zinc-100 dark:bg-zinc-800 rounded-lg px-4 py-2 text-sm text-zinc-400 dark:text-zinc-500">
                  思考中...
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        )}

        {/* Input */}
        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAsk()}
            placeholder="针对本章内容提问..."
            className="flex-1 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 rounded-lg px-4 py-2 text-sm outline-none focus:border-blue-300 dark:focus:border-blue-500 placeholder:text-zinc-400 dark:placeholder:text-zinc-500"
          />
          <button
            onClick={handleAsk}
            disabled={!question.trim() || asking}
            className="bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-zinc-700 dark:hover:bg-zinc-300 disabled:opacity-40 transition-colors"
          >
            提问
          </button>
        </div>
      </div>
        </div>
      </div>
    </div>
  );
}
