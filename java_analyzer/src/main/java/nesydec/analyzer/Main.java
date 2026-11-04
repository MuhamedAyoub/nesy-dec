package nesydec.analyzer;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Modifier;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.NodeList;
import com.github.javaparser.ast.body.*;
import com.github.javaparser.ast.expr.*;
import com.github.javaparser.ast.stmt.LocalClassDeclarationStmt;
import com.github.javaparser.ast.stmt.LocalRecordDeclarationStmt;
import com.github.javaparser.ast.type.ClassOrInterfaceType;
import com.github.javaparser.ast.type.Type;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.resolution.types.ResolvedReferenceType;
import com.github.javaparser.resolution.types.ResolvedType;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JarTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ClassLoaderTypeSolver;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * Fact extractor for one Java application.
 *
 * Usage: java -jar java-analyzer.jar CONFIG.json OUT_DIR
 *
 * CONFIG: {"app": str, "sourceRoots": [dir...], "classpath": [jar...],
 *          "languageLevel": "JAVA_17"}
 *
 * Writes to OUT_DIR:
 *   inventory.json    one record per class node (top-level or named member
 *                     type; local and anonymous classes fold into their
 *                     enclosing node)
 *   callsites.jsonl   one record per method call expression
 *   creations.jsonl   one record per object creation expression
 *   methodrefs.jsonl  one record per method reference expression
 *   fieldrefs.jsonl   one record per field read or write that resolves to a
 *                     field (name or field-access expression), and one per
 *                     class literal (X.class) anywhere in the code
 *   run.json          configuration, type solvers loaded or skipped, parse
 *                     problems, counts
 *
 * Nothing is inferred here: every resolution failure is recorded with its
 * exception type, so later stages can count refusals instead of guessing.
 */
public final class Main {
    static final String VERSION = "0.2.0";
    static final Gson GSON = new GsonBuilder().disableHtmlEscaping().serializeNulls().create();

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("usage: java -jar java-analyzer.jar CONFIG.json OUT_DIR");
            System.exit(2);
        }
        JsonObject cfg = GSON.fromJson(Files.readString(Paths.get(args[0])), JsonObject.class);
        Path out = Paths.get(args[1]);
        Files.createDirectories(out);
        new Main().run(cfg, out);
    }

    private final Map<String, Object> runInfo = new LinkedHashMap<>();

    void run(JsonObject cfg, Path out) throws IOException {
        long t0 = System.currentTimeMillis();
        List<Path> roots = new ArrayList<>();
        cfg.getAsJsonArray("sourceRoots").forEach(e -> roots.add(Paths.get(e.getAsString())));
        List<Path> cp = new ArrayList<>();
        if (cfg.has("classpath")) cfg.getAsJsonArray("classpath").forEach(e -> cp.add(Paths.get(e.getAsString())));
        String level = cfg.has("languageLevel") ? cfg.get("languageLevel").getAsString() : "JAVA_17";

        ParserConfiguration pc = new ParserConfiguration()
                .setLanguageLevel(ParserConfiguration.LanguageLevel.valueOf(level));

        CombinedTypeSolver ts = new CombinedTypeSolver();
        // Every JDK module (java.*, javax.*, org.w3c.*, org.xml.*, ...) through
        // the platform loader, and nothing from the analyzer's own classpath.
        // ReflectionTypeSolver(true) admits only java.* and javax.*, which left
        // org.w3c.dom calls unresolved.
        ts.add(new ClassLoaderTypeSolver(ClassLoader.getPlatformClassLoader()));
        for (Path r : roots) ts.add(new JavaParserTypeSolver(r, pc));   // app source wins over jars
        List<String> jarsLoaded = new ArrayList<>(), jarsSkipped = new ArrayList<>();
        for (Path p : cp) {
            String s = p.toString();
            if (!Files.isRegularFile(p) || !s.endsWith(".jar")) { jarsSkipped.add(s + " (not a jar file)"); continue; }
            try { ts.add(new JarTypeSolver(p)); jarsLoaded.add(s); }
            catch (Throwable e) { jarsSkipped.add(s + " (" + e.getClass().getSimpleName() + ")"); }
        }
        pc.setSymbolResolver(new JavaSymbolSolver(ts));
        JavaParser parser = new JavaParser(pc);

        List<Path> files = new ArrayList<>();
        for (Path r : roots) {
            try (Stream<Path> s = Files.walk(r)) {
                s.filter(p -> p.toString().endsWith(".java")).sorted().forEach(files::add);
            }
        }

        List<Map<String, Object>> inventory = new ArrayList<>();
        List<Map<String, Object>> parseProblems = new ArrayList<>();
        int nCalls = 0, nCreations = 0, nRefs = 0, nFieldRefs = 0;
        try (BufferedWriter calls = w(out.resolve("callsites.jsonl"));
             BufferedWriter creations = w(out.resolve("creations.jsonl"));
             BufferedWriter refs = w(out.resolve("methodrefs.jsonl"));
             BufferedWriter frefs = w(out.resolve("fieldrefs.jsonl"))) {
            for (Path f : files) {
                ParseResult<CompilationUnit> pr = parser.parse(f);
                if (!pr.isSuccessful() || pr.getResult().isEmpty()) {
                    parseProblems.add(Map.of("file", f.toString(),
                            "problems", pr.getProblems().stream().map(Object::toString).limit(5).collect(Collectors.toList())));
                    continue;
                }
                CompilationUnit cu = pr.getResult().get();
                String file = f.toString();
                for (TypeDeclaration<?> td : cu.findAll(TypeDeclaration.class)) {
                    if (isLocal(td)) continue;
                    inventory.add(typeRecord(td, file));
                }
                for (MethodCallExpr mc : cu.findAll(MethodCallExpr.class)) {
                    calls.write(GSON.toJson(callRecord(mc, file))); calls.newLine(); nCalls++;
                }
                for (ObjectCreationExpr oc : cu.findAll(ObjectCreationExpr.class)) {
                    creations.write(GSON.toJson(creationRecord(oc, file))); creations.newLine(); nCreations++;
                }
                for (MethodReferenceExpr mr : cu.findAll(MethodReferenceExpr.class)) {
                    refs.write(GSON.toJson(methodRefRecord(mr, file))); refs.newLine(); nRefs++;
                }
                for (FieldAccessExpr fa : cu.findAll(FieldAccessExpr.class)) {
                    Map<String, Object> r = fieldRefRecord(fa, file);
                    if (r != null) { frefs.write(GSON.toJson(r)); frefs.newLine(); nFieldRefs++; }
                }
                for (NameExpr ne : cu.findAll(NameExpr.class)) {
                    Map<String, Object> r = fieldRefRecord(ne, file);
                    if (r != null) { frefs.write(GSON.toJson(r)); frefs.newLine(); nFieldRefs++; }
                }
                for (ClassExpr ce : cu.findAll(ClassExpr.class)) {
                    frefs.write(GSON.toJson(classLiteralRecord(ce, file))); frefs.newLine(); nFieldRefs++;
                }
            }
        }
        Files.writeString(out.resolve("inventory.json"), GSON.toJson(inventory), StandardCharsets.UTF_8);

        runInfo.put("analyzer_version", VERSION);
        runInfo.put("javaparser_version", "3.26.2");
        runInfo.put("config", cfg);
        runInfo.put("java_files", files.size());
        runInfo.put("parse_failures", parseProblems);
        runInfo.put("jars_loaded", jarsLoaded.size());
        runInfo.put("jars_skipped", jarsSkipped);
        runInfo.put("class_nodes", inventory.size());
        runInfo.put("call_sites", nCalls);
        runInfo.put("object_creations", nCreations);
        runInfo.put("method_references", nRefs);
        runInfo.put("field_and_class_literal_refs", nFieldRefs);
        runInfo.put("seconds", (System.currentTimeMillis() - t0) / 1000.0);
        Files.writeString(out.resolve("run.json"), new GsonBuilder().setPrettyPrinting().disableHtmlEscaping()
                .serializeNulls().create().toJson(runInfo), StandardCharsets.UTF_8);
        System.err.printf("[analyzer] %s: %d files, %d class nodes, %d calls, %d creations, %d parse failures, %.1fs%n",
                cfg.get("app").getAsString(), files.size(), inventory.size(), nCalls, nCreations,
                parseProblems.size(), (System.currentTimeMillis() - t0) / 1000.0);
    }

    // ------------------------------------------------------------------ nodes

    /** Local classes and records fold into their enclosing class node. */
    static boolean isLocal(TypeDeclaration<?> td) {
        Optional<Node> p = td.getParentNode();
        return p.isPresent() && (p.get() instanceof LocalClassDeclarationStmt
                || p.get() instanceof LocalRecordDeclarationStmt);
    }

    /** The class node that owns a syntax node: nearest non-local enclosing type. */
    static Optional<TypeDeclaration<?>> ownerOf(Node n) {
        Node cur = n.getParentNode().orElse(null);
        while (cur != null) {
            if (cur instanceof TypeDeclaration<?> td && !isLocal(td)) return Optional.of(td);
            cur = cur.getParentNode().orElse(null);
        }
        return Optional.empty();
    }

    static String nameOf(TypeDeclaration<?> td) {
        return td.getFullyQualifiedName().orElse(td.getNameAsString());
    }

    static String ownerName(Node n) {
        return ownerOf(n).map(Main::nameOf).orElse(null);
    }

    /** Is this syntax node inside an anonymous class body or a lambda, below its owner? */
    static String enclosingContext(Node n) {
        Node cur = n.getParentNode().orElse(null);
        while (cur != null) {
            if (cur instanceof TypeDeclaration<?> td && !isLocal(td)) return "member";
            if (cur instanceof ObjectCreationExpr oc && oc.getAnonymousClassBody().isPresent()) return "anonymous";
            if (cur instanceof LocalClassDeclarationStmt) return "local";
            if (cur instanceof LambdaExpr) return "lambda";
            cur = cur.getParentNode().orElse(null);
        }
        return "none";
    }

    static Map<String, Object> typeRecord(TypeDeclaration<?> td, String file) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("name", nameOf(td));
        String kind = td instanceof ClassOrInterfaceDeclaration c ? (c.isInterface() ? "interface" : "class")
                : td instanceof EnumDeclaration ? "enum"
                : td instanceof AnnotationDeclaration ? "annotation"
                : td instanceof RecordDeclaration ? "record" : td.getClass().getSimpleName();
        r.put("kind", kind);
        r.put("abstract", td.hasModifier(Modifier.Keyword.ABSTRACT));
        r.put("top_level", td.isTopLevelType());
        r.put("enclosing", td.isTopLevelType() ? null : ownerName(td));
        r.put("file", file);
        r.put("line", td.getBegin().map(p -> p.line).orElse(-1));
        r.put("annotations", annotations(td.getAnnotations()));
        List<Map<String, Object>> ext = new ArrayList<>(), impl = new ArrayList<>();
        if (td instanceof ClassOrInterfaceDeclaration c) {
            c.getExtendedTypes().forEach(t -> ext.add(typeRef(t)));
            c.getImplementedTypes().forEach(t -> impl.add(typeRef(t)));
        } else if (td instanceof EnumDeclaration e) {
            e.getImplementedTypes().forEach(t -> impl.add(typeRef(t)));
        } else if (td instanceof RecordDeclaration rd) {
            rd.getImplementedTypes().forEach(t -> impl.add(typeRef(t)));
        }
        r.put("extends", ext);
        r.put("implements", impl);

        List<Map<String, Object>> fields = new ArrayList<>();
        for (FieldDeclaration fd : td.getFields()) {
            for (VariableDeclarator v : fd.getVariables()) {
                Map<String, Object> f = new LinkedHashMap<>();
                f.put("name", v.getNameAsString());
                f.put("type", typeInfo(v.getType()));
                f.put("static", fd.isStatic());
                f.put("annotations", annotations(fd.getAnnotations()));
                f.put("line", v.getBegin().map(p -> p.line).orElse(-1));
                f.put("init", v.getInitializer().map(i -> trunc(i.toString(), 160)).orElse(null));
                fields.add(f);
            }
        }
        r.put("fields", fields);

        List<Map<String, Object>> ctors = new ArrayList<>();
        for (ConstructorDeclaration c : td.getConstructors()) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("annotations", annotations(c.getAnnotations()));
            m.put("params", params(c.getParameters()));
            m.put("line", c.getBegin().map(p -> p.line).orElse(-1));
            ctors.add(m);
        }
        r.put("constructors", ctors);

        List<Map<String, Object>> methods = new ArrayList<>();
        for (MethodDeclaration md : td.getMethods()) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("name", md.getNameAsString());
            m.put("static", md.isStatic());
            m.put("abstract", md.isAbstract() || (kind.equals("interface") && md.getBody().isEmpty()));
            m.put("returns", typeInfo(md.getType()));
            m.put("params", params(md.getParameters()));
            m.put("annotations", annotations(md.getAnnotations()));
            m.put("line", md.getBegin().map(p -> p.line).orElse(-1));
            methods.add(m);
        }
        r.put("methods", methods);
        return r;
    }

    static List<Map<String, Object>> params(NodeList<Parameter> ps) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Parameter p : ps) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("name", p.getNameAsString());
            m.put("type", typeInfo(p.getType()));
            m.put("annotations", annotations(p.getAnnotations()));
            out.add(m);
        }
        return out;
    }

    static List<String> annotations(NodeList<AnnotationExpr> as) {
        return as.stream().map(a -> trunc(a.toString(), 240)).collect(Collectors.toList());
    }

    // ------------------------------------------------------------------ types

    static Map<String, Object> typeRef(ClassOrInterfaceType t) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("raw", t.getNameWithScope());
        try {
            ResolvedType rt = t.resolve();
            m.put("resolved", erasure(rt));
        } catch (Throwable e) {
            m.put("resolved", null);
            m.put("error", err(e));
        }
        return m;
    }

    /** Declared type: raw text, erasure, and type arguments (for List<Order> and friends). */
    static Map<String, Object> typeInfo(Type t) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("raw", trunc(t.asString(), 160));
        try {
            ResolvedType rt = t.resolve();
            m.put("erasure", erasure(rt));
            m.put("args", typeArgs(rt));
        } catch (Throwable e) {
            m.put("erasure", null);
            m.put("error", err(e));
        }
        return m;
    }

    static String erasure(ResolvedType rt) {
        if (rt == null) return null;
        if (rt.isReferenceType()) return rt.asReferenceType().getQualifiedName();
        if (rt.isArray()) return erasure(rt.asArrayType().getComponentType()) + "[]";
        if (rt.isPrimitive()) return rt.asPrimitive().describe();
        if (rt.isVoid()) return "void";
        if (rt.isTypeVariable()) return "typevar:" + rt.asTypeVariable().describe();
        if (rt.isWildcard()) return rt.asWildcard().isBounded() ? erasure(rt.asWildcard().getBoundedType()) : "?";
        if (rt.isNull()) return "null";
        // Lambda parameters can come back as a constraint type that is not a
        // ResolvedWildcard but describes itself as "? super T" / "? extends T";
        // the bound is the declared type.
        String d = rt.describe();
        for (String p : new String[]{"? super ", "? extends "}) {
            if (d.startsWith(p)) d = d.substring(p.length());
        }
        int lt = d.indexOf('<');
        return lt > 0 ? d.substring(0, lt) : d;
    }

    static List<String> typeArgs(ResolvedType rt) {
        List<String> out = new ArrayList<>();
        if (rt != null && rt.isReferenceType()) {
            ResolvedReferenceType r = rt.asReferenceType();
            r.typeParametersValues().forEach(a -> {
                try { out.add(erasure(a)); } catch (Throwable e) { out.add(null); }
            });
        }
        return out;
    }

    // ------------------------------------------------------------- call sites

    static Map<String, Object> callRecord(MethodCallExpr mc, String file) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("owner", ownerName(mc));
        r.put("context", enclosingContext(mc));
        r.put("file", file);
        r.put("line", mc.getBegin().map(p -> p.line).orElse(-1));
        r.put("method", mc.getNameAsString());
        r.put("nargs", mc.getArguments().size());
        r.put("arg0", argSummary(mc.getArguments()));

        Optional<Expression> scope = mc.getScope();
        String scopeKind = scope.map(s -> s.getClass().getSimpleName()).orElse("implicit");
        r.put("scope_kind", scopeKind);
        r.put("scope_text", scope.map(s -> trunc(s.toString(), 120)).orElse(null));

        // Receiver: declared static type of the scope expression.
        String recv = null, recvErr = null;
        if (scope.isPresent() && !(scope.get() instanceof SuperExpr)) {
            try { recv = erasure(scope.get().calculateResolvedType()); }
            catch (Throwable e) { recvErr = err(e); }
        }
        r.put("receiver_type", recv);
        r.put("receiver_error", recvErr);

        // Declaration the call binds to statically.
        try {
            ResolvedMethodDeclaration d = mc.resolve();
            r.put("decl_type", d.declaringType().getQualifiedName());
            r.put("decl_signature", trunc(d.getQualifiedSignature(), 300));
            r.put("decl_static", d.isStatic());
            r.put("decl_abstract", d.isAbstract());
            r.put("decl_error", null);
        } catch (Throwable e) {
            r.put("decl_type", null);
            r.put("decl_signature", null);
            r.put("decl_static", null);
            r.put("decl_abstract", null);
            r.put("decl_error", err(e));
        }
        // When the scope is a field of the owner, record the field name so the
        // audit can join call sites with injection points (J2).
        r.put("scope_field", scope.flatMap(Main::fieldName).orElse(null));
        return r;
    }

    /** "this.x" or a bare name that resolves to a field. */
    static Optional<String> fieldName(Expression s) {
        try {
            if (s instanceof FieldAccessExpr fa && fa.getScope() instanceof ThisExpr) return Optional.of(fa.getNameAsString());
            if (s instanceof NameExpr ne) {
                var v = ne.resolve();
                if (v.isField()) return Optional.of(ne.getNameAsString());
            }
        } catch (Throwable ignored) { }
        return Optional.empty();
    }

    static Map<String, Object> argSummary(NodeList<Expression> args) {
        if (args.isEmpty()) return null;
        Expression a = args.get(0);
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("kind", a.getClass().getSimpleName());
        if (a instanceof StringLiteralExpr s) m.put("value", trunc(s.getValue(), 200));
        else if (a instanceof ClassExpr c) {
            m.put("value", c.getType().asString());
            try { m.put("resolved", erasure(c.getType().resolve())); } catch (Throwable e) { m.put("resolved", null); }
        }
        else m.put("text", trunc(a.toString(), 120));
        return m;
    }

    static Map<String, Object> creationRecord(ObjectCreationExpr oc, String file) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("owner", ownerName(oc));
        r.put("context", enclosingContext(oc));
        r.put("file", file);
        r.put("line", oc.getBegin().map(p -> p.line).orElse(-1));
        r.put("type_raw", oc.getType().getNameWithScope());
        r.put("anonymous_body", oc.getAnonymousClassBody().isPresent());
        try { r.put("type", erasure(oc.getType().resolve())); r.put("error", null); }
        catch (Throwable e) { r.put("type", null); r.put("error", err(e)); }
        return r;
    }

    static Map<String, Object> methodRefRecord(MethodReferenceExpr mr, String file) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("owner", ownerName(mr));
        r.put("file", file);
        r.put("line", mr.getBegin().map(p -> p.line).orElse(-1));
        r.put("text", trunc(mr.toString(), 160));
        try { r.put("decl_type", mr.resolve().declaringType().getQualifiedName()); r.put("error", null); }
        catch (Throwable e) { r.put("decl_type", null); r.put("error", err(e)); }
        return r;
    }

    /**
     * A name or field-access expression that resolves to a field. Returns null
     * for names that resolve to locals or parameters, for names that are a
     * package or type (the `X` in `X.FOO`), and for names that do not resolve.
     */
    static Map<String, Object> fieldRefRecord(Expression e, String file) {
        String declType;
        boolean isStatic;
        String name;
        try {
            com.github.javaparser.resolution.declarations.ResolvedValueDeclaration v =
                    e instanceof NameExpr ne ? ne.resolve() : ((FieldAccessExpr) e).resolve();
            if (!v.isField()) return null;
            var f = v.asField();
            declType = f.declaringType().getQualifiedName();
            isStatic = f.isStatic();
            name = f.getName();
        } catch (Throwable ex) {
            return null;
        }
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("kind", "field");
        r.put("owner", ownerName(e));
        r.put("file", file);
        r.put("line", e.getBegin().map(p -> p.line).orElse(-1));
        r.put("name", name);
        r.put("decl_type", declType);
        r.put("static", isStatic);
        return r;
    }

    static Map<String, Object> classLiteralRecord(ClassExpr ce, String file) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("kind", "class_literal");
        r.put("owner", ownerName(ce));
        r.put("file", file);
        r.put("line", ce.getBegin().map(p -> p.line).orElse(-1));
        r.put("name", ce.getType().asString());
        try { r.put("decl_type", erasure(ce.getType().resolve())); } catch (Throwable ex) { r.put("decl_type", null); }
        r.put("in_annotation", ce.findAncestor(AnnotationExpr.class).isPresent());
        return r;
    }

    // ---------------------------------------------------------------- helpers

    static String err(Throwable e) {
        String msg = e.getMessage() == null ? "" : e.getMessage().replace('\n', ' ');
        return e.getClass().getSimpleName() + ": " + trunc(msg, 200);
    }

    static String trunc(String s, int n) {
        return s == null || s.length() <= n ? s : s.substring(0, n) + "...";
    }

    static BufferedWriter w(Path p) throws IOException {
        return Files.newBufferedWriter(p, StandardCharsets.UTF_8);
    }
}
