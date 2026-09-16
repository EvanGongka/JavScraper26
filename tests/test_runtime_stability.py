from __future__ import annotations

import asyncio
from io import BytesIO
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import requests
from fastapi.responses import Response
from PIL import Image
from starlette.requests import Request

from javscraper.images import ImageTooLargeError, select_best_native_poster, download_image_bytes
from javscraper.metadata_resolution import ResolvedMetadata
from javscraper.models import MovieMetadata, ScanEntry
from javscraper.network import HttpClient, UpstreamBusyError, UpstreamRequestLimiter
from javscraper.pipeline import ScrapePipeline
from javscraper.runtime_logging import LogSettings
from javscraper import webapp


class FakeResponse:
    def __init__(self, status_code: int = 200, content: bytes = b"ok", url: str = "https://example.com/a") -> None:
        self.status_code = status_code
        self.content = content
        self.url = url
        self.headers = {"content-type": "image/jpeg"}
        self.closed = False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")

    def close(self) -> None:
        self.closed = True


class ImageClient:
    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        self.responses = responses

    def request(self, method: str, url: str, **kwargs):
        return self.responses[url]


class PipelineProvider:
    site_name = "JavBus"

    def __init__(self, client) -> None:
        self.client = client


def image_bytes(size: tuple[int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (80, 100, 120)).save(buffer, format="JPEG")
    return buffer.getvalue()


class RuntimeStabilityTests(unittest.TestCase):
    def test_network_retries_get_and_closes_success_response(self) -> None:
        first = FakeResponse(503)
        second = FakeResponse(200, b"payload")
        client = HttpClient(
            timeout=1,
            retries=2,
            limiter=UpstreamRequestLimiter(1),
        )
        with patch("javscraper.network.get_runtime_log_writer", return_value=Mock()), patch(
            "javscraper.network.time.sleep"
        ), patch.object(client, "_request_once", side_effect=[first, second]) as request_mock:
            response = client.request("GET", "https://example.com/resource?token=secret")
        self.assertEqual(response.content, b"payload")
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)
        self.assertEqual(request_mock.call_count, 2)
        client.close()

    def test_network_retries_timeout_but_not_post(self) -> None:
        client = HttpClient(timeout=1, retries=2, limiter=UpstreamRequestLimiter(1))
        with patch("javscraper.network.get_runtime_log_writer", return_value=Mock()), patch(
            "javscraper.network.time.sleep"
        ), patch.object(
            client,
            "_request_once",
            side_effect=[requests.Timeout("temporary"), FakeResponse(200)],
        ) as request_mock:
            client.request("GET", "https://example.com/get")
        self.assertEqual(request_mock.call_count, 2)

        with patch("javscraper.network.get_runtime_log_writer", return_value=Mock()), patch.object(
            client,
            "_request_once",
            side_effect=requests.Timeout("permanent"),
        ) as post_mock:
            with self.assertRaises(requests.Timeout):
                client.request("POST", "https://example.com/post")
        self.assertEqual(post_mock.call_count, 1)
        client.close()

    def test_network_limiter_returns_explicit_busy_error(self) -> None:
        limiter = UpstreamRequestLimiter(1, wait_timeout=0)
        client = HttpClient(timeout=1, retries=0, limiter=limiter, upstream_wait_timeout=0)
        with patch("javscraper.network.get_runtime_log_writer", return_value=Mock()):
            with limiter.slot():
                with self.assertRaises(UpstreamBusyError):
                    client.request("GET", "https://example.com/busy")
        client.close()

    def test_image_limit_and_corrupt_candidate_fallback(self) -> None:
        too_large = FakeResponse(content=b"12345")
        too_large.headers["content-length"] = "5"
        with patch.dict(os.environ, {"JAVSCRAPER_MAX_IMAGE_BYTES": "4"}):
            with self.assertRaises(ImageTooLargeError):
                download_image_bytes(ImageClient({"https://example.com/large": too_large}), "https://example.com/large")
        self.assertTrue(too_large.closed)

        first = FakeResponse(content=b"not-an-image")
        second = FakeResponse(content=image_bytes((600, 900)))
        logs: list[str] = []
        with patch.dict(os.environ, {"JAVSCRAPER_MAX_IMAGE_BYTES": str(25 * 1024 * 1024)}):
            selected = select_best_native_poster(
                ImageClient(
                    {
                        "https://example.com/bad": first,
                        "https://example.com/good": second,
                    }
                ),
                ["https://example.com/bad", "https://example.com/good"],
                on_log=logs.append,
                code="ABP-123",
            )
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.url, "https://example.com/good")
        self.assertTrue(any("图片损坏" in line for line in logs))
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)

    def test_pipeline_isolates_one_entry_failure(self) -> None:
        entries = [
            ScanEntry(code="ABP-001", files=[Path("/tmp/ABP-001.mp4")]),
            ScanEntry(code="ABP-002", files=[Path("/tmp/ABP-002.mp4")]),
        ]
        statuses: dict[str, str] = {}
        errors: list[str] = []
        resolved = ResolvedMetadata(
            metadata=MovieMetadata(code="ABP-001", title="Movie", cover_url="https://example.com/a.jpg"),
            provider="JavBus",
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "javscraper.pipeline.PROVIDER_CLASSES", {"JavBus": PipelineProvider}, clear=False
        ), patch(
            "javscraper.pipeline.resolve_metadata_from_providers", return_value=resolved
        ), patch(
            "javscraper.pipeline.save_result",
            side_effect=[RuntimeError("first entry failed"), {"output_folder": "/tmp/ok"}],
        ), patch(
            "javscraper.pipeline.write_manifest", return_value=Path(temp_dir) / "manifest.csv"
        ):
            pipeline = ScrapePipeline(
                output_root=temp_dir,
                provider_names=["JavBus"],
                on_log=lambda _: None,
                on_status=statuses.__setitem__,
                on_error=lambda code, exc: errors.append(f"{code}:{exc}"),
            )
            result = pipeline.run(entries)
        self.assertTrue(result.name == "manifest.csv")
        self.assertEqual(statuses["ABP-001"], "失败")
        self.assertEqual(statuses["ABP-002"], "完成")
        self.assertEqual(len(errors), 1)

    def test_request_id_and_health_diagnostics(self) -> None:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/service",
                "headers": [(b"x-request-id", b"req-test")],
            }
        )

        async def call_next(_request):
            return Response(status_code=200)

        response = asyncio.run(webapp.service_request_logger(request, call_next))
        self.assertEqual(response.headers["X-Request-ID"], "req-test")
        self.assertTrue(any(entry.get("request_id") == "req-test" for entry in webapp.SERVICE_LOGS.recent(limit=20)))
        health = webapp.emby_health()
        for key in (
            "uptimeSeconds",
            "pid",
            "activeRequests",
            "metadataCacheEntries",
            "lastErrorAt",
            "logFileConfigured",
        ):
            self.assertIn(key, health)

    def test_task_log_limit_and_retention_cleanup(self) -> None:
        with patch.dict(
            os.environ,
            {"JAVSCRAPER_TASK_LOG_MAX_ENTRIES": "2", "JAVSCRAPER_TASK_RETENTION_SECONDS": "1"},
        ):
            task = webapp.TaskState("task-test", "/input", "/output", ["JavBus"])
            task.append_log("one")
            task.append_log("two")
            task.append_log("three")
            self.assertEqual(list(task.logs), ["two", "three"])
            task.finish(error="failed")
            task.finished_monotonic = time.monotonic() - 2
            with webapp.TASKS_LOCK:
                webapp.TASKS[task.task_id] = task
            try:
                self.assertEqual(webapp._cleanup_tasks(), 1)
                with webapp.TASKS_LOCK:
                    self.assertNotIn(task.task_id, webapp.TASKS)
            finally:
                with webapp.TASKS_LOCK:
                    webapp.TASKS.pop(task.task_id, None)


if __name__ == "__main__":
    unittest.main()
