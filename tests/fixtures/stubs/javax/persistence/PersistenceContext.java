package javax.persistence;
public @interface PersistenceContext { String mappedBy() default ""; }
