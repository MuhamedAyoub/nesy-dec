package fx.repo;

public class JdbcItemDao {
    // "select * from orders" in a comment must not count
    private static final String SQL = "select * from " + "item_tbl where id = ?";   // L3 sql_table
}
