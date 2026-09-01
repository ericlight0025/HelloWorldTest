"""RG File Finder 的互動式 Menu CLI。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from finder import (
    ExportResult,
    FinderError,
    SearchResult,
    export_files,
    generate_markdown,
    load_config,
    search_files,
)


def show_menu(config_path: Path | None) -> None:
    """顯示主選單與目前 YAML 載入狀態。"""
    current = str(config_path) if config_path else "尚未載入"
    print(
        "\n========================================\n"
        "          RG File Finder\n"
        "========================================\n\n"
        f"目前 YAML：\n{current}\n\n"
        "1. 載入 YAML 設定檔\n"
        "2. 執行搜尋、選擇檔案並輸出\n"
        "3. 檢視 YAML 內容\n"
        "0. 離開\n\n"
        "請選擇："
    )


def load_yaml_from_input() -> tuple[Path, dict[str, Any], str] | None:
    """要求 YAML 絕對路徑，讀入解析結果與未修改的原始文字。"""
    print("請輸入 YAML 絕對路徑：\n")
    raw_path = input("> ").strip().strip('"')
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        print("[錯誤] YAML 路徑必須是絕對路徑。")
        return None
    try:
        config = load_config(path)
        raw_content = path.read_text(encoding="utf-8")
    except (FinderError, OSError) as exc:
        print(f"[錯誤] {exc}")
        return None
    print(f"[OK] YAML 載入成功\n\n目前設定檔：\n{path}")
    return path, config, raw_content


def parse_selection(expression: str, result_count: int) -> list[int]:
    """解析 all、1、1,3,5、1,3,5-8 等格式，回傳零基索引。"""
    text = expression.strip().lower()
    if not text:
        raise ValueError("選擇不可為空。")
    if text == "all":
        return list(range(result_count))

    selected_set: set[int] = set()
    for token in text.split(","):
        token = token.strip()
        if not token:
            raise ValueError("選擇格式包含空白項目。")
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
            numbers = (int(token),)

        for number in numbers:
            if number < 1 or number > result_count:
                raise ValueError(f"編號超出範圍：{number}（有效範圍 1-{result_count}）")
            selected_set.add(number - 1)

    return [index for index in range(result_count) if index in selected_set]


def show_results(results: Sequence[SearchResult]) -> None:
    """以固定格式顯示搜尋結果與命中關鍵字。"""
    print("\n========================================\n搜尋結果\n========================================\n")
    print(f"找到 {len(results)} 個符合條件的檔案：\n")
    for index, item in enumerate(results, 1):
        matched = ", ".join(item.matched_keywords)
        print(
            f"[{index}]\n"
            f"File   : {item.file_name}\n"
            f"Source : {item.source_name}\n"
            f"Path   : {item.file_path}\n"
            f"Match  : {matched}\n"
        )


def select_results(results: Sequence[SearchResult]) -> list[SearchResult]:
    """持續要求選擇，直到輸入有效。"""
    print("請輸入要輸出的檔案編號：\n例如：1、1,3,5、1,3,5-8，或輸入 all 全選。")
    while True:
        try:
            indices = parse_selection(input("> "), len(results))
            return [results[index] for index in indices]
        except ValueError as exc:
            print(f"[錯誤] 選擇格式錯誤：{exc}")
            print("請重新輸入。")


def print_export_summary(exported: Sequence[ExportResult]) -> None:
    """顯示複製結果摘要。"""
    copied = sum(1 for item in exported if item.copied)
    skipped = len(exported) - copied
    print(f"[OK] 已選擇 {len(exported)} 個檔案，複製 {copied} 個，略過 {skipped} 個。")


def run_search(config_path: Path | None, config: dict[str, Any] | None) -> None:
    """依 YAML 搜尋、選擇、複製檔案並產生 Markdown。"""
    if config_path is None or config is None:
        print("[錯誤] 尚未載入 YAML 設定檔。\n請先選擇「1. 載入 YAML 設定檔」。")
        return
    try:
        results = search_files(config)
        if not results:
            print("沒有找到符合條件的檔案。")
            md_path = generate_markdown(
                config=config,
                yaml_path=config_path,
                total_results=0,
                exported=[],
            )
            print(f"[OK] Markdown 已產生：\n{md_path}")
            return

        show_results(results)
        selected = select_results(results)
        exported = export_files(selected, config["output"])
        print_export_summary(exported)
        md_path = generate_markdown(
            config=config,
            yaml_path=config_path,
            total_results=len(results),
            exported=exported,
        )
        print(f"[OK] Markdown 已產生：\n{md_path}")
    except FinderError as exc:
        print(f"[錯誤] {exc}")


def view_yaml(config_path: Path | None, raw_content: str | None) -> None:
    """原樣顯示 YAML 文字，不重新序列化。"""
    if config_path is None or raw_content is None:
        print("[錯誤] 尚未載入 YAML 設定檔。")
        return
    print(
        "\n========================================\n"
        "目前 YAML\n"
        "========================================\n\n"
        f"Path:\n{config_path}\n\n"
        "----------------------------------------\n\n"
        f"{raw_content.rstrip()}\n\n"
        "----------------------------------------"
    )
    input("按 Enter 回主選單...")


def main() -> int:
    """持續執行 Menu CLI，直到使用者選擇離開。"""
    config_path: Path | None = None
    config: dict[str, Any] | None = None
    raw_content: str | None = None

    while True:
        show_menu(config_path)
        choice = input("> ").strip()
        if choice == "0":
            print("程式已結束。")
            return 0
        if choice == "1":
            loaded = load_yaml_from_input()
            if loaded is not None:
                config_path, config, raw_content = loaded
        elif choice == "2":
            run_search(config_path, config)
        elif choice == "3":
            view_yaml(config_path, raw_content)
        else:
            print("[錯誤] 無效的選項，請輸入 0、1、2 或 3。")


if __name__ == "__main__":
    raise SystemExit(main())
