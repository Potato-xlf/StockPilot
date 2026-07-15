# Phase 3：全市场股票池与板块轮动

本阶段把“全市场股票元数据”和“日线行情管理池”分开，避免录入全部 A 股后，增量任务立即请求约 5000 只股票。

## 数据边界

- `stocks.quote_enabled=false`：只保存股票代码、名称和交易所，不参与日线同步。
- `stocks.quote_enabled=true`：属于行情管理池，会被 `sync-incremental` 更新。
- 数据库迁移会把升级前已有股票设为 `quote_enabled=true`，保持原行为。
- 新增行业和概念板块、成分股、每日板块快照、板块同步运行记录。

## 推荐初始化顺序

同步完整 A 股元数据，不下载日线：

```bash
docker compose exec api stockpilot sync-stock-universe
curl http://localhost:8000/api/v1/universe/status
```

按固定排序分批启用并回填日线，建议每批 50～100 只：

```bash
docker compose exec api stockpilot sync-quote-batch --days 30 --batch-size 100 --offset 0
docker compose exec api stockpilot sync-quote-batch --days 30 --batch-size 100 --offset 100
```

命令可以重复执行；只有成功取得日线的股票才会启用。`sync-incremental` 仍只更新已启用股票。

## 板块同步

同步行业板块、快照和成分股：

```bash
docker compose exec api stockpilot sync-sector-data --sector-type industry
```

同步概念板块：

```bash
docker compose exec api stockpilot sync-sector-data --sector-type concept
```

只更新板块快照、不请求成分股：

```bash
docker compose exec api stockpilot sync-sector-data --sector-type industry --no-members
```

冒烟测试可使用 `--limit 2`。板块成分接口较容易受上游限流影响，失败会指数退避重试并记录 `partial` 或 `error`。

行业快照优先使用东方财富数据；当东方财富连接失败时，会自动降级到同花顺行业数据。同花顺备用源不提供换手率和总市值，因此这两个字段会留空，排名仍使用其余可用指标。概念板块暂未启用不等价的备用快照源，避免用不完整目录数据生成误导性排名。

## API

```text
GET /api/v1/universe/status
GET /api/v1/sectors/ranking?sector_type=industry&limit=20
GET /api/v1/sectors/ranking?sector_type=concept&limit=20
```

板块强度分数范围为 0～100，采用同类板块横截面百分位：

- 涨跌幅：50%
- 上涨家数占比：25%
- 换手率：15%
- 领涨股涨幅：10%

`rank_change` 为上一快照排名减去当前排名；正数表示排名上升。只有积累至少两个交易日快照后才会出现排名变化。

该分数用于观察板块相对强弱，不是买入信号，也不包含未来收益预测。

## VPS 自动快照

安装工作日收盘后板块快照定时器：

```bash
cd /opt/stockpilot/repo
./scripts/install_sector_timer.sh
```

定时器在工作日 18:45（Asia/Shanghai）后随机延迟最多 10 分钟，更新行业板块快照，不同步成分股。概念板块可人工执行同步，待补充具备同等实时指标的备用源后再加入自动任务。成分股建议人工低频刷新。

## 测试数据库保护

集成测试会重建数据表，因此只允许连接数据库名以 `_test` 结尾的专用数据库。不要把 `RUN_INTEGRATION_TESTS=1` 指向开发或生产数据库。
