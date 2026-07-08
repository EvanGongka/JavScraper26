# javScraper26

一个本地运行的 JAV 元数据刮削器，提供两种用法：

- `普通 WebUI`
  适合扫描本地目录、批量抓取元数据、整理输出目录
- `Emby 服务模式`
  适合作为 Emby 插件后端，长期后台运行

## 你能做什么

- 扫描视频目录并识别番号
- 按番号类型自动分流站点
- 抓取标题、简介、演员、系列、片商、发布日期等信息
- 输出 `movie.nfo`、`fanart.jpg`、`thumb.jpg`、`poster.jpg`、`extrafanart/`
- 按 `女优名/[番号] 标题` 整理目录
- 给 Emby 提供元数据和图片接口

## 支持的站点

普通番号：

- `JAV321`
- `JavBooks`
- `AVBASE`
- `FreeJavBT`
- `JavBus`
- `AVMOO`
- `JavDB`

特殊番号：

- `FC2`
- `Caribbeancom`
- `CaribbeancomPR`
- `HEYZO`
- `HeyDouga`
- `1Pondo`
- `10musume`
- `PACOPACOMAMA`
- `MURAMURA`

## 快速开始

### 方式 1：本地直接运行

环境要求：

- `Python 3.10+`
- `pip`

安装并启动：

```bash
cd javScraper26
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

默认行为：

- 监听 `127.0.0.1`
- 端口随机
- 自动打开浏览器
- 先进入模式选择页

安装项目后也可以直接运行：

```bash
javscraper26
```

### 方式 2：Docker 公共镜像

Docker 镜像地址：

- [gongkeao/javscraper26](https://hub.docker.com/r/gongkeao/javscraper26)

直接拉取稳定版：

```bash
docker pull gongkeao/javscraper26:latest
```

启动：

```bash
docker run -d \
  --name javscraper26 \
  -p 8765:8765 \
  -e JAVSCRAPER_MODE=service \
  -e JAVSCRAPER_HOST=0.0.0.0 \
  -e JAVSCRAPER_PORT=8765 \
  -e JAVSCRAPER_DISABLE_BROWSER=1 \
  -v "$(pwd)/docker-data/input:/media/input" \
  -v "$(pwd)/docker-data/output:/media/output" \
  gongkeao/javscraper26:latest
```

Docker 版默认只支持：

- `Emby 服务模式`

不支持：

- 容器内普通 WebUI 的系统目录选择框
- Docker 中的 `JavDB` 浏览器登录态读取

## 启动方式

### 模式选择页

```bash
python3 app.py
```

打开后可在首页选择：

- `普通 WebUI`
- `Emby 服务模式`

### 直接启动普通 WebUI

```bash
JAVSCRAPER_MODE=webui python3 app.py
```

### 直接启动 Emby 服务模式

```bash
JAVSCRAPER_MODE=service JAVSCRAPER_PORT=8765 python3 app.py
```

### 局域网访问 / 服务器运行

```bash
JAVSCRAPER_MODE=service \
JAVSCRAPER_HOST=0.0.0.0 \
JAVSCRAPER_PORT=8765 \
JAVSCRAPER_DISABLE_BROWSER=1 \
python3 app.py
```

## 普通 WebUI 怎么用

访问：

- `/webui`

操作步骤：

1. 选择 `扫描目录`
2. 如有需要，选择 `输出目录`
3. 点击 `扫描`
4. 检查识别出的番号列表
5. 调整站点顺序
6. 点击 `开始刮削`
7. 如有需要，在连通性弹窗里填写代理
8. 点击 `继续刮削`
9. 等待任务完成

说明：

- 如果不手动选择输出目录，默认会使用：
  - `扫描目录/javScraper26-output`
- 站点顺序只能在各自分组内调整
- `JavDB` 依赖本机浏览器登录态，未登录时会自动跳过

### 页面截图

模式选择页：

![模式选择页](docs/images/mode-selector.png)

普通 WebUI：

![普通 WebUI 主界面](docs/images/main-ui.png)

连通性校验：

![站点连通性校验弹窗](docs/images/connectivity-dialog.png)

刮削结果：

![普通 WebUI 刮削结果](docs/images/scrape-result.png)

## Emby 服务模式怎么用

访问：

- `/service`

服务模式适合：

- 给 Emby 插件提供元数据
- 长时间后台运行
- 查看最近的请求和抓取日志

常用接口：

- `GET /emby-api/v1/health`
- `GET /emby-api/v1/logs/recent`
- `GET /emby-api/v1/movies/resolve`
- `GET /emby-api/v1/movies/{provider}/{id}`
- `GET /emby-api/v1/images/{primary|thumb|backdrop}/{provider}/{id}`

最小验证：

1. 启动服务模式
2. 打开 `http://127.0.0.1:8765/service`
3. 打开 `http://127.0.0.1:8765/emby-api/v1/health`
4. 确认返回 `status=ok`

页面截图：

![Emby 服务模式页面](docs/images/service-mode.png)

## Emby 插件怎么用

仓库里已经包含 Emby 插件：

- 插件 zip：
  - `emby-plugin/JavScraper26.EmbyPlugin/bin/Emby.JavScraper26@v0.1.0.zip`
- 插件 DLL：
  - `emby-plugin/JavScraper26.EmbyPlugin/bin/JavScraper26.EmbyPlugin.dll`

### 安装插件

推荐直接安装 zip：

1. 打开 Emby 管理后台
2. 进入 `插件`
3. 选择手动安装 / 上传插件
4. 上传：
   - `Emby.JavScraper26@v0.1.0.zip`
5. 安装后按提示重启 Emby

### 配置插件

插件配置项：

- `Server URL`
  - 例如：`http://127.0.0.1:8765`
- `Enable Proxy`
- `Proxy Protocol`
- `Proxy Host`
- `Proxy Port`

配置步骤：

1. 先启动 `javScraper26` 的服务模式
2. 打开 Emby 插件页
3. 在 `Server URL` 中填写服务地址
4. 如果需要代理，开启 `Enable Proxy` 并填完整代理信息
5. 保存配置
6. 在电影库中执行 `识别` 或 `刷新元数据`

如果 Emby 和 `javScraper26` 不在同一台机器：

- `Server URL` 要填写 Emby 能访问到的地址
- 例如：`http://<宿主机IP>:8765`

## 代理怎么配

### 普通 WebUI

在连通性校验弹窗中填写代理：

- `协议`
- `代理地址`
- `端口`

这会用于：

- 当前批次连通性检查
- 当前批次抓取任务

### Emby 服务模式

服务模式支持两层代理：

1. 服务端默认代理
2. 插件请求级代理

服务端默认代理通过环境变量设置：

```bash
JAVSCRAPER_PROXY_ENABLED=1
JAVSCRAPER_PROXY_PROTOCOL=http
JAVSCRAPER_PROXY_HOST=127.0.0.1
JAVSCRAPER_PROXY_PORT=7890
```

优先级：

- 插件里填了代理时，优先使用插件代理
- 插件没填时，使用服务端默认代理

## 输出结果

每个成功条目会输出到：

```text
<输出目录>/
└── #整理完成/
    └── <女优名或#未知女优>/
        └── [番号] 标题/
```

目录里通常包含：

- `番号.ext`
- `番号-CD2.ext`、`番号-CD3.ext`（多文件时）
- `movie.nfo`
- `fanart.jpg`
- `thumb.jpg`
- `poster.jpg`
- `extrafanart/`

输出根目录还会生成：

- `manifest.csv`

注意：

- 原视频文件会被移动到整理目录
- 如果没拿到最小可用字段，条目不会落盘

## 已知限制

- `JavDB` 依赖本机 Chromium 浏览器登录态
- 未登录或 Cookie 失效时，`JavDB` 会自动跳过
- Docker 首版不支持普通 WebUI 的系统目录选择框
- Docker 中默认不支持 `JavDB` 登录态

## 常用环境变量

- `JAVSCRAPER_MODE`
  - `webui` / `service`
- `JAVSCRAPER_HOST`
  - 默认：`127.0.0.1`
- `JAVSCRAPER_PORT`
  - 服务模式建议固定，例如 `8765`
- `JAVSCRAPER_DISABLE_BROWSER`
  - `1/true/yes/on` 时不自动打开浏览器
- `JAVSCRAPER_PROXY_ENABLED`
- `JAVSCRAPER_PROXY_PROTOCOL`
- `JAVSCRAPER_PROXY_HOST`
- `JAVSCRAPER_PROXY_PORT`

## Docker 镜像版本说明

- 只有 `v*` tag 才会自动发布 Docker 镜像
- 稳定版示例：
  - `v0.2.1` -> `gongkeao/javscraper26:0.2.1`
- 测试版示例：
  - `v0.2.1-test1` -> `gongkeao/javscraper26:0.2.1-test1`
- 只有稳定版本 `vX.Y.Z` 会更新：
  - `gongkeao/javscraper26:latest`

## 开发者补充

如果你需要自己构建：

### 本地 Docker 构建

```bash
docker build -t javscraper26:local .
```

### Docker Compose 本地构建启动

```bash
mkdir -p docker-data/input docker-data/output
docker compose up -d
```

### Emby 插件编译

```bash
dotnet build -c Release emby-plugin/JavScraper26.EmbyPlugin/JavScraper26.EmbyPlugin.csproj
```
