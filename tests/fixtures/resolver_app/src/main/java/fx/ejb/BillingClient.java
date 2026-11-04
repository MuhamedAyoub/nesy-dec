package fx.ejb;

import javax.naming.InitialContext;

public class BillingClient {
    public void go(String name) throws Exception {
        InitialContext ctx = new InitialContext();
        ctx.lookup("java:comp/env/ejb/Billing");       // L2 jndi_ejb -> BillingBean
        ctx.lookup(name);                              // refused: lookup_nonliteral
        ctx.lookup("java:comp/UserTransaction");       // external container resource
    }
}
