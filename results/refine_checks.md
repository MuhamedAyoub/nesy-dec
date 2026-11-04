### 1. Classes the refinement moved (teacher service -> refined service, each named by its members)

**jpetstore-6**: 2 classes moved

- `Item`: from the service of Cart, CartItem, Product to the service of CatalogActionBean, CatalogService, ItemMapper, Product, ProductMapper
- `Product`: from the service of Cart, CartItem, Item to the service of CatalogActionBean, CatalogService, Item, ItemMapper, ProductMapper

**daytrader7**: 16 classes moved

- `KeySequenceDirect`: from the service of CompleteOrderThread, PingInterceptorBinding, PingJDBCRead, PingJDBCRead2JSP, PingJDBCWrite, PingServlet2Include to the service of AccountDataBean, AccountDataJSF, AccountProfileDataBean, CompleteOrderThread, FinancialUtils, Handler
- `quotePriceComparator`: from the service of HoldingData, LoginValidator, OrderData, OrderDataJSF, PingManagedThread, PortfolioJSF to the service of AccountDataBean, AccountDataJSF, AccountProfileDataBean, CompleteOrderThread, FinancialUtils, Handler
- `TradeSLSBRemote`: from the service of ExplicitGC, KeyBlock, KeyBlockIterator, PingServlet2ServletRcv to the service of AccountDataBean, AccountDataJSF, AccountProfileDataBean, CompleteOrderThread, FinancialUtils, Handler
- `CompleteOrderThread`: from the service of KeySequenceDirect, PingInterceptorBinding, PingJDBCRead, PingJDBCRead2JSP, PingJDBCWrite, PingServlet2Include to the service of AccountDataBean, AccountDataJSF, AccountProfileDataBean, FinancialUtils, Handler, HoldingDataBean
- `LoginValidator`: from the service of HoldingData, OrderData, OrderDataJSF, PingManagedThread, PortfolioJSF, quotePriceComparator to the service of AccountDataBean, AccountDataJSF, AccountProfileDataBean, CompleteOrderThread, FinancialUtils, Handler
- `TradeActionProducer`: from the service of DTBroker3MDB, DTStreamer3MDB, MDBStats, PingInterceptor, PingServlet2Servlet, PingServlet2SessionLocal to the service of AccountDataBean, AccountDataJSF, AccountProfileDataBean, CompleteOrderThread, FinancialUtils, Handler
- `PingJDBCRead`: from the service of CompleteOrderThread, KeySequenceDirect, PingInterceptorBinding, PingJDBCRead2JSP, PingJDBCWrite, PingServlet2Include to the service of AccountDataBean, AccountDataJSF, AccountProfileDataBean, CompleteOrderThread, FinancialUtils, Handler
- `PingServletCDIBeanManagerViaCDICurrent`: from the service of PingCDIBean, PingEJBIFace, PingEJBLocalDecorator, PingServletCDI to the service of AccountDataBean, AccountDataJSF, AccountProfileDataBean, CompleteOrderThread, FinancialUtils, Handler
- `PingSession3Object`: from the service of CompleteOrderThread, KeySequenceDirect, PingInterceptorBinding, PingJDBCRead, PingJDBCRead2JSP, PingJDBCWrite to the service of AccountDataBean, AccountDataJSF, AccountProfileDataBean, CompleteOrderThread, FinancialUtils, Handler
- `MarketSummaryWebSocket`: from the service of AccountDataBean, AccountDataJSF, AccountProfileDataBean, FinancialUtils, Handler, HoldingDataBean to the service of ActionDecoder, ActionMessage
- `PingServlet2Servlet`: from the service of DTBroker3MDB, DTStreamer3MDB, MDBStats, PingInterceptor, PingServlet2SessionLocal, TimerStat to the service of PingBean, PingServlet2Jsp, PingServlet2PDF, PingServlet2ServletRcv
- `PingServlet2ServletRcv`: from the service of ExplicitGC, KeyBlock, KeyBlockIterator, TradeSLSBRemote to the service of PingBean, PingServlet2Jsp, PingServlet2PDF, PingServlet2Servlet
- `TradeSLSBLocal`: from the service of DTBroker3MDB, DTStreamer3MDB, MDBStats, PingInterceptor, PingServlet2Servlet, PingServlet2SessionLocal to the service of ExplicitGC, KeyBlock, KeyBlockIterator, PingServlet2SessionLocal
- `PingServlet2SessionLocal`: from the service of DTBroker3MDB, DTStreamer3MDB, MDBStats, PingInterceptor, PingServlet2Servlet, TimerStat to the service of ExplicitGC, KeyBlock, KeyBlockIterator, TradeSLSBLocal
- `PingInterceptor`: from the service of DTBroker3MDB, DTStreamer3MDB, MDBStats, PingServlet2Servlet, PingServlet2SessionLocal, TimerStat to the service of PingInterceptorBinding, PingJDBCRead2JSP, PingJDBCWrite, PingServlet2Include, PingServlet2JNDI, PingServlet2MDBQueue
- `PingEJBLocal`: from the service of JsonDecoder, JsonEncoder, JsonMessage, PingServletCDIBeanManagerViaJNDI, PingWebSocketJson to the service of PingCDIBean, PingEJBIFace, PingEJBLocalDecorator, PingServletCDI

### 2. Measures outside the objective (teacher -> refined)

| app | data cohesion | entity spread (lower better) | semantic cohesion | must-link kept |
|---|---|---|---|---|
| jpetstore-6 | 0.000 -> 0.000 | 1.00 -> 1.00 | 0.426 -> 0.457 | 0.58 -> 0.75 |
| acmeair | 0.000 -> 0.000 | 1.00 -> 1.00 | 0.453 -> 0.479 | 0.54 -> 0.46 |
| daytrader7 | 0.001 -> 0.001 | 1.00 -> 1.00 | 0.356 -> 0.379 | 0.74 -> 0.79 |
| plantsbywebsphere | 0.012 -> 0.009 | 1.83 -> 1.83 | 0.331 -> 0.336 | 0.58 -> 0.61 |
| lit-jpetstore | 0.022 -> 0.042 | 1.00 -> 1.00 | 0.456 -> 0.507 | 0.57 -> 0.52 |
| lit-pbw | 0.009 -> 0.011 | 1.83 -> 1.83 | 0.368 -> 0.391 | 0.51 -> 0.59 |

### 3. Hill-climb from other starts (held-out weerasinghe Score in the nine-method pool; teacher's in brackets)

| app | from teacher | from NeSy-Rep + Ward | from random s42 | from random s1 | from random s7 |
|---|---|---|---|---|---|
| jpetstore-6 | +0.72 (+0.24), 2 moves | +0.69 (+0.25), 3 moves | +0.81 (+0.23), 11 moves | +0.68 (+0.25), 14 moves | +0.70 (+0.24), 8 moves |
| acmeair | +0.77 (+0.58), 18 moves | +1.06 (+0.43), 16 moves | +1.08 (+0.39), 66 moves | +1.02 (+0.44), 59 moves | +0.90 (+0.51), 52 moves |
| daytrader7 | +0.90 (+0.44), 17 moves | +1.20 (+0.18), 24 moves | +1.20 (+0.11), 67 moves | +1.20 (+0.13), 64 moves | +1.26 (+0.05), 70 moves |
| plantsbywebsphere | +1.10 (+0.77), 4 moves | +0.95 (+0.83), 5 moves | +0.96 (+0.86), 17 moves | +1.14 (+0.70), 22 moves | +1.14 (+0.70), 19 moves |
| lit-jpetstore | +1.09 (+0.54), 19 moves | +0.97 (+0.60), 21 moves | +1.14 (+0.44), 39 moves | +0.94 (+0.62), 46 moves | +1.26 (+0.27), 53 moves |
| lit-pbw | +1.00 (+0.77), 6 moves | +1.16 (+0.53), 10 moves | +1.01 (+0.72), 20 moves | +0.93 (+0.76), 26 moves | +0.95 (+0.68), 12 moves |
