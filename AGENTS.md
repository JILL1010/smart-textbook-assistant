# Repository Guidelines

## Project Structure & Module Organization

- `apps/web/`: Next.js App Router, TypeScript, and Tailwind. Pages live in `src/app/`; shared requests and API types belong in `src/lib/api.ts`; reusable UI belongs in `src/components/`.
- `apps/api/`: FastAPI backend. Keep HTTP handling in `routers/`, parsing and generation in `services/`, ORM entities in `models/`, and database setup in `db.py`. Routes use the `/api` prefix.
- `apps/desktop/`: Windows launcher and PyInstaller build script.
- `docs/`: reference material and source-reading notes. `uploads/`, `data/`, and `dist/` hold runtime files or generated artifacts.

## Build, Test, and Development Commands

Run from the repository root in PowerShell:

```powershell
pnpm install
python -m venv apps/api/.venv
apps/api/.venv/Scripts/python -m pip install -r apps/api/requirements.txt
pnpm dev       # Frontend: localhost:3000
pnpm dev:api   # Backend: localhost:8081; separate terminal
pnpm build     # Next.js standalone production build
pnpm lint      # Frontend ESLint checks
pnpm --filter web exec tsc --noEmit --incremental false
```

`make install` assumes the backend virtual environment already exists. The root `format` script has no matching frontend command; match existing formatting manually.

## Coding Style & Naming Conventions

Use four-space indentation and `snake_case` for Python functions/modules; use PascalCase for classes. Use two-space indentation, camelCase functions, and PascalCase components/types in TypeScript. Preserve App Router names such as `page.tsx` and `[chapterId]`. Keep API contracts synchronized with `src/lib/api.ts`. ESLint uses Next.js and TypeScript rules; TypeScript strict mode is enabled.

## Testing Guidelines

Backend regressions use `unittest`: run `apps/api/.venv/Scripts/python -m unittest discover -s apps/api/tests -v`. Frontend proxy tests use `node:test`: run `pnpm --filter web test`. Install backend test dependencies from `apps/api/requirements-dev.txt`.

Name Python tests `test_*.py`; use temporary storage and mock external services. Run lint and type checks; exercise affected browser flows. No coverage threshold is configured. See `docs/reliability-checks.md` for browser checks. `test_launcher.py` launches the existing Windows EXE and creates runtime data.

## Commit & Pull Request Guidelines

This checkout has no Git metadata, so historical conventions are unavailable. Recommended messages: `feat: add chapter export` or `fix: restore subtitles`. Keep commits focused. PRs should describe behavior changes, link applicable issues, report checks and known failures, and include screenshots for UI changes.

## Security & Configuration

Copy `.env.example` to `.env` for local configuration. Relative database, upload, audio, and environment paths depend on the working directory. Keep credentials and uploaded textbooks out of commits and distribution bundles. When changing generation, account for stale audio, quiz, and graph data. Verify client API addressing when changing desktop ports.
