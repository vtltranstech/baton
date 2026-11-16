import com.github.javaparser.JavaParser;
import com.github.javaparser.JavaToken;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.ImportDeclaration;
import com.github.javaparser.ast.Modifier;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.NodeList;
import com.github.javaparser.ast.body.*;
import com.github.javaparser.ast.expr.*;
import com.github.javaparser.ast.nodeTypes.NodeWithModifiers;
import com.github.javaparser.ast.stmt.LocalClassDeclarationStmt;
import com.github.javaparser.ast.stmt.LocalRecordDeclarationStmt;
import com.github.javaparser.ast.type.ArrayType;
import com.github.javaparser.ast.type.ClassOrInterfaceType;
import com.github.javaparser.ast.type.Type;
import com.github.javaparser.ast.type.WildcardType;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Reads file paths on stdin, one per line; writes one JSON object per file, in the shape of extract/model.py. */
public class AstDump {
    private static final String OTHER = "{\"k\":\"other\"}";

    public static void main(String[] args) throws Exception {
        ParserConfiguration config =
                new ParserConfiguration().setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_26);
        PrintStream out = new PrintStream(System.out, false, StandardCharsets.UTF_8);
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        for (String line = in.readLine(); line != null; line = in.readLine()) {
            String result;
            try {
                ParseResult<CompilationUnit> parsed =
                        new JavaParser(config).parse(Files.readString(Path.of(line), StandardCharsets.UTF_8));
                if (parsed.isSuccessful() && parsed.getResult().isPresent()) {
                    result = new AstDump().file(parsed.getResult().get());
                } else {
                    String reason = parsed.getProblems().isEmpty() ? "no result" : parsed.getProblem(0).getMessage();
                    result = "{\"ok\":false,\"reason\":" + str(reason.split("\n")[0]) + "}";
                }
            } catch (Exception | StackOverflowError e) {
                result = "{\"ok\":false,\"reason\":" + str(e.getClass().getSimpleName() + ": " + e.getMessage()) + "}";
            }
            out.println(result);
            out.flush();
        }
    }

    private String pkg = "";
    private final List<TypeOut> types = new ArrayList<>();

    private static final class MethodOut {
        final List<String> locals = new ArrayList<>();
        String head;
        String params;
        int index;
    }

    private static final class TypeOut {
        String name, fqcn, kind, annotations, extendsList = "[]", implementsList = "[]";
        int line, end, outer;
        final List<String> fields = new ArrayList<>();
        final List<MethodOut> methods = new ArrayList<>();
        final List<String> chains = new ArrayList<>();
    }

    private String file(CompilationUnit unit) {
        pkg = unit.getPackageDeclaration().map(p -> p.getNameAsString()).orElse("");
        List<String> imports = new ArrayList<>();
        List<String> statics = new ArrayList<>();
        for (ImportDeclaration imp : unit.getImports()) {
            if (imp.isModule()) {
                continue;
            }
            String name = imp.getNameAsString() + (imp.isAsterisk() ? ".*" : "");
            (imp.isStatic() ? statics : imports).add(str(name));
        }
        for (TypeDeclaration<?> decl : unit.getTypes()) {
            type(decl, -1);
        }
        StringBuilder source = new StringBuilder();
        unit.getTokenRange().ifPresent(range -> {
            for (JavaToken token : range) {
                if (!token.getCategory().isWhitespaceOrComment()) {
                    source.append(token.getText()).append(' ');
                }
            }
        });
        List<String> typeJson = new ArrayList<>();
        for (TypeOut t : types) {
            List<String> methods = new ArrayList<>();
            for (MethodOut m : t.methods) {
                methods.add("{" + m.head + ",\"params\":" + m.params + ",\"locals\":" + arr(m.locals) + "}");
            }
            typeJson.add("{\"name\":" + str(t.name) + ",\"fqcn\":" + str(t.fqcn) + ",\"kind\":" + str(t.kind)
                    + ",\"line\":" + t.line + ",\"end\":" + t.end + ",\"outer\":" + t.outer + ",\"annotations\":" + t.annotations
                    + ",\"extends\":" + t.extendsList + ",\"implements\":" + t.implementsList
                    + ",\"fields\":" + arr(t.fields) + ",\"methods\":" + arr(methods)
                    + ",\"chains\":" + arr(t.chains) + "}");
        }
        return "{\"ok\":true,\"package\":" + str(pkg) + ",\"imports\":" + arr(imports)
                + ",\"static_imports\":" + arr(statics) + ",\"types\":" + arr(typeJson)
                + ",\"source\":" + str(source.toString().trim()) + "}";
    }

    // -- declarations ------------------------------------------------------------------------------------

    private void type(TypeDeclaration<?> node, int outer) {
        TypeOut out = new TypeOut();
        int index = types.size();
        types.add(out);
        out.name = node.getNameAsString();
        out.outer = outer;
        String prefix = outer >= 0 ? types.get(outer).fqcn : pkg;
        out.fqcn = prefix.isEmpty() ? out.name : prefix + "." + out.name;
        out.line = line(node.getName());
        out.end = end(node);
        out.annotations = annotations(node.getAnnotations());
        if (node instanceof ClassOrInterfaceDeclaration decl) {
            out.kind = decl.isInterface() ? "interface" : "class";
            out.extendsList = typeRefs(decl.getExtendedTypes());
            out.implementsList = typeRefs(decl.getImplementedTypes());
        } else if (node instanceof EnumDeclaration decl) {
            out.kind = "enum";
            out.implementsList = typeRefs(decl.getImplementedTypes());
            for (EnumConstantDeclaration constant : decl.getEntries()) {
                for (Expression arg : constant.getArguments()) {
                    walk(arg, index, null);
                }
                for (BodyDeclaration<?> member : constant.getClassBody()) {
                    member(member, index);
                }
            }
        } else if (node instanceof RecordDeclaration decl) {
            out.kind = "record";
            out.implementsList = typeRefs(decl.getImplementedTypes());
            for (Parameter component : decl.getParameters()) {
                out.fields.add(var(component.getNameAsString(), typeRef(component.getType()), line(component),
                        annotations(component.getAnnotations()), false, null));
            }
        } else {
            out.kind = "annotation";
        }
        for (BodyDeclaration<?> member : node.getMembers()) {
            member(member, index);
        }
    }

    private void member(BodyDeclaration<?> node, int owner) {
        TypeOut out = types.get(owner);
        if (node instanceof TypeDeclaration<?> nested) {
            type(nested, owner);
        } else if (node instanceof FieldDeclaration field) {
            boolean isFinal = field.hasModifier(Modifier.Keyword.FINAL)
                    || out.kind.equals("interface") || out.kind.equals("annotation");
            for (VariableDeclarator declarator : field.getVariables()) {
                String init = null;
                if (declarator.getInitializer().isPresent()) {
                    init = expr(declarator.getInitializer().get());
                    walk(declarator.getInitializer().get(), owner, null);
                }
                out.fields.add(var(declarator.getNameAsString(), typeRef(declarator.getType()), line(field),
                        annotations(field.getAnnotations()), isFinal, init));
            }
        } else if (node instanceof MethodDeclaration m) {
            MethodOut method = method(m.getNameAsString(), m, m.getAnnotations(), m.getParameters(), out);
            m.getBody().ifPresent(body -> walk(body, owner, method));
        } else if (node instanceof ConstructorDeclaration c) {
            walk(c.getBody(), owner, method(c.getNameAsString(), c, c.getAnnotations(), c.getParameters(), out));
        } else if (node instanceof CompactConstructorDeclaration c) {
            walk(c.getBody(), owner, method(c.getNameAsString(), c, c.getAnnotations(), new NodeList<>(), out));
        } else if (node instanceof InitializerDeclaration init) {
            walk(init.getBody(), owner, null);
        }
    }

    private MethodOut method(String name, Node at, NodeList<AnnotationExpr> anns, NodeList<Parameter> params, TypeOut out) {
        MethodOut method = new MethodOut();
        method.index = out.methods.size();
        String returns = at instanceof MethodDeclaration m ? simpleType(m.getType()) : "";
        String visibility = at instanceof NodeWithModifiers<?> owner ? visibility(owner, out.kind) : "";
        method.head = "\"name\":" + str(name) + ",\"line\":" + line(at) + ",\"end\":" + end(at)
                + ",\"ret\":" + str(returns) + ",\"vis\":" + str(visibility) + ",\"annotations\":" + annotations(anns);
        List<String> rendered = new ArrayList<>();
        for (Parameter p : params) {
            rendered.add(var(p.getNameAsString(), typeRef(p.getType()), line(p), annotations(p.getAnnotations()),
                    p.hasModifier(Modifier.Keyword.FINAL), null));
        }
        method.params = arr(rendered);
        out.methods.add(method);
        return method;
    }

    private static String var(String name, String type, int line, String annotations, boolean isFinal, String init) {
        return "{\"name\":" + str(name) + ",\"type\":" + type + ",\"line\":" + line + ",\"annotations\":" + annotations
                + ",\"final\":" + isFinal + ",\"init\":" + (init == null ? "null" : init) + "}";
    }

    private static String typeRefs(NodeList<ClassOrInterfaceType> refs) {
        List<String> out = new ArrayList<>();
        for (ClassOrInterfaceType ref : refs) {
            out.add(typeRef(ref));
        }
        return arr(out);
    }

    private static String typeRef(Type node) {
        Type type = node;
        while (type instanceof ArrayType array) {
            type = array.getComponentType();
        }
        if (!(type instanceof ClassOrInterfaceType ref)) {
            return "{\"name\":" + str(type.asString()) + ",\"args\":[]}";
        }
        List<String> args = new ArrayList<>();
        ref.getTypeArguments().ifPresent(list -> {
            for (Type arg : list) {
                args.add(str(simpleName(arg)));
            }
        });
        return "{\"name\":" + str(ref.getNameAsString()) + ",\"args\":" + arr(args) + "}";
    }

    private static String simpleName(Type type) {
        if (type instanceof WildcardType wildcard) {
            return wildcard.getExtendedType().map(AstDump::simpleName)
                    .or(() -> wildcard.getSuperType().map(AstDump::simpleName)).orElse("?");
        }
        if (type instanceof ArrayType array) {
            return simpleName(array.getComponentType());
        }
        return type instanceof ClassOrInterfaceType ref ? ref.getNameAsString() : type.asString();
    }

    private String annotations(NodeList<AnnotationExpr> nodes) {
        List<String> out = new ArrayList<>();
        for (AnnotationExpr node : nodes) {
            List<String> args = new ArrayList<>();
            if (node instanceof NormalAnnotationExpr normal) {
                for (MemberValuePair pair : normal.getPairs()) {
                    args.add(str(pair.getNameAsString()) + ":" + expr(pair.getValue()));
                }
            } else if (node instanceof SingleMemberAnnotationExpr single) {
                args.add("\"value\":" + expr(single.getMemberValue()));
            }
            out.add("{\"name\":" + str(node.getName().getIdentifier()) + ",\"line\":" + line(node)
                    + ",\"args\":{" + String.join(",", args) + "}}");
        }
        return arr(out);
    }

    // -- expressions -------------------------------------------------------------------------------------

    private String expr(Expression node) {
        if (node instanceof EnclosedExpr enclosed) {
            return expr(enclosed.getInner());
        }
        if (node instanceof StringLiteralExpr literal) {
            return "{\"k\":\"str\",\"v\":" + str(literal.asString()) + "}";
        }
        if (node instanceof TextBlockLiteralExpr literal) {
            return "{\"k\":\"str\",\"v\":" + str(literal.asString()) + "}";
        }
        String dotted = dotted(node);
        if (dotted != null) {
            return "{\"k\":\"name\",\"v\":" + str(dotted) + "}";
        }
        if (node instanceof ClassExpr cls && !cls.getType().isPrimitiveType()) {
            return "{\"k\":\"cls\",\"v\":" + str(simpleName(cls.getType())) + "}";
        }
        if (node instanceof BinaryExpr binary && binary.getOperator() == BinaryExpr.Operator.PLUS) {
            List<String> items = new ArrayList<>();
            flatten(binary, items);
            return "{\"k\":\"concat\",\"i\":" + arr(items) + "}";
        }
        if (node instanceof ArrayInitializerExpr array) {
            return "{\"k\":\"array\",\"i\":" + exprs(array.getValues()) + "}";
        }
        if (node instanceof ObjectCreationExpr creation && creation.getAnonymousClassBody().isEmpty()) {
            return "{\"k\":\"new\",\"v\":" + str(creation.getType().getNameAsString()) + ",\"i\":"
                    + exprs(creation.getArguments()) + "}";
        }
        return OTHER;
    }

    private String exprs(NodeList<Expression> nodes) {
        List<String> out = new ArrayList<>();
        for (Expression node : nodes) {
            out.add(expr(node));
        }
        return arr(out);
    }

    private void flatten(Expression node, List<String> items) {
        Expression inner = node;
        while (inner instanceof EnclosedExpr enclosed) {
            inner = enclosed.getInner();
        }
        if (inner instanceof BinaryExpr binary && binary.getOperator() == BinaryExpr.Operator.PLUS) {
            flatten(binary.getLeft(), items);
            flatten(binary.getRight(), items);
        } else {
            items.add(expr(inner));
        }
    }

    /** `a.b.c` and `this.a` as a dotted name; null for anything else. */
    private static String dotted(Expression node) {
        if (node instanceof NameExpr name) {
            return name.getNameAsString();
        }
        if (node instanceof FieldAccessExpr access) {
            if (access.getScope() instanceof ThisExpr) {
                return access.getNameAsString();
            }
            String scope = dotted(access.getScope());
            return scope == null ? null : scope + "." + access.getNameAsString();
        }
        return null;
    }

    // -- bodies ------------------------------------------------------------------------------------------

    private void walk(Node node, int owner, MethodOut method) {
        if (node instanceof AnnotationExpr) {
            return;
        }
        if (node instanceof LocalClassDeclarationStmt local) {
            type(local.getClassDeclaration(), owner);
        } else if (node instanceof LocalRecordDeclarationStmt local) {
            type(local.getRecordDeclaration(), owner);
        } else if (node instanceof VariableDeclarationExpr declaration) {
            for (VariableDeclarator declarator : declaration.getVariables()) {
                String init = null;
                if (declarator.getInitializer().isPresent()) {
                    init = expr(declarator.getInitializer().get());
                    walk(declarator.getInitializer().get(), owner, method);
                }
                if (method != null) {
                    method.locals.add(var(declarator.getNameAsString(), typeRef(declarator.getType()), 0,
                            annotations(declaration.getAnnotations()),
                            declaration.hasModifier(Modifier.Keyword.FINAL), init));
                }
            }
        } else if (node instanceof MethodCallExpr || node instanceof ObjectCreationExpr) {
            chain((Expression) node, owner, method);
        } else {
            for (Node child : node.getChildNodes()) {
                walk(child, owner, method);
            }
        }
    }

    private void chain(Expression start, int owner, MethodOut method) {
        List<MethodCallExpr> calls = new ArrayList<>();
        Expression base = start;
        while (true) {
            if (base instanceof MethodCallExpr call) {
                calls.add(call);
                if (call.getScope().isEmpty()) {
                    base = null;
                    break;
                }
                base = call.getScope().get();
            } else if (base instanceof FieldAccessExpr access && dotted(access) == null) {
                base = access.getScope();
            } else if (base instanceof ArrayAccessExpr array) {
                walk(array.getIndex(), owner, method);
                base = array.getName();
            } else if (base instanceof EnclosedExpr enclosed && calls.size() > 0) {
                base = enclosed.getInner();
            } else {
                break;
            }
        }
        Collections.reverse(calls);
        String root = "";
        String created = "null";
        int newLine = 0;
        String dotted = base == null ? null : dotted(base);
        boolean dropFirst = false;
        if (dotted != null) {
            root = dotted;
        } else if (base instanceof ObjectCreationExpr creation) {
            for (Expression arg : creation.getArguments()) {
                walk(arg, owner, method);
            }
            creation.getScope().ifPresent(scope -> walk(scope, owner, method));
            created = "{\"k\":\"new\",\"v\":" + str(creation.getType().getNameAsString()) + ",\"i\":"
                    + exprs(creation.getArguments()) + "}";
            newLine = line(creation);
            creation.getAnonymousClassBody().ifPresent(body -> body.forEach(member -> member(member, owner)));
        } else if (base instanceof SuperExpr) {
            dropFirst = true;
        } else if (base != null && !(base instanceof ThisExpr)) {
            walk(base, owner, method);
        }
        List<String> rendered = new ArrayList<>();
        for (int i = 0; i < calls.size(); i++) {
            MethodCallExpr call = calls.get(i);
            for (Expression arg : call.getArguments()) {
                walk(arg, owner, method);
            }
            if (!(dropFirst && i == 0)) {
                rendered.add("{\"name\":" + str(call.getNameAsString()) + ",\"args\":" + exprs(call.getArguments())
                        + ",\"line\":" + line(call.getName()) + "}");
            }
        }
        if (!rendered.isEmpty() || !created.equals("null")) {
            types.get(owner).chains.add("{\"root\":" + str(root) + ",\"calls\":" + arr(rendered) + ",\"new\":" + created
                    + ",\"new_line\":" + newLine + ",\"method\":" + (method == null ? -1 : method.index) + "}");
        }
    }

    // -- output ------------------------------------------------------------------------------------------

    private static int line(Node node) {
        return node.getBegin().map(p -> p.line).orElse(0);
    }

    private static int end(Node node) {
        return node.getEnd().map(p -> p.line).orElse(0);
    }

    /** The declared type as written in short form: `Optional<FeeScheduleDoc>`, `List<String>[]`, `void`. */
    private static String simpleType(Type type) {
        if (type instanceof ArrayType array) {
            return simpleType(array.getComponentType()) + "[]";
        }
        if (type instanceof ClassOrInterfaceType ref) {
            StringBuilder out = new StringBuilder(ref.getNameAsString());
            ref.getTypeArguments().ifPresent(list -> {
                List<String> args = new ArrayList<>();
                for (Type arg : list) {
                    args.add(simpleType(arg));
                }
                out.append('<').append(String.join(", ", args)).append('>');
            });
            return out.toString();
        }
        if (type instanceof WildcardType wildcard) {
            return wildcard.getExtendedType().map(t -> "? extends " + simpleType(t)).orElse("?");
        }
        return type.asString();
    }

    private static String visibility(NodeWithModifiers<?> node, String kind) {
        if (node.hasModifier(Modifier.Keyword.PUBLIC)) {
            return "public";
        }
        if (node.hasModifier(Modifier.Keyword.PROTECTED)) {
            return "protected";
        }
        if (node.hasModifier(Modifier.Keyword.PRIVATE)) {
            return "private";
        }
        return kind.equals("interface") || kind.equals("annotation") ? "public" : "package";
    }

    private static String arr(List<String> items) {
        return "[" + String.join(",", items) + "]";
    }

    private static String str(String text) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c == '"' || c == '\\') {
                out.append('\\').append(c);
            } else if (c < 0x20 || c == 0x2028 || c == 0x2029) {
                out.append(String.format("\\u%04x", (int) c));
            } else {
                out.append(c);
            }
        }
        return out.append('"').toString();
    }
}
