package fx.repo;

import fx.domain.Order;
import javax.persistence.EntityManager;
import javax.persistence.PersistenceContext;

public class OrderRepo {
    @PersistenceContext
    private EntityManager em;

    public Object load(long id) {
        em.createNamedQuery("Order.all");              // L3 jpa_named_query
        return em.find(Order.class, id);               // L3 entity_class_literal
    }
}
