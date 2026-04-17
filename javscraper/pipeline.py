from __future__ import annotations

from pathlib import Path
from typing import Callable

from javscraper.metadata_resolution import resolve_metadata_from_providers
from javscraper.models import ScanEntry
from javscraper.network import HttpClient
from javscraper.output import save_result, write_manifest
from javscraper.providers import PROVIDER_CLASSES


LogCallback = Callable[[str], None]
StatusCallback = Callable[[str, str], None]


class ScrapePipeline:
    def __init__(
        self,
        output_root: str | Path,
        provider_names: list[str],
        on_log: LogCallback,
        on_status: StatusCallback,
        proxy_url: str | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.on_log = on_log
        self.on_status = on_status
        self.shared_client = HttpClient(proxy_url=proxy_url)
        self.providers = [PROVIDER_CLASSES[name](self.shared_client) for name in provider_names]

    def run(self, entries: list[ScanEntry]) -> Path:
        manifest_rows: list[dict] = []

        for entry in entries:
            self.on_status(entry.code, "执行中")
            self.on_log(f"[{entry.code}] 开始处理，共 {entry.file_count} 个文件")
            resolved = resolve_metadata_from_providers(
                entry.code,
                self.providers,
                probe_client=self.shared_client,
                on_info=self.on_log,
                on_warn=self.on_log,
                on_error=self.on_log,
            )

            if resolved is None or not resolved.metadata.is_usable:
                self.on_status(entry.code, "失败")
                self.on_log(f"[{entry.code}] 未拿到最小可用字段(title + cover)，已跳过落盘")
                continue

            metadata = resolved.metadata
            self.on_status(entry.code, f"已命中 {resolved.provider}")
            row = save_result(self.shared_client, self.output_root, entry, metadata, self.on_log)
            manifest_rows.append(row)
            self.on_status(entry.code, "完成")
            self.on_log(f"[{entry.code}] 已输出到: {row['output_folder']}")

        manifest_path = write_manifest(manifest_rows, self.output_root)
        self.on_log(f"任务结束，清单文件: {manifest_path}")
        return manifest_path
