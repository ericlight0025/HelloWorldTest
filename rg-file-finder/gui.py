"""RG File Finder 圖形介面。

保留既有 CLI，不修改 finder.py 核心；此 GUI 直接重用 load_config、search_files、
export_files 與 generate_markdown。
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from finder import (
    ExportResult,
    FinderError,
    SearchResult,
    export_files,
    generate_markdown,
    load_config,
    search_files,
)


class RGFileFinderGUI(tk.Tk):
    """RG File Finder 的桌面圖形介面。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("RG File Finder")
        self.geometry("1180x760")
        self.minsize(900, 600)

        self.config_path: Path | None = None
        self.config_data: dict[str, Any] | None = None
        self.raw_yaml = ""
        self.results: list[SearchResult] = []
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()

        self._build_ui()
        self._set_status("請先載入 YAML 設定檔。")
        self.after(50, self._drain_events)

    def _build_ui(self) -> None:
        """建立主畫面。"""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=10)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Button(top, text="載入 YAML", command=self.load_yaml).grid(row=0, column=0, padx=(0, 8))

        self.yaml_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.yaml_var, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=(0, 8)
        )

        ttk.Button(top, text="查看 YAML", command=self.view_yaml).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(top, text="執行搜尋", command=self.run_search).grid(row=0, column=3)

        action = ttk.Frame(self, padding=(10, 0, 10, 8))
        action.grid(row=1, column=0, sticky="ew")

        ttk.Button(action, text="全選", command=self.select_all).pack(side="left")
        ttk.Button(action, text="取消全選", command=self.clear_selection).pack(side="left", padx=(8, 0))
        ttk.Button(action, text="複製選取檔案", command=self.copy_selected).pack(side="left", padx=(16, 0))

        self.count_var = tk.StringVar(value="搜尋結果：0")
        ttk.Label(action, textvariable=self.count_var).pack(side="right")

        table_frame = ttk.Frame(self, padding=(10, 0, 10, 0))
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("no", "source", "file", "keywords", "path")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("no", text="#")
        self.tree.heading("source", text="Source")
        self.tree.heading("file", text="File")
        self.tree.heading("keywords", text="Matched Keywords")
        self.tree.heading("path", text="Path")

        self.tree.column("no", width=55, minwidth=45, anchor="center", stretch=False)
        self.tree.column("source", width=130, minwidth=100)
        self.tree.column("file", width=220, minwidth=140)
        self.tree.column("keywords", width=220, minwidth=140)
        self.tree.column("path", width=520, minwidth=260)

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        bottom = ttk.Frame(self, padding=10)
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar()
        ttk.Label(bottom, textvariable=self.status_var).grid(row=0, column=0, sticky="w")

        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=180)
        self.progress.grid(row=0, column=1, sticky="e")

    def _set_status(self, message: str) -> None:
        """更新狀態列。"""
        self.status_var.set(message)

    def _set_busy(self, busy: bool) -> None:
        """切換忙碌狀態。"""
        if busy:
            self.progress.start(10)
        else:
            self.progress.stop()

    def _drain_events(self) -> None:
        """只在 Tk 主執行緒處理背景工作結果，避免跨執行緒操作 GUI。"""
        try:
            while True:
                event, payload = self._events.get_nowait()
                if event == "search_failed":
                    self._search_failed(str(payload))
                elif event == "search_finished":
                    results, warnings = payload
                    self._search_finished(results, warnings)
                elif event == "copy_failed":
                    self._copy_failed(str(payload))
                elif event == "copy_finished":
                    exported, md_path, messages = payload
                    self._copy_finished(exported, md_path, messages)
        except queue.Empty:
            pass

        if self.winfo_exists():
            self.after(50, self._drain_events)

    def load_yaml(self) -> None:
        """讓使用者選取 YAML 並載入設定。"""
        selected = filedialog.askopenfilename(
            title="選擇 YAML 設定檔",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if not selected:
            return

        path = Path(selected)
        try:
            config = load_config(path)
            raw_yaml = path.read_text(encoding="utf-8")
        except (FinderError, OSError, UnicodeError) as exc:
            messagebox.showerror("載入失敗", str(exc))
            return

        self.config_path = path
        self.config_data = config
        self.raw_yaml = raw_yaml
        self.yaml_var.set(str(path))
        self.results = []
        self._refresh_results()
        self._set_status("YAML 載入完成，可以執行搜尋。")

    def view_yaml(self) -> None:
        """以獨立視窗顯示目前 YAML 原始內容。"""
        if self.config_path is None:
            messagebox.showinfo("提示", "請先載入 YAML 設定檔。")
            return

        window = tk.Toplevel(self)
        window.title(f"YAML - {self.config_path.name}")
        window.geometry("820x620")
        window.rowconfigure(0, weight=1)
        window.columnconfigure(0, weight=1)

        text = tk.Text(window, wrap="none")
        y_scroll = ttk.Scrollbar(window, orient="vertical", command=text.yview)
        x_scroll = ttk.Scrollbar(window, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        text.insert("1.0", self.raw_yaml)
        text.configure(state="disabled")

    def run_search(self) -> None:
        """在背景執行內容搜尋，避免 GUI 搜尋時凍結。"""
        if self.config_data is None:
            messagebox.showinfo("提示", "請先載入 YAML 設定檔。")
            return

        self._set_busy(True)
        self._set_status("搜尋中…")

        thread = threading.Thread(target=self._search_worker, daemon=True)
        thread.start()

    def _search_worker(self) -> None:
        """背景搜尋工作。"""
        assert self.config_data is not None
        warnings: list[str] = []

        try:
            results = search_files(self.config_data, warning_handler=warnings.append)
        except FinderError as exc:
            self._events.put(("search_failed", str(exc)))
            return

        self._events.put(("search_finished", (results, warnings)))

    def _search_failed(self, message: str) -> None:
        """處理搜尋錯誤。"""
        self._set_busy(False)
        self._set_status("搜尋失敗。")
        messagebox.showerror("搜尋失敗", message)

    def _search_finished(self, results: list[SearchResult], warnings: list[str]) -> None:
        """顯示搜尋結果。"""
        self._set_busy(False)
        self.results = results
        self._refresh_results()

        if warnings:
            messagebox.showwarning("搜尋警告", "\n\n".join(warnings))

        if not results:
            self._set_status("搜尋完成：0 筆。")
            self._generate_empty_markdown()
            return

        self._set_status(f"搜尋完成：{len(results)} 筆。可多選後複製。")

    def _refresh_results(self) -> None:
        """重新填入結果表格。"""
        self.tree.delete(*self.tree.get_children())

        for index, item in enumerate(self.results, 1):
            self.tree.insert(
                "",
                "end",
                iid=str(index - 1),
                values=(
                    index,
                    item.source_name,
                    item.file_name,
                    ", ".join(item.matched_keywords),
                    str(item.file_path),
                ),
            )

        self.count_var.set(f"搜尋結果：{len(self.results)}")

    def select_all(self) -> None:
        """選取所有搜尋結果。"""
        items = self.tree.get_children()
        if items:
            self.tree.selection_set(items)

    def clear_selection(self) -> None:
        """取消所有選取。"""
        self.tree.selection_remove(self.tree.selection())

    def copy_selected(self) -> None:
        """複製 GUI 中選取的多筆檔案並產生 Markdown。"""
        if self.config_data is None or self.config_path is None:
            messagebox.showinfo("提示", "請先載入 YAML 並執行搜尋。")
            return

        selected_ids = self.tree.selection()
        if not selected_ids:
            messagebox.showinfo("提示", "請先選取至少一個檔案。")
            return

        selected = [self.results[int(item_id)] for item_id in selected_ids]
        self._set_busy(True)
        self._set_status(f"正在複製 {len(selected)} 個檔案…")

        thread = threading.Thread(target=self._copy_worker, args=(selected,), daemon=True)
        thread.start()

    def _copy_worker(self, selected: list[SearchResult]) -> None:
        """背景複製與 Markdown 產生工作。"""
        assert self.config_data is not None
        assert self.config_path is not None

        messages: list[str] = []
        try:
            exported = export_files(
                selected,
                self.config_data["output"],
                message_handler=messages.append,
            )
            md_path = generate_markdown(
                config=self.config_data,
                yaml_path=self.config_path,
                total_results=len(self.results),
                exported=exported,
            )
        except FinderError as exc:
            self._events.put(("copy_failed", str(exc)))
            return

        self._events.put(("copy_finished", (exported, md_path, messages)))

    def _copy_failed(self, message: str) -> None:
        """處理複製錯誤。"""
        self._set_busy(False)
        self._set_status("複製失敗。")
        messagebox.showerror("複製失敗", message)

    def _copy_finished(
        self,
        exported: list[ExportResult],
        md_path: Path,
        messages: list[str],
    ) -> None:
        """顯示複製摘要。"""
        self._set_busy(False)
        copied = sum(1 for item in exported if item.copied)
        skipped = len(exported) - copied
        self._set_status(f"完成：已複製 {copied}，略過 {skipped}。")

        detail = "\n".join(messages[-8:])
        if detail:
            detail = f"\n\n{detail}"

        messagebox.showinfo(
            "完成",
            f"已選擇：{len(exported)}\n"
            f"已複製：{copied}\n"
            f"略過：{skipped}\n"
            f"Markdown：{md_path}{detail}",
        )

    def _generate_empty_markdown(self) -> None:
        """搜尋 0 筆時仍產生空的 Markdown 報告。"""
        if self.config_data is None or self.config_path is None:
            return

        try:
            md_path = generate_markdown(
                config=self.config_data,
                yaml_path=self.config_path,
                total_results=0,
                exported=[],
            )
        except FinderError as exc:
            messagebox.showwarning("Markdown 產生失敗", str(exc))
            return

        self._set_status(f"搜尋完成：0 筆。已產生 {md_path}")


def main() -> None:
    """啟動 GUI。"""
    app = RGFileFinderGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
