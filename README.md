# javScraper26

一个本地运行的 JAV 元数据刮削器，使用浏览器页面作为操作界面，抓取核心仍然是 Python。

当前包含两种主要使用方式：

- `普通 WebUI`
- `Emby 服务模式`

仓库内同时包含 Emby 插件子项目：

- `emby-plugin/JavScraper26.EmbyPlugin/`

## 功能概览

- 扫描本地目录并识别番号
- 按番号类型自动区分普通番号和特殊番号
- 按站点顺序逐个尝试抓取元数据
- 输出 `movie.nfo`、海报、背景图、预览图
- 按女优名和影片名整理目录结构
- 提供 Emby 可调用的电影元数据和图片接口
- 提供 Emby 插件源码和插件打包文件

## 当前支持站点

普通番号站点：

- `JavBus`
- `JAV321`
- `JavBooks`
- `AVBASE`
- `FreeJavBT`
- `AVMOO`
- `JavDB`

特殊番号站点：

- `FC2`
- `Caribbeancom`
- `CaribbeancomPR`
- `HEYZO`
- `HeyDouga`
- `1Pondo`
- `10musume`
- `PACOPACOMAMA`
- `MURAMURA`

站点执行时会自动分流：

- 普通番号只使用普通番号站点
- 特殊番号只使用特殊番号站点

## 环境要求

- `Python 3.10+`
- `pip`
- macOS / Linux 可直接运行
- Windows 可通过打包脚本生成 `.exe`

## 安装

```bash
cd javScraper26
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

也可以在安装项目后直接运行：

```bash
javscraper26
```

## 启动方式

### 启动到模式选择页

```bash
python3 app.py
```

默认行为：

- 监听地址：`127.0.0.1`
- 端口：随机空闲端口
- 自动打开浏览器
- 打开后先进入模式选择页

### 直接启动到普通 WebUI

```bash
JAVSCRAPER_MODE=webui python3 app.py
```

### 直接启动到 Emby 服务模式

```bash
JAVSCRAPER_MODE=service JAVSCRAPER_PORT=8765 python3 app.py
```

### 局域网访问或服务器后台运行

```bash
JAVSCRAPER_MODE=service \
JAVSCRAPER_HOST=0.0.0.0 \
JAVSCRAPER_PORT=8765 \
JAVSCRAPER_DISABLE_BROWSER=1 \
python3 app.py
```

## 常用环境变量

- `JAVSCRAPER_MODE`
  - 可选：`webui`、`service`
  - 不设置时显示模式选择页
- `JAVSCRAPER_HOST`
  - 默认：`127.0.0.1`
  - 局域网访问时可设为 `0.0.0.0`
- `JAVSCRAPER_PORT`
  - 不设置时随机端口
  - 服务模式通常使用固定端口，例如 `8765`
- `JAVSCRAPER_DISABLE_BROWSER`
  - `1/true/yes/on` 时不自动打开浏览器
- `JAVSCRAPER_PROXY_ENABLED`
- `JAVSCRAPER_PROXY_PROTOCOL`
- `JAVSCRAPER_PROXY_HOST`
- `JAVSCRAPER_PROXY_PORT`
  - 用于配置服务模式默认代理

## 使用方式

### 方式 1：模式选择页

访问路径：

- `/`

页面作用：

- 进入普通 WebUI
- 进入 Emby 服务模式

页面操作步骤：

1. 启动程序。
2. 浏览器打开首页后，会显示模式选择页。
3. 点击 `进入普通模式` 进入普通 WebUI。
4. 点击 `进入服务模式` 进入 Emby 服务模式。

### 模式选择页

![模式选择页](docs/images/mode-selector.png)

### 方式 2：普通 WebUI

访问路径：

- `/webui`

普通 WebUI 适合：

- 扫描本地影片目录
- 手动确认站点顺序
- 批量刮削元数据
- 整理输出目录
- 查看任务日志和每条影片状态

#### 普通 WebUI 页面结构

页面主要分为三块：

- 顶部操作区
  - `扫描目录`
  - `输出目录`
  - `开始刮削`
- 左侧站点顺序区
  - 普通番号站点
  - 特殊番号站点
  - 上移 / 下移按钮
- 右侧与下方结果区
  - 扫描结果表格
  - 运行日志

#### 普通 WebUI 的完整操作步骤

1. 启动程序并进入 `/webui`。
2. 在 `扫描目录` 一栏点击 `选择目录`。
3. 选中需要扫描的视频目录。
4. 如需自定义输出位置，在 `输出目录` 一栏点击 `选择目录`。
5. 如果不手动选择输出目录，程序会自动把输出目录补成 `扫描目录/javScraper26-output`。
6. 点击 `扫描`。
7. 页面会在 `扫描结果` 表格中列出识别出的番号、文件数、首文件和当前状态。
8. 在 `站点顺序` 区域查看当前站点顺序。
9. 如果需要调整顺序，点击某个站点右侧的 `上移` 或 `下移`。
10. 普通番号站点和特殊番号站点分组独立，只能在各自分组内调整顺序。
11. 确认扫描结果后，点击右上角 `开始刮削`。
12. 页面会弹出 `站点连通性校验` 窗口。
13. 程序会根据本次扫描出的番号类型，自动只校验本次真正会使用到的站点。
14. 查看每个站点的校验结果。
15. 如果某些站点不可访问，可以在弹窗下方填写代理参数：
    - `协议`
    - `代理地址`
    - `端口`
16. 需要重新校验时，点击 `重新校验`。
17. 校验通过或确认继续后，点击 `继续刮削`。
18. 任务开始后，表格中的每条影片会持续更新状态。
19. `运行日志` 区域会持续显示每一步操作：
    - 开始处理
    - 本次尝试站点顺序
    - 命中站点
    - 下载图片
    - 写入 NFO
    - 移动视频文件
    - 输出完成
20. 全部完成后，日志末尾会显示 `manifest.csv` 的生成位置。

#### 普通 WebUI 中各按钮的作用

- `选择目录`
  - 打开系统目录选择框
- `扫描`
  - 扫描目录中的文件并识别番号
- `开始刮削`
  - 开始执行当前扫描结果的批量任务
- `上移`
  - 将当前站点在同组内向前移动
- `下移`
  - 将当前站点在同组内向后移动
- `重新校验`
  - 使用当前代理配置重新检查站点可访问性
- `继续刮削`
  - 关闭校验阶段并正式开始任务
- `关闭`
  - 关闭连通性校验窗口

#### 普通 WebUI 的任务状态说明

- `待处理`
  - 已加入任务，尚未开始执行
- `执行中`
  - 正在抓取该条目
- `已命中 <站点名>`
  - 已经从某个站点拿到可用元数据
- `完成`
  - 已完成输出落盘
- `失败`
  - 未获得最小可用字段或任务处理失败

### 普通 WebUI 主界面

![普通 WebUI 主界面](docs/images/main-ui.png)

### 连通性校验弹窗

![站点连通性校验弹窗](docs/images/connectivity-dialog.png)

### 普通 WebUI 刮削结果

![普通 WebUI 刮削结果](docs/images/scrape-result.png)

### 方式 3：Emby 服务模式

访问路径：

- `/service`

Emby 服务模式适合：

- 给 Emby 插件提供元数据接口
- 长时间在后台运行
- 查看最近的 Emby 请求和抓取日志

#### Emby 服务模式页面内容

页面会显示：

- 服务状态
- 当前模式
- Provider 数量
- 默认代理状态
- 当前日志条数
- Emby 插件应填写的 `Server URL`
- 电影解析接口路径
- 电影详情接口路径
- 图片接口路径
- 最近日志

#### Emby 服务模式页面使用步骤

1. 使用服务模式启动程序。
2. 打开 `/service` 页面。
3. 查看 `服务状态` 是否为 `运行中`。
4. 记录页面中的 `Server URL`。
5. 确认 `默认代理` 是否符合当前网络环境。
6. 保持该页面运行，观察最近日志是否有来自 Emby 的请求。

### Emby 服务模式页面

![Emby 服务模式页面](docs/images/service-mode.png)

### 方式 4：本地交互管理脚本

脚本路径：

```bash
scripts/manage_javscraper.sh
```

#### 管理脚本可执行的操作

- 启动
- 停止
- 重启
- 查看状态
- 查看日志
- 查看当前配置

#### 管理脚本使用步骤

1. 在项目根目录执行：

```bash
bash scripts/manage_javscraper.sh
```

2. 进入菜单后，输入对应数字：
   - `1` 启动
   - `2` 停止
   - `3` 重启
   - `4` 状态
   - `5` 查看日志
   - `6` 查看当前配置
   - `0` 退出
3. 选择 `启动` 后，脚本会继续询问启动模式：
   - `1` selector
   - `2` webui
   - `3` service
4. 继续输入端口号。
5. 再选择是否自动打开浏览器。
6. 启动完成后，可通过 `状态` 查看 PID、日志位置和当前配置。

#### 管理脚本运行后会生成的文件

- `.runtime/javscraper.pid`
- `.runtime/javscraper.log`
- `.runtime/javscraper.env`

### 方式 5：局域网 / 远程服务器辅助脚本

脚本路径：

```bash
scripts/manage_javscraper_lan_server.sh
```

该脚本包含：

- 代码同步
- 远程准备 Python 环境
- 远程启动服务
- 远程停止服务
- 远程重启服务

使用前需要先按自己的服务器环境修改脚本中的固定参数：

- `SERVER_HOST`
- `SERVER_USER`
- `SERVER_PASSWORD`
- `REMOTE_ROOT`
- 默认代理配置

## Emby 服务接口

当前服务模式提供以下接口：

- `GET /emby-api/v1/health`
- `GET /emby-api/v1/logs/recent`
- `GET /emby-api/v1/movies/resolve`
- `GET /emby-api/v1/movies/{provider}/{id}`
- `GET /emby-api/v1/images/{primary|thumb|backdrop}/{provider}/{id}`

接口用途：

- `/emby-api/v1/health`
  - 健康检查
- `/emby-api/v1/logs/recent`
  - 获取最近日志
- `/emby-api/v1/movies/resolve`
  - 根据名称或路径解析番号并返回候选结果
- `/emby-api/v1/movies/{provider}/{id}`
  - 获取某个候选影片的详细元数据
- `/emby-api/v1/images/...`
  - 获取主图、缩略图和背景图

## Emby 插件使用方法

### 插件文件位置

插件源码目录：

```text
emby-plugin/JavScraper26.EmbyPlugin/
```

仓库内已包含插件打包文件：

```text
emby-plugin/JavScraper26.EmbyPlugin/bin/Emby.JavScraper26@v0.1.0.zip
```

仓库内也包含插件 DLL：

```text
emby-plugin/JavScraper26.EmbyPlugin/bin/JavScraper26.EmbyPlugin.dll
```

### 插件的工作方式

插件会在 Emby 识别电影时：

1. 读取影片条目的 `Name` 和 `Path`
2. 调用 `javScraper26` 服务模式接口解析番号
3. 获取影片详细元数据
4. 获取图片地址
5. 把元数据和图片回填给 Emby

### 插件安装步骤

#### 方法 1：安装 zip 插件包

1. 打开 Emby 管理后台。
2. 进入 `插件` 页面。
3. 进入手动安装或上传插件的入口。
4. 选择文件：

```text
emby-plugin/JavScraper26.EmbyPlugin/bin/Emby.JavScraper26@v0.1.0.zip
```

5. 安装完成后，按 Emby 提示重启服务。

#### 方法 2：手动放入 DLL

1. 停止 Emby 服务。
2. 将以下文件复制到 Emby 插件目录：

```text
emby-plugin/JavScraper26.EmbyPlugin/bin/JavScraper26.EmbyPlugin.dll
```

3. 启动 Emby 服务。
4. 打开 Emby 管理后台确认插件已加载。

### 插件编译方法

在安装了 `.NET SDK 6` 的环境中执行：

```bash
dotnet build -c Release emby-plugin/JavScraper26.EmbyPlugin/JavScraper26.EmbyPlugin.csproj
```

### 插件配置项说明

插件页面包含以下配置项：

- `Server URL`
  - `javScraper26` 服务模式的完整地址
  - 示例：`http://127.0.0.1:8765`
- `Enable Proxy`
  - 是否在插件请求时附带代理参数
- `Proxy Protocol`
  - 代理协议，例如 `http`
- `Proxy Host`
  - 代理地址，例如 `127.0.0.1`
- `Proxy Port`
  - 代理端口，例如 `7890`

### Emby 插件配置步骤

1. 先启动 `javScraper26` 的服务模式。
2. 确认服务页面可以正常打开，例如：

```text
http://127.0.0.1:8765/service
```

3. 打开 Emby 管理后台。
4. 进入 `插件`。
5. 打开 `javScraper26` 插件配置页面。
6. 在 `Server URL` 中填写服务模式地址，例如：

```text
http://127.0.0.1:8765
```

7. 如果当前网络环境需要代理，勾选 `Enable Proxy`。
8. 填写：
   - `Proxy Protocol`
   - `Proxy Host`
   - `Proxy Port`
9. 保存配置。
10. 返回 Emby 媒体库设置。
11. 确认电影库启用了远程元数据抓取。
12. 在电影条目上执行刷新元数据或重新识别。
13. 回到 `javScraper26` 的服务模式页面查看最近日志，确认请求已经进入。

### Emby 插件的典型使用流程

1. 启动 `javScraper26` 服务模式。
2. 打开服务模式页面确认状态正常。
3. 在 Emby 中安装并配置 `javScraper26` 插件。
4. 打开电影库。
5. 对单个影片执行 `识别` 或 `刷新元数据`。
6. 插件调用 `javScraper26` 解析番号。
7. `javScraper26` 返回元数据和图片。
8. Emby 写入影片标题、简介、演员、系列、Studio、海报和背景图。

### Emby 插件使用时的建议

- `Server URL` 建议填写后端服务的根地址，不要带额外路径
- 服务模式端口建议固定，避免 Emby 每次修改配置
- 如果 Emby 和 `javScraper26` 不在同一台机器，`Server URL` 应填写可互相访问的局域网地址
- 若使用局域网地址，服务端应使用：

```bash
JAVSCRAPER_HOST=0.0.0.0
```

## 代理说明

### 普通 WebUI 代理

普通 WebUI 的代理在连通性校验弹窗中填写。

填写后会用于：

- 当前批次的站点连通性检测
- 当前批次的刮削任务

### Emby 服务模式代理

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

- 插件请求中带代理参数时，优先使用插件请求级代理
- 插件未带代理参数时，使用服务端默认代理

## 输出结果

每个成功条目会输出到：

```text
<输出目录>/
└── #整理完成/
    └── <女优名或#未知女优>/
        └── [番号] 标题/
```

影片目录内通常包含：

- `番号.ext`
- `番号-CD2.ext`、`番号-CD3.ext` ...（多文件时）
- `movie.nfo`
- `fanart.jpg`
- `thumb.jpg`
- `poster.jpg`
- `extrafanart/`

输出根目录下还会生成：

- `manifest.csv`

示例：

```text
FreeJavBT/
├── #整理完成/
│   └── #未知女优/
│       └── [ABP-310] 天然成分由來 輝月杏梨汁120％/
│           ├── ABP-310.mp4
│           ├── movie.nfo
│           ├── fanart.jpg
│           ├── thumb.jpg
│           ├── poster.jpg
│           └── extrafanart/
└── manifest.csv
```

## 图片与整理规则

- 原视频文件会移动到整理目录
- `fanart.jpg` 会优先选择横图候选
- `thumb.jpg` 当前由 `fanart.jpg` 复制生成
- 普通番号会优先尝试原生海报或可裁切横图
- 特殊番号通常使用同源图片生成 `fanart / thumb / poster`
- 预览图会下载到 `extrafanart/`
- 单张预览图下载失败时会自动跳过
- 无女优信息时会归入 `#未知女优`
- 未拿到最小可用字段 `title + cover` 时不会落盘

## JavDB 说明

`JavDB` 依赖本机浏览器登录态。

当前实现会尝试读取本机 Chromium 浏览器中 `javdb.com` 的 Cookie。未登录、Cookie 过期或网络环境不满足时：

- `JavDB` 会被标记为不可用
- 普通 WebUI 的连通性结果中会显示不可用状态
- 刮削流程会自动跳过 `JavDB`
- 其他站点仍可继续执行

## 截图

### 模式选择页

![模式选择页](docs/images/mode-selector.png)

### 普通 WebUI 主界面

![普通 WebUI 主界面](docs/images/main-ui.png)

### 连通性校验弹窗

![站点连通性校验弹窗](docs/images/connectivity-dialog.png)

### 普通 WebUI 刮削结果

![普通 WebUI 刮削结果](docs/images/scrape-result.png)

### Emby 服务模式页面

![Emby 服务模式页面](docs/images/service-mode.png)

## 本地测试目录

项目中保留了本地测试输入 / 输出目录：

- `test/input/`
- `test/JavBus/`
- `test/JavDB/`
- `test/AVMOO/`
- `test/FreeJavBT/`
- `test/JavBooks/`

自动化测试目录：

- `tests/`

## 打包

### 打包 macOS `.app`

```bash
bash scripts/build_macos_app.sh
```

主要产物：

- `dist/javScraper26.app`
- `release/javScraper26-macos/`
- `release/javScraper26-macos.zip`

### 打包 Windows `.exe`

```bat
scripts\build_windows_exe.bat
```

主要产物：

- `dist\javScraper26\javScraper26.exe`
- `release\javScraper26-windows\`
- `release\javScraper26-windows.zip`

## 开源协议

本项目采用以下协议发布：

- `GPL-3.0-or-later`
- `Anti-996 License`

项目根目录已包含完整的 `LICENSE` 文件。
