package fx.service;

public class LegacyOrderService extends BaseService implements OrderService {
    public void place() {
        log("legacy");                                 // L0 call_inherited
    }
}
