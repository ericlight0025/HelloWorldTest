# RG File Finder

以 `ripgrep (rg)` 的 `rg --files` 列出候選路徑，再由 Python **只比對檔名**的搜尋與匯出工具。程式不搜尋或修改檔案內容；搜尋核心可由 CLI 及未來 GUI 直接重用。

## Requirement

- Python 3.10+
- ripgrep
- PyYAML

```bash
pip install pyyaml
rg --version
```

請先依環境修改 `config.yaml` 的來源及輸出資料夾。

## Basic Usage

```bash
python main.py -k policy
```

### Negative Search

`-x` 可重複使用，也可用逗號分隔；內容會與 YAML 排除詞合併。

```bash
python main.py -k policy -x test,backup
python main.py -k policy -x query -x mapper
```

### Interactive Copy

```bash
python main.py -k policy --copy
```

可輸入 `1`、`1,3,5` 或 `1,3,5-8,12`。

### Direct Selection / Copy All

```bash
python main.py -k policy --select 1,3,5-7
python main.py -k policy --copy-all
```

每次複製流程均依設定產生 `search_result.md` manifest，內容只有搜尋條件與路徑，不含檔案內容。

## CLI Overrides

```bash
python main.py -k policy --copy-all -o "D:\temp"
python main.py -k policy --ext sql,java
python main.py -k policy --source "C:\project-a" --source "D:\project-b"
python main.py -c another-config.yaml -k policy
```

`--source` 完全取代 YAML sources，`--ext` 完全取代 YAML extensions，`-o` 優先於 YAML output folder。

## Python Core API

GUI 或其他 Python 程式可直接使用核心，不需啟動 CLI：

```python
from finder import load_config, search_files

config = load_config("config.yaml")
results = search_files(config, "policy", extra_excludes=["query"])
```

主要公開功能另包含 `export_files()` 與 `generate_markdown()`。不存在的來源只會顯示警告並略過；同名檔案以來源名稱作為輸出第一層目錄，避免不同專案互相覆蓋。
