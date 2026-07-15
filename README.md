# StockPilot

StockPilot A 股选股面板的数据基础与市场运营层。技术栈为 Python 3.12、FastAPI、PostgreSQL、可选 Redis、Docker Compose、SQLAlchemy 与 Alembic。

## 快速启动

macOS/Linux 推荐直接运行一键启动脚本：

```bash
./start.sh
```

脚本会自动检查 Docker、首次创建 `.env`、构建并启动 PostgreSQL 与 API，等待健康检查通过后显示访问地址。完成后打开：

```text
http://localhost:8000/docs
```

可选 Redis：

```bash
./start.sh --with-redis
```

停止全部本地服务：

```bash
docker compose down
```

也可以手动启动：

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

交易日增量更新已管理股票池：

```bash
docker compose exec api stockpilot sync-incremental --lookback-days 5
```

数据质量与市场总览：

```bash
curl http://localhost:8000/api/v1/data-quality/status
curl http://localhost:8000/api/v1/market/overview
curl 'http://localhost:8000/api/v1/sync/runs?limit=20'
```

自动增量任务和指标含义见 `docs/phase2-operations.md`。

`/api/v1/sync/runs` 返回最近行情、股票池和板块同步记录，可用于排查
`partial`/`error` 批次以及后续面板展示。

## 全市场股票池与板块轮动

完整股票元数据与受控批次日线：

```bash
docker compose exec api stockpilot sync-stock-universe
docker compose exec api stockpilot sync-quote-batch --days 30 --batch-size 100 --offset 0
curl http://localhost:8000/api/v1/universe/status
```

行业/概念板块及轮动排名：

```bash
docker compose exec api stockpilot sync-sector-data --sector-type industry
curl 'http://localhost:8000/api/v1/sectors/ranking?sector_type=industry&limit=20'
```

全市场元数据不会自动进入日线管理池。批次扩展策略、板块评分定义和测试数据库保护见 `docs/phase3-universe-sectors.md`。

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

共享低资源VPS请使用预构建镜像和资源受限配置，详见 `docs/vps-deployment.md`。

## 目录

```text
backend/app/{api,core,db,models,schemas,services,data_sources,tasks}
alembic/versions
tests
scripts
docs
```

数据源接口与扩展说明见 `docs/architecture.md`。
