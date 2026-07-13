# VPS低资源安全部署

此配置面向共享的1核、低内存VPS。API镜像由GitHub Actions构建，VPS只拉取镜像，避免编译过程影响现有服务。

## 安全边界

- API只监听 `127.0.0.1:8000`，不开放公网端口。
- PostgreSQL不映射宿主机端口。
- API限制为0.35核、384MB内存；PostgreSQL限制为0.25核、256MB内存。
- 行情请求并发默认为1。
- 日志启用大小和文件数量限制。

## 启动

```bash
cp .env.vps.example .env.vps
# 将 POSTGRES_PASSWORD 替换为长随机字母数字密码
docker compose --env-file .env.vps -f docker-compose.vps.yml pull
docker compose --env-file .env.vps -f docker-compose.vps.yml up -d
docker compose --env-file .env.vps -f docker-compose.vps.yml ps
```

On low-resource VPS hosts, the API health probe has a 60-second startup grace
period and a 15-second timeout so Python cold starts do not cause false
`unhealthy` results.

## 小批量验收

```bash
docker compose --env-file .env.vps -f docker-compose.vps.yml exec api \
  stockpilot sync-market-data --days 30 --limit 10
```

## SSH隧道

在本机运行：

```bash
ssh -L 8000:127.0.0.1:8000 root@VPS_IP
```

然后访问 `http://localhost:8000/docs`。

## 停止与回滚

```bash
docker compose --env-file .env.vps -f docker-compose.vps.yml down
```

不要添加 `-v`，否则会删除PostgreSQL数据卷。
