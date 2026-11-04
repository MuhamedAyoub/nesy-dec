package fx.service;

import fx.Audited;

@Audited
public class OrderServiceImpl implements OrderService {
    private Notifier notifier;

    public void place() {
        notifier.send("placed");                       // L1 cha, one implementation
    }
}
