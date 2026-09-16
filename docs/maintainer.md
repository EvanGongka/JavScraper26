# 维护者与发布说明

本文面向需要修改代码、构建镜像或发布版本的维护者，普通用户无需阅读。

## 本地 Docker 构建

```bash
docker build -t javscraper26:local .
```

使用仓库内 Compose 配置进行本地构建和启动：

```bash
mkdir -p docker-data/input docker-data/output
docker compose up -d
```

Compose 服务名为 javscraper26，默认监听 8765，并包含日志 named volume、Docker 日志轮转、健康检查和自动重启配置。

## Emby 插件编译

插件项目使用 .NET 6：

```bash
dotnet build -c Release emby-plugin/JavScraper26.EmbyPlugin/JavScraper26.EmbyPlugin.csproj
```

插件不打进 Docker 镜像，继续作为 GitHub Release 附件单独发布。

## Docker Hub 发布

镜像仓库固定为：

```text
docker.io/gongkeao/javscraper26
```

Docker 发布 workflow 为 .github/workflows/publish-docker.yml，只在 workflow_dispatch 或推送 v* tag 时运行，平台为 linux/amd64 和 linux/arm64。

标签规则：

| Git tag | Docker tag |
| --- | --- |
| v0.2.1 | 0.2.1 和 latest |
| v0.2.1-test1 | 0.2.1-test1 |

只有稳定格式 vX.Y.Z 会更新 latest。开发分支不会自动发布镜像。

GitHub Actions 需要配置以下 Secrets：

- DOCKERHUB_USERNAME：gongkeao
- DOCKERHUB_TOKEN：Docker Hub Access Token，不使用账户密码

推送 tag 后，Windows、macOS、Emby 插件和 Docker 镜像会按各自 workflow 发布。
