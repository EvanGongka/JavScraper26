from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from javscraper import webapp
from fastapi import HTTPException


class LaunchTests(unittest.TestCase):
    def test_launch_uses_safe_uvicorn_config_and_opens_browser_by_default(self) -> None:
        timer = Mock()

        with (
            patch.object(webapp, "_launch_port", return_value=43210),
            patch.object(webapp, "_should_open_browser", return_value=True),
            patch.object(webapp.threading, "Timer", return_value=timer) as timer_factory,
            patch.object(webapp.uvicorn, "run") as run_mock,
        ):
            webapp.launch()

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
            patch.object(webapp.threading, "Timer") as timer_factory,
            patch.object(webapp.uvicorn, "run") as run_mock,
        ):
            webapp.launch()

        timer_factory.assert_not_called()
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.kwargs["port"], 54321)

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
