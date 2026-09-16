from javscraper.runtime_logging import configure_bootstrap_logging, traceback_text


def main() -> None:
    writer = configure_bootstrap_logging()
    writer.emit("INFO", "bootstrap", "进程启动，准备加载应用", event="process.start")
    try:
        from javscraper.webapp import launch

        launch()
    except BaseException as exc:
        writer.emit(
            "CRITICAL",
            "bootstrap",
            f"进程因致命异常退出: {exc}",
            event="process.fatal",
            exception_type=type(exc).__name__,
            traceback=traceback_text(exc),
        )
        raise


if __name__ == "__main__":
    main()
