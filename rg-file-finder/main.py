"""RG File Finder 命令列介面。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from finder import FinderError, SearchResult, export_files, generate_markdown, load_config, search_files


def _csv_values(values: Sequence[str] | None) -> list[str]:
    """拆解可重複且可用逗號分隔的 CLI 值。"""
    return [part.strip() for value in (values or []) for part in value.split(",") if part.strip()]


def parse_selection(expression: str, result_count: int) -> list[int]:
    """解析 ``1,3,5-8`` 格式，回傳去重且維持輸入順序的零基索引。"""
    if not expression.strip():
        raise ValueError("選擇不可為空")
    selected: list[int] = []
    for token in expression.split(","):
        token = token.strip()
        if not token:
            raise ValueError("選擇格式包含空白項目")
        if "-" in token:
            parts = token.split("-")
            if len(parts) != 2 or not all(part.isdigit() for part in parts):
                raise ValueError(f"無效範圍：{token}")
            start, end = map(int, parts)
            if start > end:
                raise ValueError(f"無效範圍（起點大於終點）：{token}")
            numbers = range(start, end + 1)
        else:
            if not token.isdigit():
                raise ValueError(f"不是有效數字：{token}")
            numbers = [int(token)]
        for number in numbers:
            if number < 1 or number > result_count:
                raise ValueError(f"編號超出範圍：{number}（有效範圍 1-{result_count}）")
            if number - 1 not in selected:
                selected.append(number - 1)
    return selected


def build_parser() -> argparse.ArgumentParser:
    """建立 CLI argument parser。"""
    parser = argparse.ArgumentParser(description="使用 rg --files 依檔名搜尋並匯出檔案")
    parser.add_argument("-c", "--config", default=str(Path(__file__).with_name("config.yaml")), help="YAML 設定檔")
    parser.add_argument("-k", "--keyword", required=True, help="檔名必須包含的關鍵字")
    parser.add_argument("-x", "--exclude", action="append", help="額外排除關鍵字，可重複或逗號分隔")
    parser.add_argument("--ext", action="append", help="覆蓋副檔名，可重複或逗號分隔")
    parser.add_argument("--source", action="append", help="覆蓋 YAML 來源資料夾，可重複")
    parser.add_argument("-o", "--output", help="覆蓋輸出資料夾")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--copy", action="store_true", help="互動選擇後複製")
    mode.add_argument("--copy-all", action="store_true", help="複製全部結果")
    mode.add_argument("--select", help="直接指定編號，例如 1,3,5-8")
    return parser


def _cli_sources(paths: Sequence[str] | None) -> list[dict[str, str]] | None:
    """把 CLI 路徑轉成來源設定，並為重複名稱加上序號。"""
    if paths is None:
        return None
    counts: dict[str, int] = {}
    sources = []
    for raw_path in paths:
        base = Path(raw_path).name or "source"
        counts[base] = counts.get(base, 0) + 1
        name = base if counts[base] == 1 else f"{base}-{counts[base]}"
        sources.append({"name": name, "path": raw_path})
    return sources


def _show_results(keyword: str, results: Sequence[SearchResult]) -> None:
    """顯示編號、來源與完整路徑。"""
    print("=" * 80, "RG File Finder", "=" * 80, sep="\n")
    print(f"檔名包含：{keyword}")
    print(f"找到 {len(results)} 個檔案：")
    for index, item in enumerate(results, 1):
        print(f"[{index:3d}] {item.file_name}\n      Source : {item.source_name}\n      Path   : {item.file_path}")


def _select_interactively(result_count: int) -> list[int]:
    """重複詢問直到輸入有效選擇。"""
    print("請輸入要複製的檔案編號：\n例如：\n1,3,5\n或：\n1,3,5-8")
    while True:
        try:
            return parse_selection(input("選擇："), result_count)
        except ValueError as exc:
            print(f"選擇無效：{exc}")


def run(args: argparse.Namespace) -> int:
    """執行搜尋，以及使用者要求的匯出流程。"""
    config = load_config(args.config)
    cli_extensions = _csv_values(args.ext)
    extra_excludes = _csv_values(args.exclude)
    sources = _cli_sources(args.source)
    results = search_files(
        config, args.keyword, extra_excludes=extra_excludes,
        extensions=cli_extensions or None, sources=sources,
    )
    _show_results(args.keyword, results)
    if not results:
        print("沒有找到符合條件的檔案。")
        return 0
    if not (args.copy or args.copy_all or args.select):
        return 0

    if args.copy_all:
        indices = list(range(len(results)))
    elif args.select:
        indices = parse_selection(args.select, len(results))
    else:
        indices = _select_interactively(len(results))
    selected = [results[index] for index in indices]
    output_config: Mapping[str, Any] = config.get("output", {})
    output_root = args.output or output_config.get("folder")
    if not output_root:
        raise FinderError("輸出資料夾未設定，請使用 -o 或 output.folder")
    exported = export_files(selected, output_root, output_config)
    configured_extensions = cli_extensions or [str(item) for item in config.get("extensions", [])]
    all_excludes = [str(item) for item in config.get("exclude_keywords", [])] + extra_excludes
    active_sources = sources if sources is not None else config.get("sources", [])
    md_path = generate_markdown(
        output_root, output_config, keyword=args.keyword, exclude_keywords=all_excludes,
        extensions=configured_extensions, source_count=len(active_sources),
        total_results=len(results), exported=exported,
    )
    if md_path:
        print(f"[Markdown] {md_path}")
    return 0


def main() -> int:
    """解析命令列並將預期錯誤轉為清楚訊息。"""
    try:
        return run(build_parser().parse_args())
    except (FinderError, ValueError, OSError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
