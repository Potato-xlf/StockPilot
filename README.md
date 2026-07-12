# StockPilot

StockPilot 第一阶段：A 股选股面板的数据基础层。技术栈为 Python 3.12、FastAPI、PostgreSQL、可选 Redis、Docker Compose、SQLAlchemy 与 Alembic。

## 快速启动

```bash
cp .env.example .env
docker compose up --build -d postgres api
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/data-source/status
```

Redis 默认不启动；需要时运行 `docker compose --profile redis up -d redis`。

## 同步行情

全量股票列表与最近 30 个交易日日线：

```bash
docker compose exec api stockpilot sync-market-data --days 30
```

首次冒烟测试建议限制 10 只：

```bash
docker compose exec api stockpilot sync-market-data --days 30 --limit 10
```

命令对股票、日历和日线均执行 PostgreSQL upsert，可重复运行。单股请求自动重试；只要有股票同步失败，命令会记录股票代码并以退出码 2 结束，便于监控识别不完整批次。

## 本地开发

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
docker compose up -d postgres
alembic upgrade head
uvicorn app.main:app --reload --app-dir backend
pytest -q
```

需要本地 PostgreSQL 的幂等同步集成测试：

```bash
RUN_INTEGRATION_TESTS=1 pytest -q tests/integration
```

GitHub Actions 会启动 PostgreSQL 16，执行 Alembic 迁移、Ruff、单元测试和集成测试。

## 目录

```text
backend/app/{api,core,db,models,schemas,services,data_sources,tasks}
alembic/versions
tests
scripts
docs
```

数据源接口与扩展说明见 `docs/architecture.md`。
