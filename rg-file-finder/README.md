# RG File Finder

RG File Finder 是以 `ripgrep (rg)` 為底層的 YAML-driven 檔案內容搜尋工具，提供 Menu CLI 與 Tkinter GUI，支援多來源資料夾、指定副檔名、Include / Exclude 關鍵字、排除資料夾、多檔選取與複製，以及 Markdown 搜尋報告。

CLI 與 GUI 共用 `finder.py` 核心，搜尋、匯出、驗證與報告邏輯集中管理。

## 系統需求

- Python 3.10+
- ripgrep
- PyYAML
- Tkinter（GUI 使用）

安裝：

```bash
python -m pip install -r requirements.txt
rg --version
```

測試：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## 執行

CLI：

```bash
python main.py
```

GUI：

```bash
python gui.py
```

CLI 選單：

```text
1. 載入 YAML 設定檔
2. 執行搜尋、選擇檔案並輸出
3. 檢視 YAML 內容
0. 離開
```

GUI 支援載入與查看 YAML、背景搜尋、多選結果、全選 / 取消全選、背景複製與 Markdown 報告。背景工作透過 Queue 回到 Tk 主執行緒更新 UI，執行期間會鎖定會改變狀態的操作，避免重複工作與 race condition。

## YAML 範例

```yaml
sources:
  - name: project-a
    path: 'C:\workspace\project-a'

  - name: project-b
    path: 'D:\workspace\project-b'

extensions:
  - sql
  - java
  - js
  - jsp

include_keywords:
  - policy
  - customer

exclude_keywords:
  - test
  - backup

exclude_folders:
  - .git
  - target
  - node_modules
  - dist

search:
  ignore_case: true
  include_hidden: false
  respect_gitignore: true

security:
  allow_network_paths: false

output:
  folder: 'D:\rg-output'
  preserve_structure: true
  overwrite_files: false
  overwrite_report: true
  md_filename: 'search_result.md'
```

## 搜尋規則

- `include_keywords` 採 OR；命中任一關鍵字即成為候選。
- `exclude_keywords` 命中任一關鍵字則排除整個檔案。
- `extensions` 只允許安全副檔名格式，不接受 glob 萬用字元。
- `exclude_folders` 不允許 glob 萬用字元，避免 YAML 改寫預期搜尋範圍。
- `source.name` 必須唯一，且以不分大小寫方式判定重複，避免多個來源輸出到同一 source 目錄。
- source 與 `output.folder` 不可相同、互為父子目錄，避免輸出結果在後續搜尋中被重新掃描與重複複製。
- 關鍵字、來源數、副檔名數與排除資料夾數都有上限，避免惡意或誤設 YAML 造成大量重複掃描。

目前核心仍採每個 include / exclude keyword 分別呼叫 ripgrep。若未來大型專案量測到效能瓶頸，再評估單次 `rg --json` 掃描。

## YAML 大小限制

YAML 設定檔上限為 **1 MiB**。程式會在 YAML 解析前檢查大小，避免異常巨大的設定檔先消耗過多記憶體。

一般設定檔通常只有幾 KB，1 MiB 已遠高於正常使用需求。

## Security Hardening

此工具會讀取 YAML 指定的來源並將檔案寫入指定輸出位置，因此第三方 YAML 應視為不可信輸入。

目前防護包含：

- `subprocess.run()` 使用參數陣列，不使用 `shell=True`。
- 關鍵字前使用 ripgrep `--`，並搭配 `--fixed-strings`，避免關鍵字被解析為命令列選項或正規表示式。
- `source.name` 與 `output.md_filename` 只能是單一安全名稱，拒絕 `/`、`\`、`..`、控制字元、Windows 保留名稱，以及句點 / 空白結尾名稱。
- 預設拒絕 UNC / network path；只有明確設定 `security.allow_network_paths: true` 才允許。
- 搜尋結果解析後必須仍位於原始 source root 內。
- source 與 output 不允許互相包含，避免輸出資料再次進入搜尋範圍。
- 匯出前會解析 symlink / junction，確認 destination 仍位於 `output.folder` 內；建立目的資料夾前後各檢查一次，避免路徑逃逸與外部目錄副作用。
- Markdown 會 escape YAML 路徑、關鍵字、檔名與狀態等外部文字，避免內容改寫報告結構。
- YAML 檔案大小、source 數量、extension 數量、keyword 數量與長度、exclude folder 數量皆有限制。

`allow_network_paths: true` 代表使用者自行選擇允許 UNC / network path，只應對可信任來源使用。

## 輸出規則

`preserve_structure: true`：

```text
D:\rg-output\
  project-a\
    src\
      main\
        java\
          PolicyService.java
```

`preserve_structure: false`：

```text
D:\rg-output\
  project-a\
    PolicyService.java
```

建議使用：

```yaml
output:
  overwrite_files: false
  overwrite_report: true
```

- `overwrite_files: false`：既有來源檔案不覆寫，避免誤蓋掉先前匯出內容。
- `overwrite_report: true`：Markdown 報告每次更新，避免第二次搜尋因舊報告存在而失敗。

### 舊版 YAML 相容性

舊設定仍可使用：

```yaml
output:
  overwrite: false
```

若新舊欄位同時存在，`overwrite_files` / `overwrite_report` 優先於舊的 `overwrite`。

相容規則：

- `overwrite_files` 未設定時，使用舊 `overwrite`；若兩者皆未設定，預設 `false`。
- `overwrite_report` 未設定時，使用舊 `overwrite`；若兩者皆未設定，預設 `true`。

## Markdown

預設 `search_result.md` 包含 YAML path、Sources、Extensions、Include / Exclude Keywords、Total Matched、Selected、Copied、Skipped、原始路徑、Destination、Matched Keywords 與 Copy Status。

Markdown 不包含原始檔案完整內容。搜尋結果為 0 時仍會產生摘要。

## 專案架構

```text
HelloWorldTest/
├── .github/
│   └── workflows/
│       └── rg-file-finder-test.yml
└── rg-file-finder/
    ├── finder.py
    ├── gui.py
    ├── main.py
    ├── config.yaml
    ├── README.md
    ├── requirements.txt
    ├── requirements-dev.txt
    └── tests/
        ├── test_finder.py
        └── test_main.py
```

## Regression Tests

安全與穩定性測試涵蓋：

- 不安全 `source.name` / Markdown filename
- Windows `CON`、`NUL`、`COM1`、`LPT9` 等保留名稱
- 重複 `source.name`
- source / output 相同或互相包含
- YAML 超過 1 MiB
- 預設拒絕 UNC source / output
- 明確允許 network path 的 opt-in 行為
- glob extension / exclude folder 拒絕
- keyword 數量與長度限制
- source file 不可逃出 source root
- symlink destination escape
- `overwrite_files` / `overwrite_report`
- 舊 `overwrite` 相容性與新欄位優先權
- Markdown escape
- CLI selection parser

## CI

GitHub Actions 使用 Python 3.13，並在以下兩個 runner 執行 compile 與 pytest：

```text
windows-latest
ubuntu-latest
```

Windows 主要覆蓋實際使用環境與 Windows path 行為；Ubuntu runner 補充可穩定建立 symlink 的 containment regression test。
