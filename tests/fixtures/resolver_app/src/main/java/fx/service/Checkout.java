package fx.service;

import fx.Constants;
import fx.domain.Customer;
import fx.domain.Item;
import fx.domain.Order;
import java.util.List;
import java.util.function.Function;

public class Checkout {
    private Pricing pricing;
    private Customer customer;                         // J-T type_use only

    public int total(List<Item> items) {
        Order o = new Order();                         // L0 creation
        Function<Item, Integer> f = Item::getPrice;    // L0 method_ref
        int first = items.get(0).getPrice();           // L0 call_declared
        return pricing.price() + Constants.MAX;        // L1 cha 1/2 each; L0 field_ref
    }
}
