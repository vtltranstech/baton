"""All back-ends give the same model on the same Java, and the AST back-ends read the newest syntax."""

import pytest
from baton.extract import javaparser_backend, parser, regex_backend, treesitter_backend
from baton.extract.model import Expr, ParseFailure
from baton.extract.parser import parse_java

SOURCE = """package com.x;

import static com.x.Topics.FEE;
import com.x.other.Thing;

/** @KafkaListener(topics = "in-a-comment") */
@Service("svc")
public class Sample<T> extends Base<T, String> implements Port, Other<Thing> {
    private static final String PREFIX = "fee." + "events";
    private final KafkaTemplate<String, Thing> kafka;
    private String a = "x", b;
    // kafka.send("commented.out");

    public Sample(KafkaTemplate<String, Thing> kafka, @Value("${a.b:c}") final String url) {
        this.kafka = kafka;
    }

    @KafkaListener(topics = {"t1", PREFIX}, groupId = "g")
    public void on(Thing thing) {
        String local = "not a call: kafka.send(\\"inside.a.string\\")";
        final String topic = "t.local";
        kafka
            .send(topic, thing);
        this.kafka.send(FEE, thing).get();
        new Builder<Thing>()
            .name("n")
            .<Thing, Thing>chunk(3)
            .resource(new FileSystemResource("/f"))
            .build();
        Runnable r = () -> { kafka.send("in.lambda", null); };
        rest.get().uri("/a/" + local, Thing.class).retrieve();
    }

    interface Nested { String K = "v"; }

    enum Mode { A("x"), B; Mode() {} Mode(String s) { helper.run(s); } }
}
"""


def _need_jdk(monkeypatch=None):
    if not javaparser_backend.available():
        pytest.skip("no JDK on the PATH")
    if monkeypatch is not None:
        monkeypatch.setenv("BATON_JAVA_PARSER", "javaparser")


def _need_treesitter():
    if not treesitter_backend.available():
        pytest.skip("the baton[treesitter] extra is not installed")


def _shape(parsed):
    def expr(e):
        return (e.kind, e.value, tuple(expr(i) for i in e.items))

    def ann(a):
        return (a.name, a.line, sorted((k, expr(v)) for k, v in a.args.items()))

    out = {"package": parsed.package, "imports": parsed.imports, "static": parsed.static_imports, "types": []}
    for t in parsed.types:
        out["types"].append(
            {
                "name": t.name,
                "fqcn": t.fqcn,
                "kind": t.kind,
                "line": t.line,
                "ann": [ann(a) for a in t.annotations],
                "extends": [(r.name, r.args) for r in t.extends],
                "implements": [(r.name, r.args) for r in t.implements],
                "fields": [
                    (
                        v.name,
                        v.type.name,
                        v.type.args,
                        v.final,
                        expr(v.init) if v.init else None,
                        [ann(a) for a in v.annotations],
                    )
                    for v in t.fields
                ],
                "methods": [
                    (
                        m.name,
                        [ann(a) for a in m.annotations],
                        [(p.name, p.type.name, p.final, [ann(a) for a in p.annotations]) for p in m.params],
                        sorted((v.name, v.type.name, v.final) for v in m.locals),
                    )
                    for m in t.methods
                ],
                "chains": sorted(
                    (
                        (
                            c.root,
                            expr(c.new) if c.new else None,
                            c.new_line,
                            tuple((k.name, k.line, tuple(expr(a) for a in k.args)) for k in c.calls),
                            c.method.name if c.method else None,
                        )
                        for c in t.chains
                    ),
                    key=repr,
                ),
            }
        )
    return out


def test_backends_agree_on_a_synthetic_file():
    _need_jdk()
    assert _shape(javaparser_backend.parse(SOURCE, "S.java")) == _shape(regex_backend.parse(SOURCE, "S.java"))


def test_backends_agree_on_every_fixture_file(root):
    _need_jdk()
    compared = 0
    for path in sorted((root / "fixtures").rglob("*.java")):
        text = path.read_text()
        try:
            ast = javaparser_backend.parse(text, "F.java")
        except ParseFailure:
            continue
        assert _shape(ast) == _shape(regex_backend.parse(text, "F.java")), path
        compared += 1
    assert compared >= 15


@pytest.mark.parametrize(
    "snippet",
    [
        "public record R(@Id String id, java.util.List<String> xs) { }",
        "public sealed interface S permits A, B { }",
        'public non-sealed class N extends S2 { String t = """\n   hello\n   """; }',
    ],
)
def test_regex_reads_records_and_sealed_types(snippet):
    parsed = regex_backend.parse("package p;\n" + snippet, "X.java")
    assert parsed.types and parsed.package == "p"


def test_nested_record_is_a_type_not_a_method(monkeypatch):
    _need_jdk(monkeypatch)
    source = "package p;\nclass A {\n  public record R(String a) { }\n}\n"
    parsed = parse_java(source, "A.java", True)
    assert parsed.backend == "javaparser" and not parsed.fallback_reason
    assert [t.name for t in parsed.types] == ["A", "R"]
    assert [f.name for f in parsed.types[1].fields] == ["a"]


@pytest.mark.parametrize(
    "version, source",
    [
        (
            17,
            "sealed interface S permits A { record P(int a) {} }\n"
            'final class A implements S { String t = """\n x\n """; }',
        ),
        (
            21,
            "class U { int a(Object s) { return switch (s) "
            "{ case Integer i when i > 0 -> i; default -> 0; }; } }",
        ),
        (22, "class V { int g() { try { return 1; } catch (Exception _) { return 0; } } }"),
        (25, "import module java.base;\nclass W { W(int x) {} W() { int y = 1; this(y); } }"),
    ],
)
def test_javaparser_reads_modern_java(version, source, monkeypatch):
    _need_jdk(monkeypatch)
    parsed = parse_java(source, f"J{version}.java", True)
    assert parsed.backend == "javaparser" and parsed.types


def test_a_file_javaparser_refuses_falls_back_and_says_why(monkeypatch):
    _need_jdk(monkeypatch)
    parsed = parse_java("package p;\nclass R { int x = ; }\n", "R.java", True)
    assert parsed.backend == "regex" and parsed.fallback_reason


@pytest.mark.parametrize(
    "broken",
    [
        "class A {",
        "class A { void f( { } }",
        'class A { String s = "x; }',
        "/* never closed\nclass A { }",
        "this is not java at all",
    ],
)
def test_malformed_files_are_refused_by_both(broken):
    with pytest.raises(ParseFailure):
        parse_java(broken, "B.java", False)


def test_string_and_comment_content_is_not_code():
    parsed = regex_backend.parse(SOURCE, "S.java")
    names = [(c.root, k.args) for t in parsed.types for c in t.chains for k in c.calls if k.name == "send"]
    values = [a.value for _, args in names for a in args if a.kind == "str"]
    assert "commented.out" not in values and "inside.a.string" not in values
    assert Expr("str", "in.lambda") in [a for _, args in names for a in args]


# -- tree-sitter (contracts/models-and-activation.md section 1) ----------------------------------------------

HARD = """package p;
@SuppressWarnings({"a", "b"}) @org.junit.Ignore
abstract class B<T extends Comparable<? super T>> extends Base<java.util.List<? extends T>> implements Ser {
  protected static final String[] ARR = {"x", P.Q, B.class.getName()};
  private Map<String, List<int[]>> m;
  char c = 'x'; long[] ls = new long[]{1, 2};
  String t = \"\"\"
      hello \\\\
      "world"
        end
      \"\"\";
  B(String... names) { this(names.length); }
  B(int n) { super(); Outer.this.go(); super.go().then(); }
  public <R> Optional<? extends R> find(final List<? super R> xs, Function<T, R>[] fs) throws Exception {
    for (final String s : xs.stream().map(x -> x.call("in")).toList()) { use(s); }
    try (var in = open("f"); java.io.Reader r = other()) { in.read(); }
    catch (IOException e) { log.warn("e", e); }
    executor.submit(new Callable<String>() { @Override public String call() { return "c"; } });
    int v = switch (o) { case Integer i when i > 0 -> i; case String s -> s.length(); default -> 0; };
    if (o instanceof Point(int x, int y)) { pt(x, y); }
    record Local(String a) {}
    class LocalClass { void z() { q.z(); } }
    foo().bar.baz(1);
    this.field.sub.call(a.b.c, this.d, "s" + 1);
    new Outer().new Inner().go();
    return Optional.<R>empty();
  }
  static { init.run(); }
  enum E implements I { A("a") { @Override void f() { g.h(); } }, B, ; void f() {} E() {} }
  @interface Ann { String value() default "x"; int N = 3; }
  java.util.Map.Entry<String, Integer> entry() { return null; }
}
"""


def _extra(parsed):
    """What _shape leaves out: method ends, returns, visibility, type ends, field lines, source tokens."""
    methods = [(m.name, m.line, m.end, m.returns, m.visibility) for t in parsed.types for m in t.methods]
    types = [(t.name, t.end, [f.line for f in t.fields]) for t in parsed.types]
    return methods, types, parsed.source.split()


@pytest.mark.parametrize("source", [SOURCE, HARD], ids=["synthetic", "hard"])
def test_treesitter_and_javaparser_build_the_same_model(source):
    _need_jdk()
    _need_treesitter()
    ast, tree = javaparser_backend.parse(source, "S.java"), treesitter_backend.parse(source, "S.java")
    assert _shape(tree) == _shape(ast)
    assert _extra(tree) == _extra(ast)
    assert tree.backend == "treesitter"


def test_treesitter_and_javaparser_agree_on_every_fixture_file(root):
    _need_jdk()
    _need_treesitter()
    compared = 0
    for path in sorted((root / "fixtures").rglob("*.java")):
        text = path.read_text()
        try:
            ast = javaparser_backend.parse(text, "F.java")
        except ParseFailure:
            continue
        tree = treesitter_backend.parse(text, "F.java")
        assert (_shape(tree), _extra(tree)) == (_shape(ast), _extra(ast)), path
        compared += 1
    assert compared >= 15


def test_treesitter_is_the_first_choice_and_reads_java_21():
    _need_treesitter()
    source = (
        "package p;\nsealed interface S permits A { record P(int a) {} }\n"
        "final class A implements S { int a(Object s) { return switch (s) "
        "{ case Integer i when i > 0 -> i; default -> 0; }; } }\n"
    )
    parsed = parse_java(source, "S.java")
    assert parsed.backend == "treesitter" and not parsed.fallback_reason
    assert [(t.name, t.kind) for t in parsed.types] == [("S", "interface"), ("P", "record"), ("A", "class")]
    assert [r.name for r in parsed.types[2].implements] == ["S"]


def test_a_file_treesitter_refuses_goes_to_the_next_backend_and_says_why():
    _need_treesitter()
    parsed = parse_java("package p;\nclass R { int x = ; }\n", "R.java")
    assert parsed.backend in ("javaparser", "regex")
    assert parsed.fallback_reason.startswith("treesitter: syntax error at line 2")


def test_without_the_extra_the_order_is_javaparser_then_regex(monkeypatch):
    monkeypatch.setattr(parser, "_AVAILABLE", {"treesitter": lambda: False, "javaparser": lambda: True})
    assert parser.backends() == ["javaparser", "regex"]
    monkeypatch.setenv("BATON_JAVA_PARSER", "regex")
    assert parser.backends() == ["regex"] and not parser.ast_usable()


def test_the_environment_picks_the_first_backend(monkeypatch):
    monkeypatch.setattr(parser, "_AVAILABLE", {"treesitter": lambda: True, "javaparser": lambda: True})
    assert parser.backends() == ["treesitter", "javaparser", "regex"]
    monkeypatch.setenv("BATON_JAVA_PARSER", "javaparser")
    assert parser.backends() == ["javaparser", "regex"]
    assert parser.backends(use_ast=False) == ["regex"]


def test_a_text_block_line_continuation_joins_the_lines():
    parsed = regex_backend.parse('class T { String t = """\n  a \\\n  b\n  """; }', "T.java")
    assert parsed.types[0].fields[0].init == Expr("str", "a b\n")
