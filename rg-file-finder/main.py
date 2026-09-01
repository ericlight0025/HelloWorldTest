"""RG File Finder 的互動式選單介面。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from finder import FinderError, generate_markdown, load_config, search_files


def show_menu(config_path: Path | None) -> None:
    """顯示主選單與目前載入狀態。"""
    current = str(config_path) if config_path else "尚未載入"
    print(
        "\n========================================\n"
        "          RG File Finder\n"
        "========================================\n\n"
        f"目前 YAML：\n{current}\n\n"
        "1. 載入 YAML 設定檔\n"
        "2. 執行搜尋並產生 MD\n"
        "3. 檢視 YAML 內容\n"
        "0. 離開\n\n"
        "請選擇："
    )


def load_yaml_from_input() -> tuple[Path, dict[str, Any], str] | None:
    """讀取絕對 YAML 路徑，保留解析結果與未修改的原始文字。"""
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


def run_search(config_path: Path | None, config: dict[str, Any] | None) -> None:
    """依目前記憶體中的 YAML 設定搜尋並產生 Markdown。"""
    if config_path is None or config is None:
        print("[錯誤] 尚未載入 YAML 設定檔。\n請先選擇「1. 載入 YAML 設定檔」。")
        return
    try:
        results = search_files(config)
        md_path = generate_markdown(config, config_path, results)
    except FinderError as exc:
        print(f"[錯誤] {exc}")
        return
    if not results:
        print("沒有找到符合條件的檔案。")
    else:
        print(f"[OK] 找到 {len(results)} 個檔案。")
    print(f"[OK] Markdown 已產生：\n{md_path}")


def view_yaml(config_path: Path | None, raw_content: str | None) -> None:
    """原樣顯示 YAML 文字，不重新序列化。"""
    if config_path is None or raw_content is None:
        print("[錯誤] 尚未載入 YAML 設定檔。")
        return
    print(
        "========================================\n"
        "目前 YAML\n"
        "========================================\n\n"
        f"Path:\n{config_path}\n\n"
        "----------------------------------------\n\n"
        f"{raw_content.rstrip()}\n\n"
        "----------------------------------------"
    )
    input("按 Enter 回主選單...")


def main() -> int:
    """持續執行互動式選單，直到使用者選擇離開。"""
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
