"""RG File Finder 的可重用設定、內容搜尋、匯出與 Markdown 核心。"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import yaml


MAX_YAML_BYTES = 1024 * 1024
MAX_SOURCES = 50
MAX_EXTENSIONS = 50
MAX_TOTAL_KEYWORDS = 50
MAX_KEYWORD_LENGTH = 256
MAX_EXCLUDE_FOLDERS = 100

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_EXTENSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,31}$")


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
    """驗證只能作為單一 Windows/Linux 檔名或資料夾名稱的文字。"""
    if not isinstance(value, str) or not value.strip():
        raise FinderError(f"{field_name} 必須是非空白文字。")

    text = value.strip()
    if text in {".", ".."} or "/" in text or "\\" in text or ":" in text or "\x00" in text:
        raise FinderError(f"{field_name} 不可包含路徑、磁碟代號或特殊路徑字元：{value}")
    if any(ord(char) < 32 for char in text):
        raise FinderError(f"{field_name} 不可包含控制字元。")
    if text.endswith((".", " ")):
        raise FinderError(f"{field_name} 不可用句點或空白結尾。")

    windows_base = text.split(".", 1)[0].upper()
    if windows_base in _WINDOWS_RESERVED_NAMES:
        raise FinderError(f"{field_name} 不可使用 Windows 保留名稱：{value}")
    return text


def _is_network_path(value: str) -> bool:
    """判斷 UNC、POSIX network-style 與 Windows device namespace 路徑。"""
    text = value.strip()
    return text.startswith("\\\\") or text.startswith("//")


def _validate_local_path(value: Any, field_name: str, *, allow_network_paths: bool) -> str:
    """驗證 YAML 路徑文字；預設拒絕 UNC/network path。"""
    if not isinstance(value, str) or not value.strip():
        raise FinderError(f"{field_name} 必須是非空白文字。")
    text = value.strip()
    if "\x00" in text or any(ord(char) < 32 for char in text):
        raise FinderError(f"{field_name} 不可包含控制字元。")
    if not allow_network_paths and _is_network_path(text):
        raise FinderError(f"{field_name} 預設不允許 UNC/network path：{value}")
    return text


def _ensure_within(root: Path, candidate: Path, field_name: str) -> Path:
    """解析 symlink/junction 後確認 candidate 仍位於 root 內。"""
    try:
        resolved_root = root.resolve(strict=False)
        resolved_candidate = candidate.resolve(strict=False)
    except OSError as exc:
        raise FinderError(f"無法解析 {field_name}：{exc}") from exc

    if not resolved_candidate.is_relative_to(resolved_root):
        raise FinderError(f"{field_name} 超出允許的根目錄：{candidate}")
    return resolved_candidate


def _validate_source_output_separation(source_path: str, output_path: str, source_name: str) -> None:
    """拒絕 source 與 output 互相包含，避免輸出檔在後續搜尋中被再次掃描。"""
    if _is_network_path(source_path) or _is_network_path(output_path):
        return

    try:
        source = Path(source_path).expanduser().resolve(strict=False)
        output = Path(output_path).expanduser().resolve(strict=False)
    except OSError as exc:
        raise FinderError(f"無法解析 source/output 路徑：{exc}") from exc

    if source == output or output.is_relative_to(source) or source.is_relative_to(output):
        raise FinderError(
            f"source 與 output.folder 不可互相包含：{source_name} -> {source}；output -> {output}"
        )


def _overwrite_files_enabled(output_config: Mapping[str, Any]) -> bool:
    """取得檔案覆寫設定；新欄位優先，舊 overwrite 保持相容。"""
    if "overwrite_files" in output_config:
        return bool(output_config["overwrite_files"])
    if "overwrite" in output_config:
        return bool(output_config["overwrite"])
    return False


def _overwrite_report_enabled(output_config: Mapping[str, Any]) -> bool:
    """取得報告覆寫設定；新欄位優先，舊 overwrite 保持相容。"""
    if "overwrite_report" in output_config:
        return bool(output_config["overwrite_report"])
    if "overwrite" in output_config:
        return bool(output_config["overwrite"])
    return True


def _escape_markdown(value: Any) -> str:
    """將外部輸入轉為單行且不會改寫 Markdown 結構的文字。"""
    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    text = html.escape(text, quote=False)
    text = text.replace("\\", "\\\\")
    for char in ("`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", "!", "|", ">"):
        text = text.replace(char, f"\\{char}")
    return text


def load_config(config_path: Path | str) -> dict[str, Any]:
    """讀取並驗證 YAML 設定檔。"""
    path = Path(config_path)
    if not path.is_file():
        raise FinderError(f"YAML 設定檔不存在：{path}")
    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise FinderError("設定檔副檔名必須是 .yaml 或 .yml。")

    try:
        file_size = path.stat().st_size
    except OSError as exc:
        raise FinderError(f"無法取得 YAML 檔案資訊：{exc}") from exc

    if file_size > MAX_YAML_BYTES:
        raise FinderError(
            f"YAML 檔案過大：{file_size} bytes；上限為 {MAX_YAML_BYTES} bytes。"
        )

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
    """確認內容搜尋、資源限制與輸出安全所需的 YAML 欄位。"""
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

    if len(config["sources"]) > MAX_SOURCES:
        raise FinderError(f"sources 最多允許 {MAX_SOURCES} 筆。")
    if len(config["extensions"]) > MAX_EXTENSIONS:
        raise FinderError(f"extensions 最多允許 {MAX_EXTENSIONS} 筆。")

    security = config.get("security", {})
    if not isinstance(security, dict):
        raise FinderError("YAML 欄位 security 必須是 mapping。")
    allow_network_paths = security.get("allow_network_paths", False)
    if not isinstance(allow_network_paths, bool):
        raise FinderError("security.allow_network_paths 必須是 true 或 false。")

    source_names: set[str] = set()
    validated_sources: list[tuple[str, str]] = []
    for index, source in enumerate(config["sources"], 1):
        if not isinstance(source, dict) or not source.get("name") or not source.get("path"):
            raise FinderError(f"sources 第 {index} 筆必須包含 name 與 path。")

        source_name = _validate_safe_component(source["name"], f"sources 第 {index} 筆 name")
        source_key = source_name.casefold()
        if source_key in source_names:
            raise FinderError(f"source.name 必須唯一，重複名稱：{source_name}")
        source_names.add(source_key)

        source_path = _validate_local_path(
            source["path"],
            f"sources 第 {index} 筆 path",
            allow_network_paths=allow_network_paths,
        )
        validated_sources.append((source_name, source_path))

    if not all(isinstance(item, str) and item.strip() for item in config["extensions"]):
        raise FinderError("extensions 每一筆都必須是非空白文字。")
    for item in config["extensions"]:
        extension = item.strip().lstrip(".")
        if not _EXTENSION_PATTERN.fullmatch(extension):
            raise FinderError(f"extensions 包含不安全或不支援的格式：{item}")

    if not all(isinstance(item, str) and item.strip() for item in config["include_keywords"]):
        raise FinderError("include_keywords 每一筆都必須是非空白文字。")

    exclude_keywords = config.get("exclude_keywords", [])
    if not isinstance(exclude_keywords, list) or not all(isinstance(item, str) for item in exclude_keywords):
        raise FinderError("YAML 欄位 exclude_keywords 必須是文字 list。")

    total_keywords = len(config["include_keywords"]) + len(exclude_keywords)
    if total_keywords > MAX_TOTAL_KEYWORDS:
        raise FinderError(f"include/exclude keywords 合計最多允許 {MAX_TOTAL_KEYWORDS} 筆。")
    for keyword in [*config["include_keywords"], *exclude_keywords]:
        if not keyword.strip():
            raise FinderError("關鍵字不可為空白文字。")
        if len(keyword) > MAX_KEYWORD_LENGTH:
            raise FinderError(f"單一關鍵字最多允許 {MAX_KEYWORD_LENGTH} 個字元。")
        if "\x00" in keyword:
            raise FinderError("關鍵字不可包含 NUL 字元。")

    exclude_folders = config.get("exclude_folders", [])
    if not isinstance(exclude_folders, list) or not all(isinstance(item, str) for item in exclude_folders):
        raise FinderError("YAML 欄位 exclude_folders 必須是文字 list。")
    if len(exclude_folders) > MAX_EXCLUDE_FOLDERS:
        raise FinderError(f"exclude_folders 最多允許 {MAX_EXCLUDE_FOLDERS} 筆。")
    for folder in exclude_folders:
        safe_folder = _validate_safe_component(folder, "exclude_folders 項目")
        if any(char in safe_folder for char in "*?[]{}"):
            raise FinderError(f"exclude_folders 不可包含 glob 萬用字元：{folder}")

    search = config.get("search", {})
    if not isinstance(search, dict):
        raise FinderError("YAML 欄位 search 必須是 mapping。")
    for option in ("ignore_case", "include_hidden", "respect_gitignore"):
        if option in search and not isinstance(search[option], bool):
            raise FinderError(f"search.{option} 必須是 true 或 false。")

    output = config["output"]
    if not isinstance(output, dict) or not output.get("folder"):
        raise FinderError("YAML 必須設定 output.folder。")
    output_path = _validate_local_path(
        output["folder"],
        "output.folder",
        allow_network_paths=allow_network_paths,
    )

    for option in ("preserve_structure", "overwrite", "overwrite_files", "overwrite_report"):
        if option in output and not isinstance(output[option], bool):
            raise FinderError(f"output.{option} 必須是 true 或 false。")

    if "md_filename" in output:
        _validate_safe_component(output["md_filename"], "output.md_filename")

    for source_name, source_path in validated_sources:
        _validate_source_output_separation(source_path, output_path, source_name)


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
    includes = list(dict.fromkeys(str(item).strip() for item in config["include_keywords"] if str(item).strip()))
    excludes = list(
        dict.fromkeys(str(item).strip() for item in config.get("exclude_keywords", []) if str(item).strip())
    )
    exclude_folders = list(
        dict.fromkeys(str(item).strip() for item in config.get("exclude_folders", []) if str(item).strip())
    )
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
                if path.is_relative_to(root):
                    matched_by_file.setdefault(path, []).append(keyword)

        excluded_paths: set[Path] = set()
        for keyword in excludes:
            excluded_paths.update(
                path
                for path in _search_keyword(root, keyword, extensions, exclude_folders, search_options)
                if path.is_relative_to(root)
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
    """複製所選檔案，並防止 symlink/junction 讓輸出逃出 output root。"""
    output_root = Path(str(output_config["folder"])).expanduser()
    preserve = bool(output_config.get("preserve_structure", True))
    overwrite_files = _overwrite_files_enabled(output_config)
    notify = message_handler or print

    try:
        output_root.mkdir(parents=True, exist_ok=True)
        output_root_resolved = output_root.resolve(strict=False)
    except OSError as exc:
        raise FinderError(f"無法建立輸出資料夾：{exc}") from exc

    exported: list[ExportResult] = []

    for item in selected:
        source_name = _validate_safe_component(item.source_name, "source_name")
        try:
            source_root = item.source_root.resolve(strict=False)
            source_file = item.file_path.resolve(strict=True)
            if not source_file.is_relative_to(source_root):
                raise FinderError(f"來源檔案超出來源根目錄：{item.file_path}")

            relative = source_file.relative_to(source_root) if preserve else Path(source_file.name)
            destination = output_root / source_name / relative

            # 在建立任何目的資料夾前先解析現有 symlink/junction，避免先在根目錄外產生副作用。
            _ensure_within(output_root_resolved, destination, "輸出路徑")
            destination.parent.mkdir(parents=True, exist_ok=True)
            # 建立後再驗一次，縮小 TOCTOU 與中間層被替換的風險。
            _ensure_within(output_root_resolved, destination, "輸出路徑")

            if destination.exists() and not overwrite_files:
                reason = "Already Exists"
                notify(f"[跳過] 已存在：{destination}")
                exported.append(ExportResult(item, destination, False, reason))
                continue

            shutil.copy2(source_file, destination)
            notify(f"[複製] {destination}")
            exported.append(ExportResult(item, destination, True, None))

        except FinderError:
            raise
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
    """在 output.folder 安全產生搜尋條件、摘要與選取檔案 Markdown 報告。"""
    validate_config(config)
    output_config = config["output"]
    output_root = Path(str(output_config["folder"])).expanduser()
    overwrite_report = _overwrite_report_enabled(output_config)
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
        _escape_markdown(yaml_path),
        "",
        "Sources:",
        *[f"- {_escape_markdown(source['path'])}" for source in config["sources"]],
        "",
        "Extensions:",
        *[f"- {_escape_markdown(item)}" for item in _normalise_extensions(config["extensions"])],
        "",
        "Include Keywords:",
        *[f"- {_escape_markdown(item)}" for item in config["include_keywords"]],
        "",
        "Exclude Keywords:",
        *[f"- {_escape_markdown(item)}" for item in config.get("exclude_keywords", [])],
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
                f"### {index}. {_escape_markdown(item.file_name)}",
                "",
                "Source:",
                _escape_markdown(item.source_name),
                "",
                "Original Path:",
                _escape_markdown(item.file_path),
                "",
                "Destination:",
                _escape_markdown(record.destination),
                "",
                "Matched Keywords:",
                *[f"- {_escape_markdown(keyword)}" for keyword in item.matched_keywords],
                "",
                "Status:",
                _escape_markdown(status),
                "",
            ]
        )

    try:
        output_root.mkdir(parents=True, exist_ok=True)
        output_root_resolved = output_root.resolve(strict=False)
        md_path = output_root / md_filename
        _ensure_within(output_root_resolved, md_path, "Markdown 輸出路徑")
        if md_path.exists() and not overwrite_report:
            raise FinderError(f"Markdown 已存在且 overwrite_report=false：{md_path}")
        md_path.write_text("\n".join(lines), encoding="utf-8")
    except FinderError:
        raise
    except OSError as exc:
        raise FinderError(f"無法建立輸出或 Markdown：{exc}") from exc

    return md_path
