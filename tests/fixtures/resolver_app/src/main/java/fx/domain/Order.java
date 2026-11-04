package fx.domain;

import java.util.List;
import javax.persistence.Entity;
import javax.persistence.NamedQueries;
import javax.persistence.NamedQuery;
import javax.persistence.OneToMany;
import javax.persistence.Table;

@Entity
@Table(name = "orders")
@NamedQueries({ @NamedQuery(name = "Order.all", query = "select o from Order o") })
public class Order {
    @OneToMany(mappedBy = "order")
    private List<Item> items;                          // L3 jpa_assoc Order -> Item
}
