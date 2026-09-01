"""RG File Finder 的可重用設定、內容搜尋與 Markdown 核心。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import yaml


class FinderError(RuntimeError):
    """表示設定、ripgrep 或輸出作業無法完成。"""


@dataclass(frozen=True)
class SearchResult:
    """一筆檔案內容搜尋結果。"""

    source_name: str
    source_root: Path
    file_path: Path
    matched_keywords: tuple[str, ...]

    @property
    def file_name(self) -> str:
        """回傳不含資料夾的檔名。"""
        return self.file_path.name


def load_config(config_path: Path | str) -> dict[str, Any]:
    """讀取並驗證 YAML 設定檔。"""
    path = Path(config_path)
    if not path.is_file():
        raise FinderError(f"YAML 設定檔不存在：{path}")
    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise FinderError("設定檔副檔名必須是 .yaml 或 .yml。")
    try:
        with path.open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
    except UnicodeError as exc:
        raise FinderError(f"YAML 必須使用 UTF-8 編碼：{exc}") from exc
    except (OSError, yaml.YAMLError) as exc:
        raise FinderError(f"YAML 解析失敗：{exc}") from exc
    validate_config(config)
    return config


def validate_config(config: Any) -> None:
    """確認內容搜尋所需的 YAML 欄位與基本型別。"""
    if not isinstance(config, dict):
        raise FinderError("YAML 根節點必須是 mapping。")
    required = ("sources", "extensions", "include_keywords", "output")
    missing = [name for name in required if name not in config]
    if missing:
        raise FinderError(f"YAML 缺少必要欄位：{', '.join(missing)}")
    for field in ("sources", "extensions", "include_keywords"):
        value = config[field]
        if not isinstance(value, list) or not value:
            raise FinderError(f"YAML 欄位 {field} 必須至少有一筆設定。")
    for index, source in enumerate(config["sources"], 1):
        if not isinstance(source, dict) or not source.get("name") or not source.get("path"):
            raise FinderError(f"sources 第 {index} 筆必須包含 name 與 path。")
    if not all(isinstance(item, str) and item.strip() for item in config["extensions"]):
        raise FinderError("extensions 每一筆都必須是非空白文字。")
    if not all(isinstance(item, str) and item for item in config["include_keywords"]):
        raise FinderError("include_keywords 每一筆都必須是非空白文字。")
    if not isinstance(config["output"], dict) or not config["output"].get("folder"):
        raise FinderError("YAML 必須設定 output.folder。")
    for optional in ("exclude_keywords", "exclude_folders"):
        if optional in config and not isinstance(config[optional], list):
            raise FinderError(f"YAML 欄位 {optional} 必須是 list。")
    if "search" in config and not isinstance(config["search"], dict):
        raise FinderError("YAML 欄位 search 必須是 mapping。")


def _normalise_extensions(extensions: Iterable[str]) -> list[str]:
    """將副檔名統一為不含點的小寫格式並去除重複。"""
    return list(dict.fromkeys(str(item).strip().lower().lstrip(".") for item in extensions))


def _build_rg_command(
    keyword: str,
    extensions: Sequence[str],
    exclude_folders: Sequence[str],
    search_options: Mapping[str, Any],
) -> list[str]:
    """建立只輸出命中檔案名稱的 ripgrep 內容搜尋命令。"""
    command = ["rg", "--files-with-matches", "--fixed-strings", "--color", "never"]
    if bool(search_options.get("ignore_case", True)):
        command.append("--ignore-case")
    if bool(search_options.get("include_hidden", False)):
        command.append("--hidden")
    if not bool(search_options.get("respect_gitignore", True)):
        command.append("--no-ignore")
    for extension in extensions:
        command.extend(["--glob", f"*.{extension}"])
    for folder in exclude_folders:
        cleaned = str(folder).strip().strip("/\\")
        if cleaned:
            command.extend(["--glob", f"!**/{cleaned}/**"])
    command.extend(["--", keyword, "."])
    return command


def _search_keyword(
    root: Path,
    keyword: str,
    extensions: Sequence[str],
    exclude_folders: Sequence[str],
    search_options: Mapping[str, Any],
) -> set[Path]:
    """在單一來源搜尋一個內容關鍵字，回傳命中的絕對路徑。"""
    command = _build_rg_command(keyword, extensions, exclude_folders, search_options)
    try:
        completed = subprocess.run(
            command, cwd=root, check=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError as exc:
        raise FinderError("系統找不到 ripgrep（rg）。請先執行 rg --version 確認安裝。") from exc
    # ripgrep 的 1 表示沒有命中，並非執行錯誤。
    if completed.returncode not in (0, 1):
        detail = completed.stderr.strip() or f"結束代碼 {completed.returncode}"
        raise FinderError(f"ripgrep 執行失敗：{detail}")
    return {(root / line.removeprefix("./")).resolve() for line in completed.stdout.splitlines() if line}


def search_files(
    config: Mapping[str, Any],
    *,
    warning_handler: Callable[[str], None] | None = None,
) -> list[SearchResult]:
    """依 YAML 搜尋檔案內容；include 採 OR，命中 exclude 則排除。"""
    validate_config(config)
    warn = warning_handler or print
    extensions = _normalise_extensions(config["extensions"])
    includes = [str(item) for item in config["include_keywords"]]
    excludes = [str(item) for item in config.get("exclude_keywords", []) if str(item)]
    exclude_folders = [str(item) for item in config.get("exclude_folders", [])]
    search_options = config.get("search", {})
    results: list[SearchResult] = []

    for source in config["sources"]:
        root = Path(str(source["path"])).expanduser()
        if not root.is_dir():
            warn(f"[警告] 搜尋資料夾不存在，略過：\n{root}")
            continue
        matched_by_file: dict[Path, list[str]] = {}
        for keyword in includes:
            for path in _search_keyword(root, keyword, extensions, exclude_folders, search_options):
                matched_by_file.setdefault(path, []).append(keyword)
        excluded_paths: set[Path] = set()
        for keyword in excludes:
            excluded_paths.update(_search_keyword(root, keyword, extensions, exclude_folders, search_options))
        for path, matched in matched_by_file.items():
            if path not in excluded_paths:
                results.append(SearchResult(str(source["name"]), root, path, tuple(matched)))

    return sorted(results, key=lambda item: (item.file_name.casefold(), str(item.file_path).casefold()))


def generate_markdown(
    config: Mapping[str, Any],
    yaml_path: Path | str,
    results: Sequence[SearchResult],
) -> Path:
    """在 output.folder 產生只有條件、路徑與命中詞的 Markdown 清單。"""
    output_config = config["output"]
    output_root = Path(str(output_config["folder"])).expanduser()
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        md_path = output_root / str(output_config.get("md_filename", "search_result.md"))
        lines = [
            "# RG Search Result", "", "## Search Conditions", "", f"YAML：  \n{yaml_path}", "",
            "Sources:", *[f"- {source['path']}" for source in config["sources"]], "",
            "Extensions:", *[f"- {item}" for item in _normalise_extensions(config["extensions"])], "",
            "Include Keywords:", *[f"- {item}" for item in config["include_keywords"]], "",
            "Exclude Keywords:", *[f"- {item}" for item in config.get("exclude_keywords", [])], "",
            "## Result", "", f"Total: {len(results)} files", "",
        ]
        for index, result in enumerate(results, 1):
            lines.extend([
                f"### {index}. {result.file_name}", "", "Source:", result.source_name, "",
                "Path:", str(result.file_path), "", "Matched Keywords:",
                *[f"- {keyword}" for keyword in result.matched_keywords], "",
            ])
        md_path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        raise FinderError(f"無法建立輸出或 Markdown：{exc}") from exc
    return md_path
