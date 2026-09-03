package example.order;

// 範例 Repository：實際專案可能使用 JDBC、JPA、MyBatis 或 XML SQL。
public class OrderRepository {

    public Order findByOrderNo(String orderNo) {
        return jdbcTemplate.queryForObject("order.sql", orderNo);
    }
}
