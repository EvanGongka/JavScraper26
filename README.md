# javScraper26

一个本地运行的 JAV 元数据刮削器，界面使用浏览器页面呈现，抓取核心仍然是 Python。

当前内置的五个站点：

- `JavBus`
- `JavDB`
- `AVMOO`
- `FreeJavBT`
- `JavBooks`

## 运行

```bash
cd javScraper26
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

## Web 界面功能

- 选择待扫描目录
- 选择结果输出目录
- 扫描视频文件并识别番号
- 通过上移/下移编排站点执行顺序
- 按顺序逐站刮削
- 在浏览器界面中查看日志和逐条状态

## 输出结果

当前输出结构已经调整为常见刮削整理工具的目录方式。

每个站点的输出目录下会生成：

- `#整理完成/`
- `#整理完成/女优名/`
- `#整理完成/女优名/[番号] 标题/`

影片目录中默认包含：

- `番号.ext`
- `movie.nfo`
- `fanart.jpg`
- `poster.jpg`
- `extrafanart/`

站点根目录下还会生成：

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
│           ├── poster.jpg
│           └── extrafanart/
└── manifest.csv
```

## 当前行为说明

- 当前会将原视频文件移动到整理目录
- `poster.jpg` 目前直接由 `fanart.jpg` 复制生成，还没有接入单独裁剪逻辑
- `extrafanart/` 会尽量下载站点提供的预览图，失败的单张会自动跳过
- 没有女优信息时会落到 `#未知女优`

## 本地测试

项目内已经有一套本地测试输出目录：

- `test/input/`
- `test/JavBus/`
- `test/JavDB/`
- `test/AVMOO/`
- `test/FreeJavBT/`
- `test/JavBooks/`

如果想脚本化重跑，可以复用当前思路：

1. 把待测文件放进 `test/input/`
2. 逐站点创建 `ScrapePipeline`
3. 把输出目录指向 `test/<站点名>/`

## JavDB 说明

`JavDB` 站点依赖浏览器 Cookie。

当前实现会优先尝试读取本机 Chromium 浏览器中 `javdb.com` 的 Cookie。如果浏览器未登录、Cookie 已过期，`JavDB` provider 会失败，但不会阻断其他站点继续执行。

实际运行时还要注意：

- `JavDB` 成功率受浏览器登录态、`cf_clearance` 和当前网络环境影响
- 某些站点会出现站点侧限流、连接中断或部分影片缺失，这属于真实网络结果，不一定是代码错误

## 开源协议

本项目采用以下协议发布：

- `GPL-3.0-or-later`
- `Anti-996 License`

项目根目录已包含完整的 `LICENSE` 文件。

这样处理的目的，是让项目当前的实现方式、再分发方式和许可证约束保持一致，也避免后续改成更宽松协议时带来的不确定风险。

如果你分发源码、打包产物或修改后的版本，建议一并保留：

- `LICENSE`
- `README.md`

## 打包 macOS 应用

当前项目已经可以在 macOS 上打包为 `.app`。

项目内已提供打包脚本：

```bash
scripts/build_macos_app.sh
```

默认产物路径：

```text
dist/javScraper26.app
```

补充说明：

- `build/` 目录只是 PyInstaller 的中间构建目录，不要直接运行里面的可执行文件
- 实际应运行 `dist/javScraper26.app`，或者目录版产物 `dist/javScraper26/javScraper26`
- 新版应用启动后，会在本机启动一个本地服务，并自动打开浏览器界面
- 当前打包脚本会优先使用 `/usr/bin/python3`
- 脚本会把 `webui/` 静态页面一起打进应用包
- 另外还会生成一个目录版产物：`dist/javScraper26/`

## 打包 Windows EXE

当前工作环境是 macOS，不能直接产出 Windows `.exe`。

项目内已提供 Windows 打包脚本和 `PyInstaller` 依赖，需在 Windows 机器上执行：

```bat
scripts\build_windows_exe.bat
```

Windows 打包完成后，产物默认在：

```text
dist\javScraper26\javScraper26.exe
```
