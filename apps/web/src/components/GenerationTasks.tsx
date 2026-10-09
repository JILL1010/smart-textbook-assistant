"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { cancelGenerationTask, listGenerationTasks, retryGenerationTask, startGenerationTask, type GenerationTask } from "@/lib/api";

const active = (task: GenerationTask) => task.status === "queued" || task.status === "running";
const names = { lecture: "讲解", quiz: "练习", graph: "知识图谱" };
const statuses = { queued: "排队中", running: "生成中", succeeded: "已完成", failed: "失败", cancelled: "已停止", interrupted: "已中断" };

export function useGenerationTasks(book: number, chapter: number, enabled: boolean, onCompleted: (task: GenerationTask | null) => Promise<void>) {
  const [tasks, setTasks] = useState<GenerationTask[]>([]);
  const [ready, setReady] = useState(false);
  const [submitting, setSubmitting] = useState<GenerationTask["kind"] | null>(null);
  const [error, setError] = useState("");
  const callback = useRef(onCompleted);
  const known = useRef(new Map<string, string>());
  const refresh = useRef<() => Promise<void>>(async () => {});
  useEffect(() => { callback.current = onCompleted; }, [onCompleted]);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let initialized = false;
    let timer: ReturnType<typeof setTimeout>;
    let inFlight = false;
    async function poll() {
      if (inFlight || !alive) return;
      inFlight = true;
      try {
        const values = await listGenerationTasks(book, chapter);
        if (!alive) return;
        if (!initialized) {
          // Reconcile chapter data after the initial fetch; a task may have just finished.
          await callback.current(null);
        } else {
          for (const task of values) {
            if (task.status === "succeeded" && known.current.get(task.id) !== "succeeded") await callback.current(task);
          }
        }
        if (!alive) return;
        known.current = new Map(values.map((task) => [task.id, task.status]));
        setTasks(values);
        setError("");
        setReady(true);
        initialized = true;
      } catch (reason) {
        if (alive) setError(reason instanceof Error ? reason.message : "任务状态读取失败");
      } finally {
        inFlight = false;
        if (alive) { clearTimeout(timer); timer = setTimeout(poll, 1000); }
      }
    }
    refresh.current = poll;
    void poll();
    return () => { alive = false; clearTimeout(timer); };
  }, [book, chapter, enabled]);

  const submit = useCallback(async (kind: GenerationTask["kind"], operation: () => Promise<GenerationTask>) => {
    setSubmitting(kind);
    setError("");
    try {
      const task = await operation();
      setTasks((previous) => [task, ...previous.filter((value) => value.id !== task.id)]);
      // Record acknowledgement so a very fast task also produces a completion event.
      if (!known.current.has(task.id)) known.current.set(task.id, task.status);
      await refresh.current();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "任务启动失败"); }
    finally { setSubmitting(null); }
  }, []);

  return {
    tasks, ready, submitting, error, current: tasks.find(active),
    start: (kind: GenerationTask["kind"], parameters: GenerationTask["parameters"]) => submit(kind, () => startGenerationTask(book, chapter, kind, parameters)),
    retry: (task: GenerationTask) => submit(task.kind, () => retryGenerationTask(book, chapter, task.id)),
    cancel: async (task: GenerationTask) => {
      try { await cancelGenerationTask(book, chapter, task.id); await refresh.current(); }
      catch (reason) { setError(reason instanceof Error ? reason.message : "停止失败"); }
    },
  };
}

export default function GenerationTasks({ controller }: { controller: ReturnType<typeof useGenerationTasks> }) {
  const recent = controller.tasks.slice(0, 5);
  return <section aria-label="生成任务" className="mb-5 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4 bg-white dark:bg-zinc-900">
    <h2 className="font-semibold mb-2">生成任务</h2>
    <p className="text-xs text-zinc-500 mb-3">刷新或离开页面后任务继续执行。停止会等待当前请求结束；重试从头处理。</p>
    {controller.error && <p role="alert" className="text-red-600 text-sm">{controller.error}</p>}
    {!controller.ready && <p className="text-sm text-zinc-500">正在检查任务状态…</p>}
    {controller.ready && !recent.length && <p className="text-sm text-zinc-500">暂无生成任务。</p>}
    <ul className="space-y-3">{recent.map((task) => <li key={task.id} className="text-sm" data-task-id={task.id}>
      <div className="flex items-center gap-3 flex-wrap">
        <span>{names[task.kind]} · {statuses[task.status]}</span>
        {active(task) && <span role="status">{task.cancel_requested ? "正在停止，当前请求结束后不会继续" : task.status === "queued" ? "等待执行" : `正在处理第 ${Math.min(task.completed_parts + 1, task.total_parts)}/${task.total_parts} 部分`}</span>}
        {active(task) && <button disabled={task.cancel_requested} onClick={() => controller.cancel(task)} className="text-red-600 underline disabled:opacity-40">停止任务</button>}
        {["failed", "cancelled", "interrupted"].includes(task.status) && <button disabled={!!controller.current || !!controller.submitting} onClick={() => controller.retry(task)} className="text-blue-600 underline disabled:opacity-40">从头重试{nameLabel(task.kind)}</button>}
      </div>
      <p className="text-xs text-zinc-500">已完成 {task.completed_parts}/{task.total_parts} 部分{task.status === "failed" && task.completed_parts < task.total_parts ? ` · 失败位置：第 ${task.completed_parts + 1} 部分` : ""}</p>
      {task.error && <p className="text-red-600 text-xs">{task.error}</p>}
    </li>)}</ul>
  </section>;
}

function nameLabel(kind: GenerationTask["kind"]) { return names[kind]; }
