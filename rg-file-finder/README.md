# RG File Finder

RG File Finder 是以 `ripgrep (rg)` 為底層的 YAML-driven 檔案內容搜尋工具，提供：

- Menu CLI
- Tkinter GUI
- 多來源資料夾搜尋
- `.sql`、`.java`、`.js`、`.jsp` 等副檔名篩選
- Include / Exclude 關鍵字
- 排除指定資料夾
- 多檔選取與複製
- Markdown 搜尋報告
- Windows GitHub Actions 測試

CLI 與 GUI 共用同一份 `finder.py` 核心，避免搜尋、匯出與 Markdown 邏輯重複實作。

## 系統需求

- Python 3.10+
- ripgrep
- PyYAML
- Tkinter（GUI 使用）

安裝 Python 相依套件：

```bash
python -m pip install -r requirements.txt
```

確認 ripgrep：

```bash
rg --version
```

若要執行測試：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## 執行 CLI

進入 `rg-file-finder` 目錄後：

```bash
python main.py
```

主選單：

```text
========================================
          RG File Finder
========================================

目前 YAML：
尚未載入

1. 載入 YAML 設定檔
2. 執行搜尋、選擇檔案並輸出
3. 檢視 YAML 內容
0. 離開
```

## 執行 GUI

進入 `rg-file-finder` 目錄後：

```bash
python gui.py
```

GUI 支援：

- 選擇並載入 YAML
- 查看 YAML 原始內容
- 背景執行搜尋，不阻塞視窗
- 多選搜尋結果
- 全選 / 取消全選
- 背景複製檔案
- 產生 Markdown 報告
- 搜尋結果為 0 時仍產生 Markdown

背景作業使用 Queue 將結果交回 Tk 主執行緒更新 UI；執行搜尋或複製期間，會暫停可改變狀態的按鈕，避免重複啟動工作或切換 YAML 造成 race condition。

## 操作流程

### 1. 載入 YAML

CLI 選擇 `1` 後需輸入 YAML 絕對路徑：

```text
D:\config\rg-search.yaml
```

GUI 則可直接使用檔案選擇器。

程式會驗證：

- YAML 檔案存在
- 副檔名為 `.yaml` 或 `.yml`
- YAML 可解析
- `sources`、`extensions`、`include_keywords` 至少一筆
- 每個 source 具備 `name` 與 `path`
- `source.name` 不可包含路徑字元
- `search.*` 布林設定必須是 `true` / `false`
- `output.folder` 已設定
- `output.md_filename` 只能是單一檔名，不可包含路徑或 `..`

### 2. 搜尋、選擇、輸出

CLI 選擇 `2` 後完全依 YAML 執行，不再要求輸入 keyword、source、extension 或 output。

搜尋的是檔案內容，底層使用：

```text
rg --files-with-matches --fixed-strings
```

搜尋結果會顯示：

- 編號
- 檔名
- Source
- 完整路徑
- 命中的 include keyword

CLI 選擇格式支援：

```text
1
1,3,5
1,3,5-8
1,3,5-8,12
all
```

`all` 代表全部選取。

GUI 可直接使用多選方式選取結果。

選取後會把實體檔案複製到 `output.folder`，並產生 Markdown 報告。

### 3. 檢視 YAML

CLI 選擇 `3` 或 GUI 點選「查看 YAML」都會顯示目前 YAML 的原始文字。

程式不重新 serialize YAML，因此原有縮排與註解可保留。

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
  - temp
  - old

exclude_folders:
  - .git
  - target
  - node_modules
  - dist

search:
  ignore_case: true
  include_hidden: false
  respect_gitignore: true

output:
  folder: 'D:\rg-output'
  preserve_structure: true
  overwrite: false
  md_filename: 'search_result.md'
```

## 搜尋規則

### include_keywords

採 OR。檔案內容只要命中任一 include keyword 即成為候選結果。

### exclude_keywords

只要候選檔案內容命中任一 exclude keyword，整個檔案就排除。

### extensions

只搜尋 YAML 指定的副檔名。

### exclude_folders

透過 ripgrep glob 排除指定資料夾，例如 `.git`、`target`、`node_modules`、`dist`。

### search

- `ignore_case`：忽略大小寫
- `include_hidden`：包含隱藏檔案
- `respect_gitignore`：遵守 `.gitignore`

## 輸出規則

### preserve_structure: true

保留來源內的相對路徑：

```text
D:\rg-output\
  project-a\
    src\
      main\
        java\
          PolicyService.java
```

### preserve_structure: false

只保留 Source 層與檔名：

```text
D:\rg-output\
  project-a\
    PolicyService.java
```

### overwrite: false

目的檔已存在時略過，不覆寫。

### overwrite: true

允許覆寫既有檔案。

## Markdown

預設 `search_result.md` 會包含：

- YAML path
- Sources
- Extensions
- Include Keywords
- Exclude Keywords
- Total Matched
- Selected
- Copied
- Skipped
- 每個選取檔案的原始路徑
- Destination
- Matched Keywords
- Copy Status

Markdown 不包含原始檔案完整內容。

即使搜尋結果為 0，仍會產生：

```text
Total Matched: 0
Selected: 0
Copied: 0
Skipped: 0
```

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

### `main.py`

- Menu CLI
- YAML path state
- 顯示搜尋結果
- 解析使用者選擇
- 呼叫 Core

### `gui.py`

- Tkinter GUI
- Queue + main-thread UI 更新
- 背景搜尋與複製
- Busy 狀態鎖定
- 設定與結果 snapshot，避免 worker 讀取到變更後的狀態

### `finder.py`

- `load_config()`
- `validate_config()`
- `search_files()`
- `export_files()`
- `generate_markdown()`
- YAML 路徑安全驗證
- ripgrep 啟動與錯誤處理

## CI

當 `rg-file-finder/**` 或 workflow 本身有變更時，GitHub Actions 會在 Windows runner 上執行：

```text
Python 3.13
ripgrep install
pip install
py_compile
pytest
```

這可以避免未來修改 CLI、GUI 或核心後，只有人工測試紀錄而沒有可重複驗證的 regression test。
