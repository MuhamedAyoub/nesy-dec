package fx.web;

import org.springframework.context.ApplicationContext;

public class SpringClient {
    private ApplicationContext ctx;

    public Object get() {
        return ctx.getBean("orderService");            // L2 spring_getbean -> OrderServiceImpl
    }
}
