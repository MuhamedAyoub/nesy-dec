package fx.domain;

import javax.persistence.Entity;
import javax.persistence.ManyToOne;
import javax.persistence.Table;

@Entity
@Table(name = "item_tbl")
public class Item {
    @ManyToOne
    private Order order;                               // L3 jpa_assoc Item -> Order

    public Integer getPrice() { return 1; }
}
