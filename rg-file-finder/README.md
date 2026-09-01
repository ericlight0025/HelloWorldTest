# RG File Finder

RG File Finder 是以 `ripgrep (rg)` 為底層的 **YAML-driven Menu CLI**。工具會依 YAML 設定搜尋 `.sql`、`.java`、`.js`、`.jsp` 等檔案的**內容**，顯示命中結果，讓使用者選擇要輸出的檔案，再複製到指定資料夾並產生 Markdown 報告。

## 系統需求

- Python 3.10+
- ripgrep
- PyYAML

```bash
pip install pyyaml
rg --version
```

## 執行方式

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

## 操作流程

### 1. 載入 YAML

選擇 `1` 後輸入 YAML **絕對路徑**：

```text
D:\config\rg-search.yaml
```

程式會驗證：

- 路徑為絕對路徑
- 檔案存在
- 副檔名為 `.yaml` 或 `.yml`
- YAML 可解析
- `sources`、`extensions`、`include_keywords` 至少一筆
- `output.folder` 已設定

### 2. 搜尋、選擇、輸出

選擇 `2` 後完全依 YAML 執行，不再要求輸入 keyword、source、extension 或 output。

搜尋的是**檔案內容**，底層使用：

```text
rg --files-with-matches --fixed-strings
```

搜尋結果會顯示：

- 編號
- 檔名
- Source
- 完整路徑
- 命中的 include keyword

選擇格式支援：

```text
1
1,3,5
1,3,5-8
1,3,5-8,12
all
```

`all` 代表全部選取。

選取後會把實體檔案複製到 `output.folder`，並產生 `search_result.md`。

### 3. 檢視 YAML

選擇 `3` 會顯示目前 YAML 的**原始文字**。程式不會重新 serialize YAML，因此原有縮排與註解可保留。

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

`search_result.md` 會包含：

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

Markdown **不包含原始檔案完整內容**。

即使搜尋結果為 0，仍會產生：

```text
Total Matched: 0
Selected: 0
Copied: 0
Skipped: 0
```

## 程式架構

```text
rg-file-finder/
├── main.py
├── finder.py
├── config.yaml
└── README.md
```

`main.py`：

- Menu CLI
- YAML path state
- 顯示搜尋結果
- 解析使用者選擇
- 呼叫 Core

`finder.py`：

- `load_config()`
- `validate_config()`
- `search_files()`
- `export_files()`
- `generate_markdown()`

搜尋與輸出核心可直接由未來 GUI 重用。
