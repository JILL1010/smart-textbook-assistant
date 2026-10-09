// Browser requests share the frontend origin; the server chooses the API port.
export const API_BASE = "";

export interface GenerationTask {
  id: string;
  chapter_id: number;
  kind: "lecture" | "quiz" | "graph";
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | "interrupted";
  revision: number;
  parameters: { difficulty: string; style: string; num_questions: number };
  completed_parts: number;
  total_parts: number;
  cancel_requested: boolean;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

const tasksPath = (book: number, chapter: number) => `/api/textbooks/${book}/chapters/${chapter}/tasks`;
export function listGenerationTasks(book: number, chapter: number) {
  return request<GenerationTask[]>(tasksPath(book, chapter));
}
export function startGenerationTask(book: number, chapter: number, kind: GenerationTask["kind"], parameters: { difficulty: string; style: string; num_questions: number }) {
  return request<GenerationTask>(tasksPath(book, chapter), { method: "POST", body: JSON.stringify({ kind, ...parameters }) });
}
export function cancelGenerationTask(book: number, chapter: number, id: string) {
  return request<GenerationTask>(`${tasksPath(book, chapter)}/${id}/cancel`, { method: "POST", body: "{}" });
}
export function retryGenerationTask(book: number, chapter: number, id: string) {
  return request<GenerationTask>(`${tasksPath(book, chapter)}/${id}/retry`, { method: "POST", body: "{}" });
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// Health check
export async function healthCheck() {
  return request<{ status: string }>("/api/health");
}

// Upload a textbook file
export async function uploadTextbook(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

// List textbooks
export interface Textbook {
  id: number;
  title: string;
  filename: string;
  chapter_count: number;
  generated_count: number;
  created_at: string;
}

export async function listTextbooks() {
  return request<Textbook[]>("/api/textbooks");
}

export async function getTextbook(id: number) {
  return request<Textbook & { chapters: Chapter[] }>(`/api/textbooks/${id}`);
}

export async function deleteTextbook(id: number) {
  return request<{ status: string }>(`/api/textbooks/${id}`, { method: "DELETE" });
}

// Chapters
export interface Chapter {
  id: number;
  textbook_id: number;
  title: string;
  order: number;
  content: string | null;
  generated_content: string | null;
  generation_metadata?: GenerationMetadata | null;
  audio_filename: string | null;
  quiz_data: string | null;
  quiz_token?: string | null;
  knowledge_graph_data: string | null;
}

export interface GenerationMetadata {
  source_characters: number;
  parts: number;
  difficulty: string;
  style: string;
  mode: "ai" | "template";
  created_at: string;
}

export async function getChapter(textbookId: number, chapterId: number) {
  return request<Chapter>(`/api/textbooks/${textbookId}/chapters/${chapterId}`);
}

// Generate content for a chapter
export async function generateContent(
  textbookId: number,
  chapterId: number,
  difficulty: string = "medium",
  style: string = "teacher"
) {
  return request<{ status: string; content: string; generated_content: string; generation_metadata: GenerationMetadata }>(
    `/api/textbooks/${textbookId}/chapters/${chapterId}/generate`,
    {
      method: "POST",
      body: JSON.stringify({ difficulty, style }),
    }
  );
}

// Generate TTS audio for a chapter
export interface Subtitle {
  start: number;
  end: number;
  text: string;
}

export interface TTSResult {
  status: string;
  audio_url: string;
  subtitle_url: string;
  subtitles: Subtitle[];
}

export async function getSubtitles(audioFilename: string) {
  const filename = audioFilename.replace(/\.mp3$/, ".json");
  return request<Subtitle[]>(`/api/subtitles/${encodeURIComponent(filename)}`);
}

export async function generateTTS(textbookId: number, chapterId: number) {
  return request<TTSResult>(
    `/api/textbooks/${textbookId}/chapters/${chapterId}/tts`,
    { method: "POST" }
  );
}

// Ask a question about a chapter
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface Citation {
  id: string;
  textbook_id: number;
  chapter_id: number;
  chapter_title: string;
  page: number | null;
  paragraph: number | null;
  location: string;
  offset: number;
  text: string;
}

export function getSource(textbookId: number, chapterId: number, sourceId: string) {
  return request<Citation>(`/api/textbooks/${textbookId}/chapters/${chapterId}/sources/${sourceId}`);
}

export async function askQuestion(
  textbookId: number,
  chapterId: number,
  question: string,
  messages: ChatMessage[] = []
) {
  return request<{ answer: string; citations: Citation[]; status: string }>(
    `/api/textbooks/${textbookId}/chapters/${chapterId}/ask`,
    {
      method: "POST",
      body: JSON.stringify({ question, messages }),
    }
  );
}

// Quiz
export interface QuizQuestion {
  question: string;
  options: string[];
  answer: number;
  explanation: string;
  source_part?: number;
  source_parts_total?: number;
}

export interface QuizResult {
  status: string;
  quiz: QuizQuestion[];
  quiz_token: string;
}

export interface QuizAttempt {
  id: number;
  generation_revision: number;
  quiz_token: string;
  answers: number[];
  correct: number;
  total: number;
  created_at: string;
}

export interface LearningSummary {
  read_completed: boolean;
  draft: { answers: Record<number, number>; quiz_token: string } | null;
  current_attempt: QuizAttempt | null;
  attempts: QuizAttempt[];
  pending_reviews: number;
}

export function getLearning(textbookId: number, chapterId: number) {
  return request<LearningSummary>(`/api/textbooks/${textbookId}/chapters/${chapterId}/learning`);
}

export function setReadCompleted(textbookId: number, chapterId: number, readCompleted: boolean) {
  return request<{ read_completed: boolean }>(`/api/textbooks/${textbookId}/chapters/${chapterId}/learning/read`, { method: "POST", body: JSON.stringify({ read_completed: readCompleted }) });
}

export function saveQuizDraft(textbookId: number, chapterId: number, token: string, answers: Record<number, number>, sequence: number) {
  return request<{ status: string }>(`/api/textbooks/${textbookId}/chapters/${chapterId}/quiz/draft`, { method: "POST", body: JSON.stringify({ quiz_token: token, answers, sequence }) });
}

export function submitQuiz(textbookId: number, chapterId: number, token: string, answers: number[], sequence: number) {
  return request<QuizAttempt>(`/api/textbooks/${textbookId}/chapters/${chapterId}/quiz/submit`, { method: "POST", body: JSON.stringify({ quiz_token: token, answers, sequence }) });
}

export interface ReviewItem {
  id: number;
  chapter_id: number;
  chapter_title: string;
  question: QuizQuestion;
  selected_answer: number;
  resolved: boolean;
  review_count: number;
}

export function listReviews(textbookId: number) {
  return request<ReviewItem[]>(`/api/textbooks/${textbookId}/reviews`);
}

export function reviewQuestion(textbookId: number, reviewId: number, answer: number) {
  return request<{ correct: boolean; explanation: string; answer: number }>(`/api/textbooks/${textbookId}/reviews/${reviewId}`, { method: "POST", body: JSON.stringify({ answer }) });
}

export async function generateQuiz(
  textbookId: number,
  chapterId: number,
  numQuestions: number = 5,
  difficulty: string = "medium",
  style: string = "teacher"
) {
  return request<QuizResult>(
    `/api/textbooks/${textbookId}/chapters/${chapterId}/quiz`,
    {
      method: "POST",
      body: JSON.stringify({
        num_questions: numQuestions,
        difficulty,
        style,
      }),
    }
  );
}

// Knowledge Graph
export interface KnowledgeGraphNode {
  id: string;
  label: string;
  category: "definition" | "theorem" | "method" | "application";
  source_parts?: number[];
}

export interface KnowledgeGraphEdge {
  source: string;
  target: string;
  relation: "prerequisite" | "generalization" | "application" | "related";
}

export interface KnowledgeGraphData {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
  coverage?: { source_characters: number; parts: number };
}

export interface KnowledgeGraphResult {
  status: string;
  data: KnowledgeGraphData;
}

export async function generateKnowledgeGraph(
  textbookId: number,
  chapterId: number
) {
  return request<KnowledgeGraphResult>(
    `/api/textbooks/${textbookId}/chapters/${chapterId}/knowledge-graph`,
    { method: "POST" }
  );
}
