-- 範例 SQL：Repository 最後載入並執行這支 SQL。
SELECT ORDER_NO,
       POLICY_NO,
       CUSTOMER_NAME,
       TOTAL_AMOUNT
  FROM CUSTOMER_ORDER
 WHERE ORDER_NO = :orderNo;
