from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr

from javscraper.runtime_logging import LogSettings, RuntimeLogWriter, RuntimeMonitor, redact_text, redact_url
from javscraper.service_logging import ServiceLogStore


class RuntimeLoggingTests(unittest.TestCase):
    def test_redaction_keeps_local_paths_and_removes_url_secrets(self) -> None:
        self.assertEqual(redact_url("https://example.com/image.jpg?token=secret&x=1"), "https://example.com/image.jpg")
        self.assertEqual(redact_url("http://user:password@example.com:8080"), "http://[REDACTED]@example.com:8080")
        result = redact_text("path=/media/input/file.mp4 token=secret Cookie=session-value")
        self.assertIn("/media/input/file.mp4", result)
        self.assertNotIn("session-value", result)
        self.assertNotIn("token=secret", result)

    def test_writer_outputs_text_and_jsonl_with_structured_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "javscraper.log"
            stream = io.StringIO()
            writer = RuntimeLogWriter(
                LogSettings(file_path=str(path), max_bytes=1024 * 1024, backup_count=2),
                stream=stream,
            )
            writer.emit(
                "ERROR",
                "network",
                "请求 https://example.com/a.jpg?token=secret",
                event="upstream.request.failed",
                request_id="req-1",
                task_id="task-1",
                code="ABP-123",
                provider="JavBus",
                duration_ms=12.34,
                exception_type="TimeoutError",
                traceback="Cookie=session-value\n/var/lib/javscraper/input/file.mp4",
                details={"path": "/media/input/file.mp4", "password": "secret"},
            )

            text = stream.getvalue()
            self.assertIn("ERROR network", text)
            self.assertIn("request_id=req-1", text)
            record = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["event"], "upstream.request.failed")
            self.assertEqual(record["request_id"], "req-1")
            self.assertIn("/media/input/file.mp4", path.read_text(encoding="utf-8"))
            self.assertEqual(record["details"]["password"], "[REDACTED]")
            self.assertNotIn("token=secret", path.read_text(encoding="utf-8"))
            self.assertNotIn("session-value", path.read_text(encoding="utf-8"))

    def test_writer_rotates_jsonl_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "javscraper.log"
            writer = RuntimeLogWriter(
                LogSettings(file_path=str(path), max_bytes=250, backup_count=2),
                stream=io.StringIO(),
            )
            for index in range(12):
                writer.emit("INFO", "test", f"日志 {index}" * 10)
            self.assertTrue(path.exists())
            self.assertTrue(path.with_name("javscraper.log.1").exists())
            for candidate in path.parent.glob("javscraper.log*"):
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    json.loads(line)

    def test_file_failure_only_warns_and_keeps_stdout_working(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            blocked_parent = Path(temp_dir) / "blocked"
            blocked_parent.write_text("not a directory", encoding="utf-8")
            stream = io.StringIO()
            writer = RuntimeLogWriter(
                LogSettings(file_path=str(blocked_parent / "javscraper.log")),
                stream=stream,
            )
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                writer.emit("INFO", "test", "仍然可用")
                writer.emit("INFO", "test", "继续运行")
            self.assertIn("仍然可用", stream.getvalue())
            self.assertEqual(stderr.getvalue().count("日志文件写入失败"), 1)

    def test_service_log_optional_fields_are_backward_compatible(self) -> None:
        mirrored = []
        store = ServiceLogStore(on_entry=mirrored.append)
        store.add(
            "ERROR",
            "test",
            "failure token=secret",
            event="test.failed",
            request_id="req-2",
            task_id="task-2",
            code="ABP-123",
            provider="JavBus",
            duration_ms=3.2,
            exception_type="ValueError",
            traceback="stack",
            details={"password": "secret"},
        )
        recent = store.recent(limit=1)[0]
        self.assertEqual(recent["message"], "failure token=[REDACTED]")
        self.assertEqual(recent["event"], "test.failed")
        self.assertNotIn("traceback", recent)
        self.assertEqual(mirrored[0].to_dict(include_traceback=True)["traceback"], "stack")
        self.assertEqual(store.recent(limit=0), [])

    def test_monitor_emits_a_structured_heartbeat(self) -> None:
        class Writer:
            def __init__(self) -> None:
                self.calls = []

            def emit(self, *args, **kwargs) -> None:
                self.calls.append((args, kwargs))

        writer = Writer()
        monitor = RuntimeMonitor(lambda: {"taskCount": 2}, interval=60, writer=writer)
        monitor.emit_heartbeat()
        self.assertEqual(writer.calls[0][0][:2], ("INFO", "heartbeat"))
        self.assertTrue(writer.calls[0][0][2].startswith("运行心跳:"))
        self.assertEqual(writer.calls[0][1]["event"], "runtime.heartbeat")
        self.assertEqual(writer.calls[0][1]["details"]["taskCount"], 2)


if __name__ == "__main__":
    unittest.main()
