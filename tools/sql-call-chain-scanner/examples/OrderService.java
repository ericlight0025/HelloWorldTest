package example.order;

// 範例 Service：接收 Controller 請求並呼叫 Repository。
public class OrderService {

    private final OrderRepository orderRepository;

    public Order queryOrder(String orderNo) {
        return orderRepository.findByOrderNo(orderNo);
    }
}
