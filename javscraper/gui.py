from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from javscraper.pipeline import ScrapePipeline
from javscraper.scanner import scan_directory


DEFAULT_SITES = [
    "JavBus",
    "JavBooks",
    "AVBASE",
    "JAV321",
    "FC2",
    "1Pondo",
    "10musume",
    "PACOPACOMAMA",
    "MURAMURA",
    "AVMOO",
    "FreeJavBT",
    "JavDB",
]


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("javScraper26")
        self.geometry("1220x760")
        self.minsize(1080, 680)
        self.configure(background="#f3f3f3")

        self.events: queue.Queue[tuple[str, tuple]] = queue.Queue()
        self.entries = []
        self.tree_items: dict[str, str] = {}

        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar()

        self._setup_style()
        self._build_layout()
        self._load_default_sites()
        self.after(150, self._drain_events)

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            if "clam" in style.theme_names():
                style.theme_use("clam")
        except tk.TclError:
            pass

    def _build_layout(self) -> None:
        top = ttk.Frame(self, padding=12)
        top.pack(fill=tk.X, padx=12, pady=(12, 8))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="扫描目录").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(top, textvariable=self.source_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(top, text="选择", command=self.choose_source).grid(row=0, column=2, padx=8)
        ttk.Button(top, text="扫描", command=self.scan).grid(row=0, column=3)

        ttk.Label(top, text="输出目录").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(10, 0))
        ttk.Entry(top, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(top, text="选择", command=self.choose_output).grid(row=1, column=2, padx=8, pady=(10, 0))
        ttk.Button(top, text="开始刮削", command=self.start_scrape).grid(row=1, column=3, pady=(10, 0))

        middle = ttk.Frame(self)
        middle.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        middle.columnconfigure(0, weight=3)
        middle.columnconfigure(1, weight=2)
        middle.rowconfigure(0, weight=1)

        left = ttk.Labelframe(middle, text="扫描结果", padding=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        columns = ("code", "count", "file", "status")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", height=16)
        self.tree.heading("code", text="番号")
        self.tree.heading("count", text="文件数")
        self.tree.heading("file", text="首文件")
        self.tree.heading("status", text="状态")
        self.tree.column("code", width=120, anchor="center")
        self.tree.column("count", width=80, anchor="center")
        self.tree.column("file", width=500)
        self.tree.column("status", width=160, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        tree_scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scrollbar.set)

        right = ttk.Labelframe(middle, text="站点顺序", padding=8)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        right.columnconfigure(2, weight=1)
        right.rowconfigure(1, weight=1)

        ttk.Label(right, text="可用站点").grid(row=0, column=0, sticky="w")
        ttk.Label(right, text="执行队列").grid(row=0, column=2, sticky="w")

        self.available_list = tk.Listbox(right, exportselection=False, height=12, relief=tk.SOLID, borderwidth=1)
        self.available_list.grid(row=1, column=0, sticky="nsew")

        buttons = ttk.Frame(right)
        buttons.grid(row=1, column=1, padx=10, sticky="ns")
        ttk.Button(buttons, text="添加 >", command=self.add_site).grid(row=0, column=0, pady=4)
        ttk.Button(buttons, text="< 移除", command=self.remove_site).grid(row=1, column=0, pady=4)
        ttk.Button(buttons, text="上移", command=self.move_up).grid(row=2, column=0, pady=12)
        ttk.Button(buttons, text="下移", command=self.move_down).grid(row=3, column=0, pady=4)

        self.selected_list = tk.Listbox(right, exportselection=False, height=12, relief=tk.SOLID, borderwidth=1)
        self.selected_list.grid(row=1, column=2, sticky="nsew")

        bottom = ttk.Labelframe(self, text="运行日志", padding=8)
        bottom.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(bottom, wrap=tk.WORD, height=12)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.configure(state="disabled")

    def _load_default_sites(self) -> None:
        for site in DEFAULT_SITES:
            self.available_list.insert(tk.END, site)
            self.selected_list.insert(tk.END, site)

    def choose_source(self) -> None:
        folder = filedialog.askdirectory(title="选择待扫描目录")
        if not folder:
            return
        self.source_var.set(folder)
        if not self.output_var.get():
            self.output_var.set(str(Path(folder) / "javScraper26-output"))

    def choose_output(self) -> None:
        folder = filedialog.askdirectory(title="选择结果输出目录")
        if folder:
            self.output_var.set(folder)

    def add_site(self) -> None:
        selection = self.available_list.curselection()
        if not selection:
            return
        site = self.available_list.get(selection[0])
        if site not in self.selected_list.get(0, tk.END):
            self.selected_list.insert(tk.END, site)

    def remove_site(self) -> None:
        selection = self.selected_list.curselection()
        if selection:
            self.selected_list.delete(selection[0])

    def move_up(self) -> None:
        selection = self.selected_list.curselection()
        if not selection or selection[0] == 0:
            return
        index = selection[0]
        value = self.selected_list.get(index)
        self.selected_list.delete(index)
        self.selected_list.insert(index - 1, value)
        self.selected_list.selection_set(index - 1)

    def move_down(self) -> None:
        selection = self.selected_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= self.selected_list.size() - 1:
            return
        value = self.selected_list.get(index)
        self.selected_list.delete(index)
        self.selected_list.insert(index + 1, value)
        self.selected_list.selection_set(index + 1)

    def scan(self) -> None:
        source = self.source_var.get().strip()
        if not source:
            messagebox.showwarning("提示", "请先选择扫描目录")
            return

        self.entries, skipped = scan_directory(source)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree_items.clear()

        for entry in self.entries:
            item_id = self.tree.insert(
                "",
                tk.END,
                values=(entry.code, entry.file_count, str(entry.primary_file.name), entry.status),
            )
            self.tree_items[entry.code] = item_id

        self.log(f"扫描完成，可识别条目: {len(self.entries)}，跳过文件: {len(skipped)}")
        for path in skipped[:20]:
            self.log(f"未识别番号，已跳过: {path}")

    def start_scrape(self) -> None:
        if not self.entries:
            messagebox.showwarning("提示", "请先扫描目录")
            return

        provider_names = list(self.selected_list.get(0, tk.END))
        if not provider_names:
            messagebox.showwarning("提示", "请至少保留一个站点")
            return

        output_root = self.output_var.get().strip()
        if not output_root:
            messagebox.showwarning("提示", "请先选择输出目录")
            return

        worker = threading.Thread(
            target=self._run_pipeline,
            args=(output_root, provider_names),
            daemon=True,
        )
        worker.start()

    def _run_pipeline(self, output_root: str, provider_names: list[str]) -> None:
        self.events.put(("log", (f"开始刮削，站点顺序: {' -> '.join(provider_names)}",)))
        pipeline = ScrapePipeline(
            output_root=output_root,
            provider_names=provider_names,
            on_log=lambda text: self.events.put(("log", (text,))),
            on_status=lambda code, status: self.events.put(("status", (code, status))),
        )
        try:
            manifest = pipeline.run(self.entries)
            self.events.put(("done", (str(manifest),)))
        except Exception as exc:
            self.events.put(("error", (str(exc),)))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self.log(*payload)
            elif kind == "status":
                self.update_status(*payload)
            elif kind == "done":
                self.log(f"任务完成，manifest: {payload[0]}")
                messagebox.showinfo("完成", f"任务完成\n{payload[0]}")
            elif kind == "error":
                self.log(f"任务失败: {payload[0]}")
                messagebox.showerror("失败", payload[0])

        self.after(150, self._drain_events)

    def update_status(self, code: str, status: str) -> None:
        item_id = self.tree_items.get(code)
        if not item_id:
            return
        values = list(self.tree.item(item_id, "values"))
        values[3] = status
        self.tree.item(item_id, values=values)

    def log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")


def launch() -> None:
    app = App()
    app.mainloop()
