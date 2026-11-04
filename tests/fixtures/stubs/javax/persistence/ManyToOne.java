package javax.persistence;
public @interface ManyToOne { String mappedBy() default ""; }
