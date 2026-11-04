package javax.persistence;
public @interface OneToMany { String mappedBy() default ""; }
