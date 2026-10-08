.PHONY: dev dev-api dev-web build lint install clean

# Install all dependencies
install:
	pnpm install
	apps/api/.venv/Scripts/pip install -r apps/api/requirements.txt

# Start both frontend and backend dev servers (run in separate terminals)
dev:
	@echo "Start frontend: pnpm dev"
	@echo "Start backend:  pnpm dev:api"

dev-web:
	pnpm dev

dev-api:
	apps/api/.venv/Scripts/python -m uvicorn main:app --app-dir apps/api --reload --port 8081

build:
	pnpm build

lint:
	pnpm lint

clean:
	rm -rf apps/web/.next apps/web/node_modules
	rm -rf apps/api/__pycache__ apps/api/.venv apps/api/.mypy_cache
