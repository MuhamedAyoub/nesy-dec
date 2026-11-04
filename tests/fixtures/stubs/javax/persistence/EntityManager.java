package javax.persistence;
public interface EntityManager {
    <T> T find(Class<T> type, Object id);
    Object createNamedQuery(String name);
}
