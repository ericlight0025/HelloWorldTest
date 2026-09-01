"""RG File Finder 的可重用搜尋與匯出核心。"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import yaml


class FinderError(RuntimeError):
    """表示設定、ripgrep 或匯出作業無法完成。"""


@dataclass(frozen=True)
class SearchResult:
    """一筆檔名搜尋結果。"""

    source_name: str
    source_root: Path
    file_path: Path

    @property
    def file_name(self) -> str:
        """回傳不含資料夾的檔名。"""
        return self.file_path.name


@dataclass(frozen=True)
class ExportResult:
    """記錄來源、目的地與實際複製狀態。"""

    search_result: SearchResult
    destination: Path
    copied: bool


def load_config(config_path: Path | str) -> dict[str, Any]:
    """讀取 YAML 設定檔，並確認根節點為 mapping。"""
    path = Path(config_path)
    if not path.is_file():
        raise FinderError(f"讀取設定檔失敗：找不到 {path}")
    try:
        with path.open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise FinderError(f"讀取設定檔失敗：{exc}") from exc
    if not isinstance(config, dict):
        raise FinderError("讀取設定檔失敗：YAML 根節點必須是 mapping")
    return config


def _normalise_extensions(extensions: Iterable[str]) -> set[str]:
    """將副檔名統一為不含點的小寫形式。"""
    return {str(item).strip().lower().lstrip(".") for item in extensions if str(item).strip()}


def _rg_files(source_root: Path, exclude_folders: Sequence[str], search: Mapping[str, Any]) -> list[Path]:
    """只用 ``rg --files`` 列出候選路徑，絕不讀取檔案內容。"""
    command = ["rg", "--files"]
    if bool(search.get("include_hidden", False)):
        command.append("--hidden")
    if not bool(search.get("respect_gitignore", True)):
        command.append("--no-ignore")
    for folder in exclude_folders:
        folder = str(folder).strip().strip("/\\")
        if folder:
            command.extend(["--glob", f"!**/{folder}/**"])
    try:
        completed = subprocess.run(
            command,
            cwd=source_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise FinderError("錯誤：系統找不到 ripgrep（rg）。\n請先確認：\nrg --version") from exc
    # rg 在沒有任何檔案時回傳 1，這是正常的空結果。
    if completed.returncode not in (0, 1):
        detail = completed.stderr.strip() or f"return code {completed.returncode}"
        raise FinderError(f"ripgrep 執行失敗：{detail}")
    return [source_root / line for line in completed.stdout.splitlines() if line]


def search_files(
    config: Mapping[str, Any],
    keyword: str,
    *,
    extra_excludes: Sequence[str] = (),
    extensions: Sequence[str] | None = None,
    sources: Sequence[Mapping[str, str]] | None = None,
    warning_handler: Callable[[str], None] | None = None,
) -> list[SearchResult]:
    """依檔名搜尋所有來源；可由 CLI 或未來 GUI 直接呼叫。"""
    warn = warning_handler or (lambda message: print(message))
    configured_sources = sources if sources is not None else config.get("sources", [])
    allowed = _normalise_extensions(extensions if extensions is not None else config.get("extensions", []))
    excludes = [str(value) for value in config.get("exclude_keywords", [])] + list(extra_excludes)
    exclude_folders = [str(value) for value in config.get("exclude_folders", [])]
    search_options = config.get("search", {})
    ignore_case = bool(search_options.get("ignore_case", True))
    needle = keyword.casefold() if ignore_case else keyword
    excluded_needles = [item.casefold() if ignore_case else item for item in excludes if item]
    results: list[SearchResult] = []

    for source in configured_sources:
        root = Path(str(source.get("path", ""))).expanduser()
        name = str(source.get("name") or root.name or "source")
        if not root.is_dir():
            warn(f"[警告] 搜尋資料夾不存在，略過：\n{root}")
            continue
        for file_path in _rg_files(root, exclude_folders, search_options):
            file_name = file_path.name
            compared = file_name.casefold() if ignore_case else file_name
            if file_path.suffix.lower().lstrip(".") not in allowed:
                continue
            if needle not in compared or any(item in compared for item in excluded_needles):
                continue
            results.append(SearchResult(name, root, file_path))

    return sorted(results, key=lambda item: (item.file_name.casefold(), str(item.file_path).casefold()))


def export_files(
    selected: Sequence[SearchResult],
    output_root: Path | str,
    output_config: Mapping[str, Any],
    *,
    message_handler: Callable[[str], None] | None = None,
) -> list[ExportResult]:
    """複製所選檔案，保留來源名稱以避免多專案同名檔互相覆蓋。"""
    output = Path(output_root).expanduser()
    output.mkdir(parents=True, exist_ok=True)
    preserve = bool(output_config.get("preserve_structure", True))
    overwrite = bool(output_config.get("overwrite", False))
    notify = message_handler or (lambda message: print(message))
    exported: list[ExportResult] = []

    for item in selected:
        relative = item.file_path.relative_to(item.source_root) if preserve else Path(item.file_name)
        destination = output / item.source_name / relative
        if destination.exists() and not overwrite:
            notify(f"[跳過] 已存在：{destination}")
            exported.append(ExportResult(item, destination, False))
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item.file_path, destination)
        notify(f"[複製] {destination}")
        exported.append(ExportResult(item, destination, True))
    return exported


def generate_markdown(
    output_root: Path | str,
    output_config: Mapping[str, Any],
    *,
    keyword: str,
    exclude_keywords: Sequence[str],
    extensions: Sequence[str],
    source_count: int,
    total_results: int,
    exported: Sequence[ExportResult],
) -> Path | None:
    """在輸出根目錄建立純路徑清單；不讀取或寫入任何檔案內容。"""
    if not bool(output_config.get("generate_md", True)):
        return None
    md_path = Path(output_root).expanduser() / str(output_config.get("md_filename", "search_result.md"))
    lines = [
        "# RG File Finder 搜尋結果", "", "## 搜尋條件",
        f"- 關鍵字：{keyword}",
        f"- 排除關鍵字：{', '.join(exclude_keywords) or '（無）'}",
        f"- 副檔名：{', '.join(sorted(_normalise_extensions(extensions)))}",
        f"- 搜尋來源數：{source_count}", f"- 搜尋結果：{total_results}",
        f"- 已選擇檔案：{len(exported)}", "", "---", "", "## 已選擇檔案", "",
    ]
    for index, record in enumerate(exported, 1):
        item = record.search_result
        lines.extend([
            f"### {index}. {item.file_name}", f"- Source：{item.source_name}",
            "- 原始路徑：", f"`{item.file_path}`", "- 輸出路徑：", f"`{record.destination}`",
            f"- 狀態：{'已複製' if record.copied else '已存在，略過'}", "", "---", "",
        ])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path
