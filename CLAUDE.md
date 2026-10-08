# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

智能课本助手 (Smart Textbook Assistant) — 上传课本 (PDF/docx) 后生成讲解、语音、练习题和知识图谱，支持 AI 互动问答。

## Architecture

```
apps/web/     Next.js 16 App Router + TypeScript + Tailwind (port 3000)
apps/api/     Python FastAPI + SQLAlchemy + SQLite (port 8081)
```

## Commands

```bash
# Install all dependencies
make install

# Start frontend dev server (port 3000)
pnpm dev

# Start backend dev server (port 8081)
pnpm dev:api

# Build frontend
pnpm build

# Lint
pnpm lint
```

## Key conventions

- Frontend API calls go through `apps/web/src/lib/api.ts` and same-origin `/api`; the Next.js proxy reads `API_UPSTREAM_URL` at runtime (default `http://127.0.0.1:8081`).
- Backend routes are registered in `apps/api/main.py` under the `/api` prefix
- File uploads stored in `uploads/`, database in `data/`
