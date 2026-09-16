# javScraper26

一个用于整理 JAV 影片的元数据刮削器，支持本地 WebUI 和 Emby 服务模式。

- **普通 WebUI**：扫描本地目录、批量刮削并整理影片。
- **Emby 服务模式**：为 Emby 插件提供影片元数据和图片。

## 支持的站点

普通番号：JAV321、JavBooks、AVBASE、FreeJavBT、JavBus、AVMOO、JavDB

特殊番号：FC2、Caribbeancom、CaribbeancomPR、HEYZO、HeyDouga、1Pondo、10musume、PACOPACOMAMA、MURAMURA

## 本地 WebUI

需要 Python 3.10 或更高版本。

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

### Windows

```powershell
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
python app.py
```

启动后按页面提示选择普通 WebUI，依次选择扫描目录、输出目录，扫描番号并开始刮削。

如果不选择输出目录，结果会保存到扫描目录下的 javScraper26-output。

### 页面示例

![普通 WebUI 主界面](docs/images/main-ui.png)

![站点连通性校验](docs/images/connectivity-dialog.png)

![刮削结果](docs/images/scrape-result.png)

## Docker + Emby

Docker 镜像默认为 Emby 服务模式，端口为 8765。

镜像地址：[Docker Hub](https://hub.docker.com/r/gongkeao/javscraper26)

```bash
docker pull gongkeao/javscraper26:latest
mkdir -p docker-data/input docker-data/output
docker run -d --name javscraper26 --restart unless-stopped -p 8765:8765 -v "$(pwd)/docker-data/input:/media/input" -v "$(pwd)/docker-data/output:/media/output" gongkeao/javscraper26:latest
```

启动后访问：

- 服务页面：http://127.0.0.1:8765/service
- 健康检查：http://127.0.0.1:8765/emby-api/v1/health

Docker 版只支持服务模式，不支持容器内普通 WebUI 的系统目录选择框。

## Emby 插件

1. 从 [GitHub Releases](https://github.com/EvanGongka/JavScraper26/releases) 下载最新的 Emby 插件 zip。
2. 在 Emby 管理后台进入“插件”，手动上传 zip 并重启 Emby。
3. 打开插件设置，填写服务地址并保存。
4. 在 Emby 电影库中执行识别或刷新元数据。

插件配置：

| 配置项 | 说明 |
| --- | --- |
| Server URL | javScraper26 服务地址，例如 http://127.0.0.1:8765 |
| Enable Proxy | 是否让插件请求通过代理 |
| Proxy Protocol | 代理协议，例如 http |
| Proxy Host | 代理地址 |
| Proxy Port | 代理端口 |

如果 Emby 在 Docker 容器中，127.0.0.1 指向 Emby 容器本身，请改填宿主机 IP 或同一 Compose 网络中的服务名。不同机器部署时填写 http://<服务器IP>:8765，并先从 Emby 所在机器确认健康检查地址可访问。

## 代理配置

代理可以直接填写在 Emby 插件中，也可以配置在服务端。插件请求中的代理优先；插件未填写时，服务端使用以下环境变量：

```text
JAVSCRAPER_PROXY_ENABLED=true
JAVSCRAPER_PROXY_PROTOCOL=http
JAVSCRAPER_PROXY_HOST=127.0.0.1
JAVSCRAPER_PROXY_PORT=7890
```

普通 WebUI 的代理在站点连通性校验页面中填写，只对当前批次生效。

## 输出结果

普通 WebUI 的结果目录结构如下：

```text
输出目录/
└── #整理完成/
    └── 女优名/
        └── [番号] 标题/
            ├── 番号.ext
            ├── movie.nfo
            ├── poster.jpg
            ├── fanart.jpg
            └── thumb.jpg
```

原视频会移动到整理后的目录，输出根目录还会生成 manifest.csv。

## 已知限制

- JavDB 需要本机 Chromium 浏览器已有登录态；未登录或 Cookie 失效时会跳过。
- Docker 中不读取 JavDB 浏览器登录态。
- Docker 首版面向 Emby 服务模式，不提供普通 WebUI 的目录选择交互。

## 高级文档

- [Docker 故障排查与日志](docs/docker-troubleshooting.md)
- [维护者与发布说明](docs/maintainer.md)
