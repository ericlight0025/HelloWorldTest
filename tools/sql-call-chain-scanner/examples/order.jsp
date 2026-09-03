<%-- 範例 JSP：畫面載入 JavaScript，並由 JS 呼叫後端查詢訂單。 --%>
<%@ page contentType="text/html; charset=UTF-8" %>
<!DOCTYPE html>
<html>
<head>
    <title>訂單查詢</title>
    <script src="/static/order.js"></script>
</head>
<body>
    <button onclick="queryOrder('A0001')">查詢訂單</button>
</body>
</html>
