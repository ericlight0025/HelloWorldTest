"""RG File Finder 的可重用設定、內容搜尋、匯出與 Markdown 核心。"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import yaml


class FinderError(RuntimeError):
    """表示設定、ripgrep、匯出或 Markdown 作業無法完成。"""


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


@dataclass(frozen=True)
class ExportResult:
    """記錄一筆選取檔案的輸出狀態。"""

    search_result: SearchResult
    destination: Path
    copied: bool
    reason: str | None = None


def _validate_safe_component(value: Any, field_name: str) -> str:
    """驗證只能作為單一檔名或資料夾名稱的文字，避免路徑穿越。"""
    if not isinstance(value, str) or not value.strip():
        raise FinderError(f"{field_name} 必須是非空白文字。")

    text = value.strip()
    if text in {".", ".."} or "/" in text or "\\" in text or ":" in text or "\x00" in text:
        raise FinderError(f"{field_name} 不可包含路徑、磁碟代號或特殊路徑字元：{value}")
    return text


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
    """確認內容搜尋與輸出所需的 YAML 欄位與基本型別。"""
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
        _validate_safe_component(source["name"], f"sources 第 {index} 筆 name")
        if not isinstance(source["path"], str) or not source["path"].strip():
            raise FinderError(f"sources 第 {index} 筆 path 必須是非空白文字。")

    if not all(isinstance(item, str) and item.strip() for item in config["extensions"]):
        raise FinderError("extensions 每一筆都必須是非空白文字。")

    if not all(isinstance(item, str) and item.strip() for item in config["include_keywords"]):
        raise FinderError("include_keywords 每一筆都必須是非空白文字。")

    for optional in ("exclude_keywords", "exclude_folders"):
        if optional in config:
            value = config[optional]
            if not isinstance(value, list):
                raise FinderError(f"YAML 欄位 {optional} 必須是 list。")
            if not all(isinstance(item, str) for item in value):
                raise FinderError(f"YAML 欄位 {optional} 每一筆都必須是文字。")

    search = config.get("search", {})
    if not isinstance(search, dict):
        raise FinderError("YAML 欄位 search 必須是 mapping。")
    for option in ("ignore_case", "include_hidden", "respect_gitignore"):
        if option in search and not isinstance(search[option], bool):
            raise FinderError(f"search.{option} 必須是 true 或 false。")

    output = config["output"]
    if not isinstance(output, dict) or not output.get("folder"):
        raise FinderError("YAML 必須設定 output.folder。")
    if not isinstance(output["folder"], str) or not output["folder"].strip():
        raise FinderError("output.folder 必須是非空白文字。")

    for option in ("preserve_structure", "overwrite"):
        if option in output and not isinstance(output[option], bool):
            raise FinderError(f"output.{option} 必須是 true 或 false。")

    if "md_filename" in output:
        _validate_safe_component(output["md_filename"], "output.md_filename")


def _normalise_extensions(extensions: Iterable[str]) -> list[str]:
    """將副檔名統一為不含點的小寫格式並去除重複。"""
    normalised = (str(item).strip().lower().lstrip(".") for item in extensions)
    return list(dict.fromkeys(item for item in normalised if item))


def _build_rg_command(
    keyword: str,
    extensions: Sequence[str],
    exclude_folders: Sequence[str],
    search_options: Mapping[str, Any],
) -> list[str]:
    """建立只輸出命中檔名的 ripgrep 內容搜尋命令。"""
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
    """在單一來源搜尋一個內容關鍵字，回傳命中的絕對路徑集合。"""
    command = _build_rg_command(keyword, extensions, exclude_folders, search_options)
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise FinderError("系統找不到 ripgrep（rg）。請先執行 rg --version 確認安裝。") from exc
    except OSError as exc:
        raise FinderError(f"ripgrep 無法啟動：{exc}") from exc

    if completed.returncode not in (0, 1):
        detail = completed.stderr.strip() or f"結束代碼 {completed.returncode}"
        raise FinderError(f"ripgrep 執行失敗：{detail}")

    return {
        (root / line.removeprefix("./")).resolve()
        for line in completed.stdout.splitlines()
        if line.strip()
    }


def search_files(
    config: Mapping[str, Any],
    *,
    warning_handler: Callable[[str], None] | None = None,
) -> list[SearchResult]:
    """依 YAML 搜尋檔案內容；include 採 OR，命中 exclude 則排除。"""
    validate_config(config)

    warn = warning_handler or print
    extensions = _normalise_extensions(config["extensions"])
    includes = [str(item).strip() for item in config["include_keywords"] if str(item).strip()]
    excludes = [str(item).strip() for item in config.get("exclude_keywords", []) if str(item).strip()]
    exclude_folders = [str(item) for item in config.get("exclude_folders", [])]
    search_options = config.get("search", {})
    results: list[SearchResult] = []

    for source in config["sources"]:
        root = Path(str(source["path"])).expanduser()
        if not root.is_dir():
            warn(f"[警告] 搜尋資料夾不存在，略過：\n{root}")
            continue

        root = root.resolve()
        matched_by_file: dict[Path, list[str]] = {}

        for keyword in includes:
            for path in _search_keyword(root, keyword, extensions, exclude_folders, search_options):
                matched_by_file.setdefault(path, []).append(keyword)

        excluded_paths: set[Path] = set()
        for keyword in excludes:
            excluded_paths.update(
                _search_keyword(root, keyword, extensions, exclude_folders, search_options)
            )

        for path, matched_keywords in matched_by_file.items():
            if path in excluded_paths:
                continue

            unique_keywords = tuple(dict.fromkeys(matched_keywords))
            results.append(
                SearchResult(
                    source_name=str(source["name"]),
                    source_root=root,
                    file_path=path,
                    matched_keywords=unique_keywords,
                )
            )

    return sorted(
        results,
        key=lambda item: (item.file_name.casefold(), str(item.file_path).casefold()),
    )


def export_files(
    selected: Sequence[SearchResult],
    output_config: Mapping[str, Any],
    *,
    message_handler: Callable[[str], None] | None = None,
) -> list[ExportResult]:
    """複製所選檔案，保留 source 層以避免不同來源的同名檔互相覆蓋。"""
    output_root = Path(str(output_config["folder"])).expanduser()
    preserve = bool(output_config.get("preserve_structure", True))
    overwrite = bool(output_config.get("overwrite", False))
    notify = message_handler or print

    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise FinderError(f"無法建立輸出資料夾：{exc}") from exc

    exported: list[ExportResult] = []

    for item in selected:
        source_name = _validate_safe_component(item.source_name, "source_name")
        try:
            relative = item.file_path.relative_to(item.source_root) if preserve else Path(item.file_name)
            destination = output_root / source_name / relative

            if destination.exists() and not overwrite:
                reason = "Already Exists"
                notify(f"[跳過] 已存在：{destination}")
                exported.append(ExportResult(item, destination, False, reason))
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.file_path, destination)
            notify(f"[複製] {destination}")
            exported.append(ExportResult(item, destination, True, None))

        except (OSError, ValueError) as exc:
            raise FinderError(f"複製檔案失敗：{item.file_path}\n{exc}") from exc

    return exported


def generate_markdown(
    *,
    config: Mapping[str, Any],
    yaml_path: Path | str,
    total_results: int,
    exported: Sequence[ExportResult],
) -> Path:
    """在 output.folder 產生搜尋條件、摘要與選取檔案的 Markdown 報告。"""
    validate_config(config)
    output_config = config["output"]
    output_root = Path(str(output_config["folder"])).expanduser()
    md_filename = _validate_safe_component(
        str(output_config.get("md_filename", "search_result.md")),
        "output.md_filename",
    )

    copied = sum(1 for item in exported if item.copied)
    skipped = len(exported) - copied

    lines = [
        "# RG Search Result",
        "",
        "## Search Conditions",
        "",
        "YAML:",
        str(yaml_path),
        "",
        "Sources:",
        *[f"- {source['path']}" for source in config["sources"]],
        "",
        "Extensions:",
        *[f"- {item}" for item in _normalise_extensions(config["extensions"])],
        "",
        "Include Keywords:",
        *[f"- {item}" for item in config["include_keywords"]],
        "",
        "Exclude Keywords:",
        *[f"- {item}" for item in config.get("exclude_keywords", [])],
        "",
        "## Search Summary",
        "",
        f"Total Matched: {total_results}",
        f"Selected: {len(exported)}",
        f"Copied: {copied}",
        f"Skipped: {skipped}",
        "",
        "## Selected Files",
        "",
    ]

    for index, record in enumerate(exported, 1):
        item = record.search_result
        status = "Copied" if record.copied else f"Skipped - {record.reason or 'Unknown'}"

        lines.extend(
            [
                f"### {index}. {item.file_name}",
                "",
                "Source:",
                item.source_name,
                "",
                "Original Path:",
                str(item.file_path),
                "",
                "Destination:",
                str(record.destination),
                "",
                "Matched Keywords:",
                *[f"- {keyword}" for keyword in item.matched_keywords],
                "",
                "Status:",
                status,
                "",
            ]
        )

    try:
        output_root.mkdir(parents=True, exist_ok=True)
        md_path = output_root / md_filename
        md_path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        raise FinderError(f"無法建立輸出或 Markdown：{exc}") from exc

    return md_path
