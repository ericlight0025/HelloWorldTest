# SQL Call Chain Scanner

掃描 JSP、JavaScript、Spring Controller、Service、DAO／Repository 與 SQL，產生可能的呼叫鏈報告。
Java Controller／Service／Repository 使用 JavaParser AST 解析方法與方法呼叫，JSP／JS／SQL 使用對應的語法規則分析。

## 建置

```bash
mvn clean package
```

## 使用

```bash
java -jar target/sql-call-chain-scanner-1.0.0.jar <專案路徑> <入口關鍵字> [輸出檔]
```

## 範例

```bash
java -jar target/sql-call-chain-scanner-1.0.0.jar D:/legacy-system order.jsp report.md
java -jar target/sql-call-chain-scanner-1.0.0.jar D:/legacy-system /order/query report.md
java -jar target/sql-call-chain-scanner-1.0.0.jar D:/legacy-system POLICY_NO report.md
```

## 內建範例程式

`examples` 資料夾包含完整示範：

```text
order.jsp
  ↓
order.js：queryOrder()
  ↓
OrderController.java：queryOrder()
  ↓
OrderService.java：queryOrder()
  ↓
OrderRepository.java：findByOrderNo()
  ↓
order.sql：SELECT POLICY_NO ...
```

測試範例：

```bash
java -jar target/sql-call-chain-scanner-1.0.0.jar examples order.jsp examples-report.md
```

輸入 JSP 檔名後，工具會將 AST 方法呼叫與前端 URL、SQL 檔案引用合併，輸出可能的業務流程；反射、AOP、動態 SQL 與框架代理仍需人工複核。

## 注意事項

這是靜態分析工具，會以檔案內容、方法名稱、Spring Mapping 與 SQL 關鍵字建立候選呼叫鏈。反射、AOP、XML 設定、動態 SQL、共用方法及框架代理可能需要人工確認。
