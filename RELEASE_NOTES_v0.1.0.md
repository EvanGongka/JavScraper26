# javScraper26 v0.1.0

首个公开版本发布。

## 主要功能

- 本地运行的 JAV 元数据刮削器
- 浏览器 Web UI
- Python 抓取核心
- 支持 5 个站点：
  - `JavBus`
  - `JavBooks`
  - `AVMOO`
  - `FreeJavBT`
  - `JavDB`
- 站点可排序，按顺序依次尝试
- 命中一个站点后停止继续尝试后续站点
- 刮削前自动执行站点连通性检测
- 支持应用内代理配置
- 支持 `JavDB` 登录态检测
- 输出目录结构：
  - `#整理完成/女优名/[番号] 标题/`
- 生成：
  - 视频文件
  - `movie.nfo`
  - `fanart.jpg`
  - `poster.jpg`
  - `extrafanart/`

## 当前行为

- 当前默认会将原视频文件移动到整理目录
- `poster.jpg` 目前直接由 `fanart.jpg` 复制生成，尚未接入单独裁剪逻辑
- `JavDB` 依赖浏览器登录态与 Cookie 有效性
- 部分站点可访问性受网络环境、代理、全局代理或 TUN 模式影响

## macOS 产物

本次发布附带：

- `javScraper26-macos.zip`

## 开源协议

- `GPL-3.0-or-later`
- `Anti-996 License`
