// 範例 JavaScript：呼叫 Spring Controller 的查詢 API。
function queryOrder(orderNo) {
    return fetch('/order/query?orderNo=' + orderNo, {
        method: 'GET'
    }).then(response => response.json());
}
