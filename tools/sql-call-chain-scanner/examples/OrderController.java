package example.order;

// 範例 Controller：實際專案可使用 Spring MVC 的 Mapping 註解。
@RequestMapping("/order")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/query")
    public Order queryOrder(String orderNo) {
        return orderService.queryOrder(orderNo);
    }
}
