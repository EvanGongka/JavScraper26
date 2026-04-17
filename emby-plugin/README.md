# javScraper26 Emby Plugin

这个目录包含给 Emby 4.9.x 使用的 `.NET 6` 插件子项目。

插件职责很薄：

- 从 Emby 电影条目读取 `Name` / `Path`
- 调用 `javScraper26` 的服务模式接口解析番号并获取电影元数据
- 把结果映射回 Emby 的 `Movie` 与远程图片

典型配置：

- `Server URL`: `http://127.0.0.1:8765`
- 可选代理：`Protocol` / `Host` / `Port`

当前工作区没有安装 `dotnet`，因此这里的插件代码还没有在本机完成编译验证。建议在安装了 `.NET SDK 6` 的机器或 CI 中执行：

```bash
dotnet build emby-plugin/JavScraper26.EmbyPlugin/JavScraper26.EmbyPlugin.csproj
```
