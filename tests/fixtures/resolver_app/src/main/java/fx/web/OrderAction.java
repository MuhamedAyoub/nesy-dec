package fx.web;

import fx.service.OrderService;

public class OrderAction {
    private OrderService orderService;

    public void setOrderService(OrderService s) { this.orderService = s; }

    public void execute() {
        orderService.place();                          // L2 spring_xml_property -> OrderServiceImpl only
    }
}
