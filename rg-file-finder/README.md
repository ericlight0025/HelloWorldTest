# RG File Finder

RG File Finder 是以 ripgrep (`rg`) 為底層的互動式檔案**內容**搜尋工具。搜尋條件完全由 YAML 提供，搜尋後會產生 Markdown 清單；清單只包含檔案路徑與命中關鍵字，不會包含完整檔案內容。

## 系統需求

- Python 3.10+
- ripgrep
- PyYAML

```bash
pip install pyyaml
rg --version
```

## 執行方式

進入專案資料夾後直接執行：

```bash
python main.py
```

程式會持續顯示選單：

```text
1. 載入 YAML 設定檔
2. 執行搜尋並產生 MD
3. 檢視 YAML 內容
0. 離開
```

先選擇 `1` 並輸入 YAML 的**絕對路徑**。載入成功後，選擇 `2` 即會依 YAML 搜尋全部來源並在 `output.folder` 產生 Markdown。選擇 `3` 可查看 YAML 原始文字，包含原本的縮排與註解。

## YAML 設定

專案內的 `config.yaml` 是完整範例。主要欄位如下：

- `sources`：一或多個來源，每筆必須包含 `name` 與 `path`。
- `extensions`：允許搜尋的副檔名，不含開頭的點。
- `include_keywords`：內容至少命中其中一個關鍵字才列入結果（OR）。
- `exclude_keywords`：內容命中任何一個關鍵字就排除。
- `exclude_folders`：不搜尋的資料夾。
- `search.ignore_case`：是否忽略大小寫。
- `search.include_hidden`：是否包含隱藏檔案。
- `search.respect_gitignore`：是否遵守 `.gitignore`。
- `output.folder`：Markdown 輸出資料夾。
- `output.md_filename`：Markdown 檔名，預設為 `search_result.md`。

不存在的來源會顯示警告並繼續搜尋其他來源。搜尋結果為零不是錯誤，程式仍會產生 `Total: 0 files` 的 Markdown。

## 搜尋與核心架構

`main.py` 只處理選單、使用者輸入、目前 YAML 狀態與畫面訊息。`finder.py` 負責：

- 載入及驗證 YAML。
- 執行 ripgrep 檔案內容搜尋。
- 套用副檔名、include、exclude、資料夾與搜尋選項。
- 排序搜尋結果。
- 產生 Markdown。

未來 GUI 可直接使用核心，不需要啟動 CLI：

```python
from finder import generate_markdown, load_config, search_files

config = load_config("/絕對路徑/rg-search.yaml")
results = search_files(config)
generate_markdown(config, "/絕對路徑/rg-search.yaml", results)
```

## 錯誤處理

程式會顯示繁體中文訊息處理下列情況：

- YAML 路徑不是絕對路徑、檔案不存在或副檔名錯誤。
- YAML 無法解析或缺少必要設定。
- ripgrep 未安裝或執行失敗。
- Source 不存在。
- Output 或 Markdown 無法建立。
