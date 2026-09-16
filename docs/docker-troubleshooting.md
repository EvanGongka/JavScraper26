# Docker 故障排查与日志

本文面向已经启动 Docker 服务、但遇到容器退出、健康检查失败或日志不足的情况。

## 先看三项信息

```bash
docker compose logs --timestamps --tail=500 -f javscraper26
docker inspect javscraper26 --format 'status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} error={{.State.Error}} finished={{.State.FinishedAt}} restarts={{.RestartCount}}'
docker inspect javscraper26 --format '{{json .State.Health}}'
```

正常启动时，日志应包含进程启动、服务就绪，以及按配置间隔输出的 runtime.heartbeat。

## 健康检查

```bash
curl http://127.0.0.1:8765/emby-api/v1/health
```

健康接口保留 status=ok，并提供 uptime、PID、RSS、活动请求、任务数、缓存数和最近错误时间等诊断信息。

如果健康检查失败，继续查看：

```bash
docker inspect javscraper26 --format '{{range .State.Health.Log}}{{.Output}}{{end}}'
docker stats --no-stream javscraper26
docker events --since 24h --filter container=javscraper26
```

健康状态为 unhealthy 只表示检查连续失败，Docker 不会仅因为该状态停止容器。如果容器随后重启，还要检查外部面板、编排器和 RestartCount。

## 容器退出原因

- oom=true 或退出码 137：发生内存不足。检查 docker stats 和宿主机内存，必要时降低上游并发、缓存条数或图片大小上限。
- 退出码 143：进程收到正常停止信号。检查手动操作、宿主机面板和编排器记录。
- State.Error 有内容：重点检查启动命令、端口、权限和镜像配置。
- 没有最后一条关闭日志：可能是 SIGKILL、OOM 或宿主机断电，应以最后一次心跳和 Docker 状态为准。

## 持久化日志

应用同时写入 stdout 和 JSONL 文件。Compose 配置使用 named volume javscraper26_logs 保存文件日志，容器重启后仍会保留：

```bash
docker compose exec javscraper26 sh -c 'tail -n 200 /var/log/javscraper/javscraper.log'
```

使用 docker run 时，如需保留文件日志，增加以下挂载：

```bash
-v javscraper26_logs:/var/log/javscraper
```

不要使用 docker compose down -v，否则会删除日志卷。应用日志默认按 10 MB、最多 5 个备份文件轮转；Docker stdout 也按 10 MB、最多 5 个文件轮转。

## 日志和稳定性参数

可以将变量写入 .env，或添加到 Compose 的 environment 中。

| 变量 | 默认值 | 说明 |
| --- | ---: | --- |
| JAVSCRAPER_LOG_LEVEL | INFO | 日志级别，可设为 DEBUG |
| JAVSCRAPER_LOG_FILE | /var/log/javscraper/javscraper.log | JSONL 文件路径 |
| JAVSCRAPER_LOG_MAX_BYTES | 10485760 | 单个日志文件大小 |
| JAVSCRAPER_LOG_BACKUP_COUNT | 5 | 日志备份数量 |
| JAVSCRAPER_HEARTBEAT_INTERVAL | 60 | 心跳间隔，单位秒 |
| JAVSCRAPER_SLOW_REQUEST_MS | 3000 | 慢请求阈值，单位毫秒 |
| JAVSCRAPER_METADATA_CACHE_MAX_ENTRIES | 512 | 元数据缓存上限 |
| JAVSCRAPER_METADATA_CACHE_TTL_SECONDS | 86400 | 元数据缓存有效期 |
| JAVSCRAPER_MAX_IMAGE_BYTES | 26214400 | 单张图片大小上限 |
| JAVSCRAPER_MAX_CONCURRENT_UPSTREAM | 8 | 上游请求并发上限 |
| JAVSCRAPER_HTTP_CONNECT_TIMEOUT | 10 | HTTP 连接超时，单位秒 |
| JAVSCRAPER_HTTP_READ_TIMEOUT | 30 | HTTP 读取超时，单位秒 |
| JAVSCRAPER_HTTP_RETRIES | 2 | GET 请求重试次数 |
| JAVSCRAPER_TASK_RETENTION_SECONDS | 3600 | 已完成任务保留时间 |
| JAVSCRAPER_TASK_MAX_COUNT | 100 | 任务记录上限 |
| JAVSCRAPER_TASK_LOG_MAX_ENTRIES | 400 | 单任务日志上限 |

## 日志内容和隐私

每条日志可能包含时间、级别、事件、请求 ID、任务 ID、番号、站点、耗时和异常类型。URL 查询参数、Cookie、Authorization、token、password 和代理认证信息会自动脱敏；输入目录、输出目录和目标路径会保留，用于定位文件问题。

向他人提交日志前，仍应检查路径中是否包含用户名、媒体库名称或其他个人信息。

## JavDB 限制

Docker 服务不会自动读取宿主机 Chromium 的 Cookie，也没有内置登录态挂载方案。需要 JavDB 登录态时使用本地 WebUI，并在本机浏览器完成登录。
