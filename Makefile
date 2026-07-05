.PHONY: dev test lint clean setup

# ── 开发 ──

dev:
	@echo "Starting engine (FastAPI)..."
	uv run uvicorn engine.api.main:app --reload --port 8000 &

.PHONY: dev-web
dev-web:
	@echo "Starting frontend (Next.js)..."
	cd apps/web && npm run dev &

# ── 测试 ──

test:
	uv run pytest engine/tests/ -v

test-coverage:
	uv run pytest engine/tests/ --cov=engine --cov-report=term-missing

# ── Lint ──

lint:
	uv run ruff check engine
	uv run ruff format --check engine

format:
	uv run ruff format engine

# ── 安装 ──

install:
	uv sync --dev
	cd apps/web && npm install

# ── 数据库 ──

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
	@echo "make dev         启动后端"
	@echo "make dev-web     启动前端"
	@echo "make test        运行测试"
	@echo "make lint        代码检查"
	@echo "make format      自动格式化"
	@echo "make db-reset    重置数据库"
	@echo "make clean       清理缓存"
