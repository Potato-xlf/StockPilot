# 第二阶段：数据运营与市场总览

本阶段仍不包含推荐模型、前端和自动交易。它增加三项能力：

- 对数据库中已管理的股票池执行交易日增量同步；
- 检查最新交易日覆盖率、OHLC 合法性、成交量和成交额完整度；
- 基于已管理股票池生成上涨/下跌家数、平均涨跌幅和成交额概览。

## 增量同步

```bash
stockpilot sync-incremental --lookback-days 5
```

命令使用 `Asia/Shanghai` 判断日期，非交易日返回 `skipped`。增量同步只处理
`stocks` 表中已管理的股票，不会自动扩大股票池；扩大股票池仍使用
`sync-market-data`。每次执行都会写入 `data_sync_runs`。

## 状态接口

```text
GET /api/v1/data-quality/status
GET /api/v1/market/overview
```

市场总览的 `scope` 固定为 `managed_universe`。必须结合 `universe_size`、
`quoted_stocks` 和 `data_quality_status` 阅读，不能把测试股票池的统计当作全 A 股。

## VPS 定时任务

安装前确认 `/opt/stockpilot/repo` 是实际部署目录：

```bash
sudo ./scripts/install_incremental_timer.sh
systemctl status stockpilot-incremental.timer
journalctl -u stockpilot-incremental.service -n 100 --no-pager
```

Timer 在周一至周五 18:30（Asia/Shanghai）运行，并增加最多 5 分钟随机延迟。
节假日会由交易日历检查自动跳过。低资源 VPS 上扩大股票池前，必须先重新评估
同步耗时和 AKShare 限流情况。
