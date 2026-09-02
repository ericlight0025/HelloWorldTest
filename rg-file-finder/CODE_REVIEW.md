# RG File Finder Code Review 文件

## 1. 審查範圍

本文件針對目前 RG File Finder 專案進行完整 Code Review，涵蓋：

- `finder.py`：搜尋、匯出、Markdown 報告核心邏輯
- `main.py`：CLI 操作流程
- `gui.py`：Tkinter GUI、背景執行緒與狀態管理
- YAML 設定驗證
- 檔案系統路徑與輸出安全
- Regression Tests
- GitHub Actions CI

審查重點包含：

- 正確性
- 安全性
- 可維護性
- 使用體驗
- 是否適合公開使用
- 是否還有必要繼續優化

---

## 2. 整體評估

**目前評分：9 / 10**

目前專案已經不只是單純個人 Script，而是一個具備：

- CLI
- GUI
- YAML 設定
- 共用核心
- 自動化測試
- Windows / Ubuntu CI
- 路徑安全防護
- Regression Test

的完整小型工具。

目前架構清楚，CLI 與 GUI 共用同一份核心邏輯；前面 Code Review 發現的安全問題，也大多已經轉成自動化測試。

整體判斷：

**適合個人長期使用，也已達到可以公開 GitHub 專案的程度。**

目前最大的剩餘優化方向只有搜尋效能，但在沒有實際 Benchmark 證明效能不足以前，不建議重寫搜尋核心。

---

## 3. 架構審查

### 3.1 目前架構

```text
main.py
  ↓
CLI 操作層


gui.py
  ↓
GUI 操作層

      ↓

finder.py
  ↓
搜尋 / 驗證 / 匯出 / Markdown 核心
```

### 3.2 優點

- CLI 與 GUI 都使用 `finder.py`，沒有重複實作搜尋與匯出邏輯。
- `SearchResult` 與 `ExportResult` 使用 dataclass，資料結構清楚。
- GUI 與 Core 的責任分離合理。
- YAML 是 CLI / GUI 共用的單一設定來源。
- 核心安全驗證集中在 `finder.py`，不依賴 GUI 或 CLI 幫忙擋錯誤輸入。

### 3.3 建議

目前架構已經足夠。

暫時不建議再拆成：

```text
service/
repository/
controller/
validator/
security/
```

這種更大型的分層。

對目前工具規模而言，這只會增加檔案與維護成本。

---

## 4. Command Injection 審查

### 狀態

**PASS**

目前 ripgrep 呼叫方式使用：

```python
subprocess.run(command)
```

其中 `command` 是參數陣列，而不是：

```python
subprocess.run(command, shell=True)
```

另外搜尋指令包含：

```text
--fixed-strings
--
keyword
```

因此以下輸入：

```text
--help
; rm ...
$(...)
```

不會被 Shell 執行，也不會被當成 ripgrep option。

### 結論

目前沒有發現 Command Injection 問題。

---

## 5. Path Traversal 審查

### 狀態

**PASS**

目前 `source.name` 與 `output.md_filename` 都會進行安全驗證。

會拒絕：

```text
.
..
/
\
:
NUL
控制字元
```

另外也會拒絕 Windows 保留名稱，例如：

```text
CON
PRN
AUX
NUL
COM1 ~ COM9
LPT1 ~ LPT9
```

也會拒絕以：

```text
.
空白
```

結尾的 Windows 不安全名稱。

### 結論

一般直接型 Path Traversal 已經有完整防護。

---

## 6. Symlink / Junction 路徑逃逸

### 狀態

**PASS，且已有 Defense in Depth**

過去可能出現：

```text
D:\output\project-a
        ↓ Junction
D:\important
```

程式表面上寫入：

```text
D:\output\project-a\test.sql
```

實際卻可能寫入：

```text
D:\important\test.sql
```

目前已新增 containment 驗證。

輸出時會：

1. resolve `output.folder`
2. resolve destination
3. 確認 destination 仍在 output root
4. 建立目的資料夾
5. 再檢查一次 containment
6. 最後才 copy

來源檔案本身也必須 resolve 後仍位於設定的 source root 內。

### 測試

Regression Test 已涵蓋 symlink destination escape。

Ubuntu CI 可穩定建立 symlink，因此可以補足 Windows CI 可能因權限無法建立 symlink 的問題。

---

## 7. UNC / Network Path

### 狀態

**PASS**

預設拒絕：

```text
\\server\share
//server/share
```

如果使用者確認來源可信任，可以明確設定：

```yaml
security:
  allow_network_paths: true
```

### 評估

這個設計合理。

因為如果工具公開，第三方 YAML 應視為不可信任輸入。

預設禁止 network path 可以降低 Windows 自動存取遠端 SMB 等非預期行為。

---

## 8. Source / Output 隔離

### 狀態

**PASS**

目前會禁止以下三種情況：

### 情況一：Source 與 Output 相同

```text
source = D:\project
output = D:\project
```

### 情況二：Output 放在 Source 裡

```text
source = D:\project
output = D:\project\rg-output
```

### 情況三：Source 放在 Output 裡

```text
source = D:\rg-output\project
output = D:\rg-output
```

### 為什麼需要禁止

否則第一次輸出的檔案，下一次搜尋可能又被搜尋到。

例如：

```text
D:\project\a.sql
D:\project\rg-output\project-a\a.sql
```

再執行一次後可能出現遞迴式重複輸出。

### source.name 唯一性

目前 `source.name` 也要求大小寫不敏感的唯一值。

例如：

```yaml
- name: project-a
- name: Project-A
```

會被視為重複。

這可以避免兩個來源寫入同一個 output source layer。

---

## 9. YAML 資源消耗防護

### 狀態

**PASS**

目前 YAML 已有限制：

- YAML 檔案大小
- Sources 數量
- Extensions 數量
- Include / Exclude Keywords 總數
- 單一 Keyword 長度
- Exclude Folders 數量

### YAML File Size

目前在進入：

```python
yaml.safe_load(...)
```

之前，就先檢查檔案大小。

目前上限：

```text
1 MiB
```

這樣可以避免超大型 YAML 還沒進行設定驗證，就先大量消耗記憶體。

---

## 10. Extension / Glob 安全

### 狀態

**PASS**

`extensions` 不允許直接輸入任意 glob。

例如：

```yaml
extensions:
  - "*"
```

會被拒絕。

`exclude_folders` 也不允許：

```text
*
?
[]
{}
```

等 glob wildcard。

這可以避免 YAML 設定偷偷改變原本預期的搜尋範圍。

---

## 11. Markdown Injection

### 狀態

**PASS**

以下外部文字在寫入 Markdown 前都會 escape：

- YAML path
- Source path
- Source name
- Keyword
- File name
- Original path
- Destination
- Status

例如 Keyword：

```text
safe
## injected-heading
```

不會真的產生新的 Markdown Heading。

### 結論

目前 Markdown 報告不容易被 YAML 輸入改寫文件結構。

---

## 12. Overwrite 規則

### 建議使用的新格式

```yaml
output:
  folder: 'D:\rg-output'
  preserve_structure: true
  overwrite_files: false
  overwrite_report: true
  md_filename: 'search_result.md'
```

### overwrite_files

建議：

```yaml
overwrite_files: false
```

避免程式碼、SQL 等原始檔案被意外覆寫。

### overwrite_report

建議：

```yaml
overwrite_report: true
```

因為 Markdown 是搜尋報告，通常希望每次執行都更新。

### 舊版相容

舊設定仍支援：

```yaml
overwrite: false
```

如果新舊欄位同時存在：

```yaml
overwrite: false
overwrite_files: true
overwrite_report: true
```

則新欄位優先。

### 評估

這個相容策略合理，可以避免舊 YAML 升級後突然失效。

---

## 13. GUI Thread Safety 審查

### 狀態

**PASS**

目前 GUI 使用：

```text
Worker Thread
    ↓
Queue
    ↓
Tk Main Thread
```

Worker 不直接操作 Tk widget。

### 已完成的改善

- Search 使用背景 Thread。
- Copy 使用背景 Thread。
- Worker 結果透過 Queue 回傳。
- Tk GUI 只在 Main Thread 更新。
- 搜尋前會 deepcopy config snapshot。
- Copy 前會 snapshot selected results。
- Busy 狀態期間停用操作按鈕。
- 避免重複啟動 Search / Copy。
- 未預期例外也會回到 GUI 顯示，不會讓 Busy 永久卡住。

### 結論

目前 Tkinter 架構對此工具已經足夠。

暫時沒有必要改成：

```text
asyncio
multiprocessing
PyQt
Electron
Web UI
```

---

## 14. Search Logic 審查

### Include Keyword

採 OR。

例如：

```yaml
include_keywords:
  - policy
  - customer
```

只要檔案命中其中一個就會成為候選。

### Exclude Keyword

只要檔案命中任一 exclude keyword，整個檔案排除。

### 目前效能特性

目前每一個 keyword 都會對每個 source 執行一次 ripgrep。

假設：

```text
3 sources
20 include keywords
10 exclude keywords
```

最多可能執行：

```text
3 × 30 = 90 次 rg
```

### 可能的未來優化

未來可以評估：

```text
rg --json
```

改成單次或較少次掃描。

### 現在要不要改？

**不建議。**

目前應該先用真實工作資料 Benchmark。

建議測試：

```text
10,000 files
50,000 files
100,000 files
```

搭配：

```text
5 keywords
20 keywords
50 keywords
```

紀錄：

```text
搜尋時間
CPU
記憶體
```

真的出現明顯瓶頸，再開獨立效能 PR。

---

## 15. Regression Test 審查

目前測試已涵蓋：

- 正常 YAML
- 不安全 source.name
- Windows 保留名稱
- 不安全 Markdown filename
- 非 Boolean 設定
- UNC source 拒絕
- UNC output 拒絕
- Network path 明確 opt-in
- 不安全 Extension / Glob
- 不安全 Exclude Folder Glob
- Keyword 數量上限
- Keyword 長度上限
- Source file 逃出 source root
- Symlink destination escape
- Source / Output overlap
- Duplicate source name
- YAML 檔案過大
- File overwrite
- Report overwrite
- 舊版 overwrite 相容性
- 新 overwrite 欄位優先順序
- Markdown escape
- CLI selection parser

### 評估

這是目前專案很重要的優點。

安全問題不只被「修掉」，還有測試防止未來 Regression。

---

## 16. CI 審查

GitHub Actions 目前使用：

```text
Python 3.13
```

Runner：

```text
windows-latest
ubuntu-latest
```

執行：

```text
安裝 ripgrep
安裝 requirements-dev.txt
py_compile
pytest
```

### Windows CI

主要驗證實際主要使用環境與 Windows Path 行為。

### Ubuntu CI

主要補足 symlink containment 測試。

### 結論

雙平台 CI 對目前工具非常合理。

---

## 17. 可維護性審查

### 建議保留

- Runtime dependency 維持少量。
- PyYAML 暫時維持唯一主要第三方 Runtime dependency。
- 安全驗證集中在 Core。
- CLI / GUI 共用 Core。
- Regression Test 跟著問題一起新增。
- YAML Schema 保持簡單。

### 暫時不要做

目前沒有實際需求時，不建議加入：

```text
Database
Plugin Architecture
Web Server
Electron
Multiprocessing
自建搜尋 Index
大型 YAML Schema Framework
Auto Update System
```

這些功能增加的維護成本，會遠高於目前工具實際收益。

---

## 18. Merge Checklist

未來每次 PR Merge 前，建議確認：

- [ ] Windows CI 通過
- [ ] Ubuntu CI 通過
- [ ] `py_compile` 通過
- [ ] pytest 通過
- [ ] 新 YAML 欄位已有 README 說明
- [ ] 舊 YAML 相容性已確認
- [ ] 所有輸出仍限制在 `output.folder`
- [ ] 所有搜尋結果仍限制在 Source Root
- [ ] Source / Output 不互相包含
- [ ] GUI Worker 沒有直接操作 Tk Widget
- [ ] 新設定不會導致無限制搜尋或寫入
- [ ] 安全修正有 Regression Test

---

## 19. 剩餘 Backlog

### P2：搜尋效能 Benchmark

實際大型 Repo 搜尋變慢時，再量測：

```text
檔案數 × Keyword 數 × Source 數
```

確認瓶頸後再考慮 `rg --json`。

### P3：Python Packaging

如果未來公開使用者增加，可以評估新增：

```text
pyproject.toml
```

以及 console entry point，例如：

```text
rg-file-finder
```

目前不是必要項目。

### P3：Release / Version

如果開始有外部使用者依賴，可以增加：

```text
v1.0.0
v1.1.0
CHANGELOG.md
```

目前也不影響功能。

---

## 20. 最終結論

目前 RG File Finder 已經到一個很好的停止點。

前面 Review 發現的重要問題，包括：

- GUI Race Condition
- Path Traversal
- Symlink / Junction Escape
- UNC Path
- Markdown Overwrite
- Markdown Injection
- Source / Output Recursive Search
- Duplicate Source Name
- YAML Resource Limit

都已經處理，而且多數都有 Regression Test。

### 最終評價

**程式品質：9 / 10**

**個人長期使用：適合**

**公開 GitHub：適合**

**目前是否需要繼續大改：不需要**

接下來最有價值的事情是實際使用。

未來只有在真實資料證明搜尋速度不足，或出現新的使用需求時，再開新的 PR。

目前不建議為了「可能會更快」或「架構看起來更漂亮」而繼續重構。