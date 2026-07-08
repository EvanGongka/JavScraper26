from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from javscraper import webapp
from fastapi import HTTPException
from javscraper.service_logging import ServiceLogStore


class LaunchTests(unittest.TestCase):
    def test_service_log_store_can_mirror_entries_to_callback(self) -> None:
        mirrored = []
        store = ServiceLogStore(on_entry=mirrored.append)

        store.add("info", "startup", "ready")

        self.assertEqual(len(mirrored), 1)
        self.assertEqual(mirrored[0].level, "INFO")
        self.assertEqual(mirrored[0].source, "startup")
        self.assertEqual(mirrored[0].message, "ready")
        self.assertEqual(store.recent(limit=1)[0]["message"], "ready")

    def test_launch_uses_safe_uvicorn_config_and_opens_browser_by_default(self) -> None:
        timer = Mock()

        with (
            patch.object(webapp, "_launch_port", return_value=43210),
            patch.object(webapp, "_should_open_browser", return_value=True),
            patch.object(webapp, "_log_launch_summary") as launch_log_mock,
            patch.object(webapp.threading, "Timer", return_value=timer) as timer_factory,
            patch.object(webapp.uvicorn, "run") as run_mock,
        ):
            webapp.launch()

        launch_log_mock.assert_called_once_with("127.0.0.1", 43210, "127.0.0.1")
        timer_factory.assert_called_once()
        delay, callback = timer_factory.call_args.args
        self.assertEqual(delay, 1.2)
        self.assertTrue(callable(callback))
        timer.start.assert_called_once_with()
        run_mock.assert_called_once_with(
            webapp.app,
            host="127.0.0.1",
            port=43210,
            log_level="warning",
            access_log=False,
            log_config=None,
            use_colors=False,
        )

    def test_launch_skips_browser_when_disabled(self) -> None:
        with (
            patch.object(webapp, "_launch_port", return_value=54321),
            patch.object(webapp, "_should_open_browser", return_value=False),
            patch.object(webapp, "_log_launch_summary") as launch_log_mock,
            patch.object(webapp.threading, "Timer") as timer_factory,
            patch.object(webapp.uvicorn, "run") as run_mock,
        ):
            webapp.launch()

        launch_log_mock.assert_called_once_with("127.0.0.1", 54321, "127.0.0.1")
        timer_factory.assert_not_called()
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.kwargs["port"], 54321)

    def test_launch_summary_logs_access_urls_and_proxy_state(self) -> None:
        with patch.object(webapp, "_log_service") as log_mock:
            webapp.EMBY_SERVICE.default_proxy = webapp.ProxyConfig(
                enabled=True,
                protocol="http",
                host="127.0.0.1",
                port="7890",
            )
            with patch.object(webapp, "_should_open_browser", return_value=False):
                webapp._log_launch_summary("0.0.0.0", 8765, "127.0.0.1")

        messages = [call.args[2] for call in log_mock.call_args_list]
        self.assertTrue(any("启动服务" in message and "browser=disabled" in message for message in messages))
        self.assertTrue(any("service=http://127.0.0.1:8765/service" in message for message in messages))
        self.assertTrue(any("默认代理=http://127.0.0.1:7890" in message for message in messages))

    def test_launch_port_uses_env_override(self) -> None:
        with patch.dict("os.environ", {"JAVSCRAPER_PORT": "65432"}, clear=False):
            self.assertEqual(webapp._launch_port(), 65432)

    def test_launch_port_rejects_invalid_env_value(self) -> None:
        with patch.dict("os.environ", {"JAVSCRAPER_PORT": "abc"}, clear=False):
            with self.assertRaisesRegex(ValueError, "JAVSCRAPER_PORT must be an integer"):
                webapp._launch_port()

    def test_connectivity_filters_selected_sites(self) -> None:
        fake_client = Mock()
        with (
            patch.object(webapp, "HttpClient", return_value=fake_client),
            patch.object(webapp, "_connectivity_result_for", side_effect=lambda client, name, url: {"name": name, "url": url}),
        ):
            data = webapp.api_connectivity(webapp.ConnectivityRequest(sites=["HEYZO", "FC2"]))

        self.assertEqual(data["results"], [
            {"name": "HEYZO", "url": webapp.SITE_CONNECTIVITY_TARGETS["HEYZO"]},
            {"name": "FC2", "url": webapp.SITE_CONNECTIVITY_TARGETS["FC2"]},
        ])

    def test_connectivity_rejects_unknown_sites(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            webapp.api_connectivity(webapp.ConnectivityRequest(sites=["Nope"]))
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
