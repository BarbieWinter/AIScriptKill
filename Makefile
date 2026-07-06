.PHONY: dev dev-api dev-web test test-coverage lint lint-api lint-web format install db-start db-stop db-reset db-migrate clean help

# ── 开发 ──

dev:
	@echo "Starting engine (FastAPI) and frontend (Next.js)..."
	@trap 'kill $$(jobs -p) 2>/dev/null || true' INT TERM EXIT; \
	uv run uvicorn engine.api.main:app --reload --port 8000 & \
	NEXT_PUBLIC_USE_MOCK=false NEXT_PUBLIC_WS_URL=ws://localhost:8000 npm --prefix apps/web run dev & \
	wait

dev-api:
	@echo "Starting engine (FastAPI)..."
	uv run uvicorn engine.api.main:app --reload --port 8000

dev-web:
	@echo "Starting frontend (Next.js)..."
	NEXT_PUBLIC_USE_MOCK=false NEXT_PUBLIC_WS_URL=ws://localhost:8000 npm --prefix apps/web run dev

# ── 测试 ──

test:
	uv run pytest engine/tests/ -v

test-coverage:
	uv run pytest engine/tests/ --cov=engine --cov-report=term-missing

# ── Lint ──

lint:
	$(MAKE) lint-api
	$(MAKE) lint-web

lint-api:
	uv run ruff check engine
	uv run ruff format --check engine

lint-web:
	npm --prefix apps/web run lint

format:
	uv run ruff format engine

# ── 安装 ──

install:
	uv sync --dev
	cd apps/web && npm install

# ── 数据库 ──

db-start:
	supabase start -x vector,logflare

db-stop:
	supabase stop

db-reset:
	supabase db reset

db-migrate:
	supabase db push

# ── 清理 ──

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".next" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".venv" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache 2>/dev/null || true

# ── 帮助 ──

help:
	@echo "AIScriptKill - 开发命令"
	@echo "─────────────────────────"
	@echo "make install     安装所有依赖"
	@echo "make dev         同时启动后端和前端"
	@echo "make dev-api     只启动后端"
	@echo "make dev-web     只启动前端"
	@echo "make test        运行测试"
	@echo "make lint        代码检查"
	@echo "make format      自动格式化"
	@echo "make db-start    启动本地 Supabase"
	@echo "make db-stop     停止本地 Supabase"
	@echo "make db-reset    重置数据库"
	@echo "make clean       清理缓存"
