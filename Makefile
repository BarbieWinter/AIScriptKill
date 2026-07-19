.PHONY: dev dev-api dev-web dev-mp2 dev-mp2-api dev-mp2-web test test-coverage test-database-privileges test-checkpoint-recovery test-mp2-contract test-mp2-live lint lint-api lint-web typecheck-api format install verify-dev-tools db-start db-stop db-reset db-migrate clean help

# ── 开发 ──

dev:
	@echo "Starting engine (FastAPI) and frontend (Next.js)..."
	@trap 'kill $$(jobs -p) 2>/dev/null || true' INT TERM EXIT; \
	uv run uvicorn engine.api.main:app --reload --port 8000 --ws-max-size 65536 --ws-max-queue 4 & \
	NEXT_PUBLIC_USE_MOCK=false NEXT_PUBLIC_WS_URL=ws://localhost:8000 npm --prefix apps/web run dev & \
	wait

dev-api:
	@echo "Starting engine (FastAPI)..."
	uv run uvicorn engine.api.main:app --reload --port 8000 --ws-max-size 65536 --ws-max-queue 4

dev-web:
	@echo "Starting frontend (Next.js)..."
	npm --prefix apps/web run dev

dev-mp2:
	@echo "Starting MP-2 API and frontend from $$(pwd)..."
	@trap 'kill $$(jobs -p) 2>/dev/null || true' INT TERM EXIT; \
	MULTIPLAYER_V1=true DATABASE_POOLER_URL= uv run uvicorn engine.api.main:app --reload --port 8000 --ws-max-size 65536 --ws-max-queue 4 & \
	NEXT_PUBLIC_USE_MOCK=false npm --prefix apps/web run dev & \
	wait

dev-mp2-api:
	@echo "Starting MP-2 API from $$(pwd)..."
	MULTIPLAYER_V1=true DATABASE_POOLER_URL= uv run uvicorn engine.api.main:app --reload --port 8000 --ws-max-size 65536 --ws-max-queue 4

dev-mp2-web:
	@echo "Starting MP-2 frontend from $$(pwd)..."
	NEXT_PUBLIC_USE_MOCK=false npm --prefix apps/web run dev

# ── 测试 ──

test:
	uv run --frozen pytest engine/tests/ -v

test-coverage:
	uv run --frozen pytest engine/tests/ --cov=engine --cov-report=term-missing

test-database-privileges:
	AISCRIPTKILL_DATABASE_PRIVILEGE_DB_URL="$${AISCRIPTKILL_DATABASE_PRIVILEGE_DB_URL:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}" uv run --frozen pytest engine/tests/test_database_access_boundary.py -k browser_roles_have_no_effective_access -v

test-checkpoint-recovery:
	AISCRIPTKILL_PROCESS_RECOVERY_DB_URL="$${AISCRIPTKILL_PROCESS_RECOVERY_DB_URL:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}" uv run --frozen pytest engine/tests/test_checkpoint_process_recovery.py -v

test-mp2-contract:
	npm --prefix apps/web run test:e2e

test-mp2-live:
	@curl --fail --silent "$${PLAYWRIGHT_API_BASE_URL:-http://127.0.0.1:8000}/health/db" >/dev/null || { echo "MP-2 LIVE BLOCKED: FastAPI/database health check failed."; exit 1; }
	@curl --fail --silent "$${PLAYWRIGHT_BASE_URL:-http://127.0.0.1:3000}/multiplayer" >/dev/null || { echo "MP-2 LIVE BLOCKED: target Next.js checkout is not reachable."; exit 1; }
	npm --prefix apps/web run test:e2e:mp2-live

# ── 代码检查 ──

lint:
	$(MAKE) lint-api
	$(MAKE) lint-web

lint-api:
	uv run --frozen ruff check engine
	uv run --frozen ruff format --check engine

typecheck-api:
	uv run --frozen basedpyright engine/__init__.py engine/agents engine/api engine/core engine/db engine/media engine/rag engine/repositories engine/services

lint-web:
	npm --prefix apps/web run lint

format:
	uv run --frozen ruff format engine

# ── 安装 ──

install:
	uv sync --frozen --extra dev
	cd apps/web && npm install

verify-dev-tools:
	uv run --frozen pytest --version
	uv run --frozen ruff --version
	uv run --frozen basedpyright --version

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
	@echo "make dev-mp2     从当前 checkout 启动 MP-2 后端和前端（需先配置本地 Supabase 与已发布包）"
	@echo "make dev-mp2-api 显式开启 MULTIPLAYER_V1 并启动后端"
	@echo "make dev-mp2-web 使用当前公开 Supabase 环境启动前端"
	@echo "make test        运行测试"
	@echo "make test-database-privileges 使用本地 PostgreSQL 验证浏览器角色权限"
	@echo "make test-checkpoint-recovery 使用本地 PostgreSQL 验证进程强杀恢复"
	@echo "make test-mp2-contract 运行 route-mocked MP-2 浏览器契约测试"
	@echo "make test-mp2-live 针对已启动的真实 Supabase/FastAPI/Next 栈运行双身份大厅测试"
	@echo "make lint        代码检查"
	@echo "make typecheck-api 检查生产后端类型"
	@echo "make verify-dev-tools 验证后端开发工具已按锁文件安装"
	@echo "make format      自动格式化"
	@echo "make db-start    启动本地 Supabase"
	@echo "make db-stop     停止本地 Supabase"
	@echo "make db-reset    重置数据库"
	@echo "make clean       清理缓存"
