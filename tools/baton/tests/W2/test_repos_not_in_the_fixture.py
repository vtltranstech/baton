"""What the fixture does not cover: malformed input, constants, placeholders, profiles, git, repeatability."""

import io
import json
import os
import re
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import jsonschema
import pytest
from baton import cli, miniyaml
from baton.extract import javaparser_backend, yamlio
from baton.extract.pipeline import GENERATED_FILES
from conftest import ROOT, git, make_java_repo, schema, write_project

TEMPLATE_PUBLISHER = """package com.x;
import org.springframework.kafka.core.KafkaTemplate;
{extra_imports}
public class Pub {{
    {members}
    private final KafkaTemplate<String, String> kafka;
    public Pub(KafkaTemplate<String, String> kafka) {{ this.kafka = kafka; }}
    public void go(String param) {{
        kafka.send({target}, "v");
    }}
}}
"""


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def setup_repo(tmp_path, files, pom=None, name="svc"):
    make_java_repo(tmp_path, name, files, pom)
    central = tmp_path / "central"
    write_project(central, [(name, f"../{name}")])
    return central


def extract(central):
    code, out, err = run_cli("extract", "--central", str(central), "--json")
    assert code == 0, err
    document = json.loads(out)
    jsonschema.validate(document, schema("dependencies"))
    return document["repos"][0]


def questions(central):
    code, out, err = run_cli("onboard", "--allow-sample", "--central", str(central))
    assert code == 0, err
    return json.loads(out)


def targets(entry, kind=None):
    return sorted(e["to"] for e in entry["edges"] if kind in (None, e["kind"]))


def publisher(target, members="", extra_imports=""):
    return {
        "src/main/java/com/x/Pub.java": TEMPLATE_PUBLISHER.format(
            target=target, members=members, extra_imports=extra_imports
        )
    }


# -- malformed files -----------------------------------------------------------------------------------------


def test_malformed_java_is_reported_and_the_rest_still_extracted(tmp_path, backend):
    files = publisher('"good.topic"')
    files["src/main/java/com/x/Broken.java"] = (
        'package com.x;\n@KafkaListener(topics = "x")\npublic class Broken {'
    )
    central = setup_repo(tmp_path, files)
    entry = extract(central)
    assert targets(entry) == ["topic:good.topic"]
    ids = [q["id"] for q in questions(central)["questions"]]
    assert "parse-failure:svc:src/main/java/com/x/Broken.java" in ids


def test_non_utf8_java_is_reported_not_fatal(tmp_path, backend):
    central = setup_repo(tmp_path, publisher('"good.topic"'))
    (tmp_path / "svc/src/main/java/com/x/Latin.java").write_bytes(
        b'package com.x;\nclass L { String a = "\xe9"; }\n'
    )
    assert targets(extract(central)) == ["topic:good.topic"]
    assert "parse-failure:svc:src/main/java/com/x/Latin.java" in [
        q["id"] for q in questions(central)["questions"]
    ]


def test_malformed_pom_keeps_what_is_known_and_asks(tmp_path, backend):
    central = setup_repo(tmp_path, publisher('"t"'), pom="<project><properties><java.version>21</java")
    code, out, _ = run_cli("extract-stack", "--central", str(central), "--json")
    assert code == 0
    row = json.loads(out)["repos"][0]
    jsonschema.validate(json.loads(out), schema("stack-detected"))
    assert row["build"] == "maven" and row["java"] == "unknown" and row["springBoot"] == "unknown"
    assert any(q["id"].startswith("build-file:svc:pom.xml") for q in questions(central)["questions"])


def test_malformed_yml_leaves_placeholders_open_even_with_a_default(tmp_path, backend):
    files = publisher('"${topic.name:fallback}"')
    files["src/main/resources/application.yml"] = "a:\n  b: 1\n c: broken indent\n  : : :\n"
    central = setup_repo(tmp_path, files)
    entry = extract(central)
    assert entry["unresolved"] == ["topic:${topic.name:fallback}"]
    ids = [q["id"] for q in questions(central)["questions"]]
    assert "config-unreadable:svc:src/main/resources/application.yml" in ids


# -- constants ----------------------------------------------------------------------------------------------


def test_unresolvable_constant_stays_literal_and_is_listed(tmp_path, backend):
    entry = extract(setup_repo(tmp_path, publisher("Elsewhere.TOPIC")))
    assert entry["unresolved"] == ["topic:<Pub.Elsewhere.TOPIC>"] == targets(entry)


def test_method_parameter_and_call_are_not_guessed(tmp_path, backend):
    assert extract(setup_repo(tmp_path, publisher("param")))["unresolved"] == ["topic:<Pub.param>"]
    other = tmp_path / "second"
    assert extract(setup_repo(other, publisher("name()")))["unresolved"] == ["topic:<Pub:9>"]


@pytest.mark.parametrize(
    ("target", "members", "imports", "extra"),
    [
        ("TOPIC", 'private static final String TOPIC = "res.olved";', "", {}),
        ("A + B", 'static final String A = "res"; static final String B = ".olved";', "", {}),
        ("TOPIC", 'static final String TOPIC = BASE + ".olved"; static final String BASE = "res";', "", {}),
        (
            "Topics.FEE",
            "",
            "",
            {"Topics": 'package com.x;\nclass Topics { static final String FEE = "res.olved"; }'},
        ),
        (
            "Names.FEE",
            "",
            "import com.y.Names;",
            {"../y/Names": 'package com.y;\npublic interface Names { String FEE = "res.olved"; }'},
        ),
        (
            "FEE",
            "",
            "import static com.y.Names.FEE;",
            {"../y/Names": 'package com.y;\npublic interface Names { String FEE = "res.olved"; }'},
        ),
        (
            "FEE",
            "",
            "import static com.y.Names.*;",
            {
                "../y/Names": "package com.y;\npublic final class Names { public static final String FEE = "
                '"res.olved"; }'
            },
        ),
        ("TOPIC", 'static final String TOPIC = "${the.topic}";', "", {"cfg": "the:\n  topic: res.olved\n"}),
        ("Pub.TOPIC", 'static final String TOPIC = "res.olved";', "", {}),
    ],
)
def test_constants_resolve_through_static_final(tmp_path, backend, target, members, imports, extra):
    files = publisher(target, members, imports)
    for key, text in extra.items():
        rel = "src/main/resources/application.yml" if key == "cfg" else f"src/main/java/com/x/{key}.java"
        files[rel] = text
    entry = extract(setup_repo(tmp_path, files))
    assert entry["unresolved"] == [] and targets(entry) == ["topic:res.olved"]


def test_non_final_field_is_not_treated_as_a_constant(tmp_path, backend):
    entry = extract(setup_repo(tmp_path, publisher("topic", 'private String topic = "maybe";')))
    assert entry["unresolved"] == ["topic:<Pub.topic>"]


def test_constant_cycle_terminates_unresolved(tmp_path, backend):
    entry = extract(
        setup_repo(tmp_path, publisher("A", "static final String A = B; static final String B = A;"))
    )
    assert len(entry["unresolved"]) == 1


def test_comments_and_strings_produce_nothing(tmp_path, backend):
    source = """package com.x;
    // @Document(collection = "commented")
    /* kafka.send("commented"); java.math.BigDecimal */
    public class Quiet {
        private final KafkaTemplate<String, String> kafka = null;
        String note = "kafka.send(\\"in.string\\") BigDecimal";
    }
    """
    central = setup_repo(tmp_path, {"src/main/java/com/x/Quiet.java": source})
    assert extract(central)["edges"] == []
    assert miniyaml.load_file(str(central / "profile/risk-zones.yaml"))["zones"] == []


def test_text_block_target_is_not_a_target(tmp_path, backend):
    entry = extract(setup_repo(tmp_path, publisher('"""\n   multi\n   line\n   """')))
    assert len(entry["unresolved"]) == 1 and "multi" not in entry["unresolved"][0]


# -- placeholders and profiles ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "yml", "expected", "open_"),
    [
        ('"${x:dflt}"', "", "topic:dflt", False),
        ('"${x:dflt}"', "x: from-yml\n", "topic:from-yml", False),
        ('"${a:${b:deep}}"', "", "topic:deep", False),
        ('"${a:${b:deep}}"', "b: mid\n", "topic:mid", False),
        ('"${x:}"', "", "topic:<Pub:9>", True),
        ('"${x}"', "", "topic:${x}", True),
        ('"${x}"', "x: ${ENV_ONLY}\n", "topic:${x}", True),
        ('"${x}"', "x: ${ENV_ONLY:env-default}\n", "topic:env-default", False),
        ('"pre.${x}.post"', "x: mid\n", "topic:pre.mid.post", False),
        ('"${a}"', "a: ${b}\nb: ${a}\n", "topic:${a}", True),
        ('"${fee.eventsTopic}"', "fee:\n  events-topic: relaxed\n", "topic:relaxed", False),
        ('"#{beanExpr}"', "", "topic:#{beanExpr}", True),
    ],
)
def test_placeholders(tmp_path, backend, target, yml, expected, open_):
    files = publisher(target)
    if yml:
        files["src/main/resources/application.yml"] = yml
    entry = extract(setup_repo(tmp_path, files))
    assert targets(entry) == [expected]
    assert bool(entry["unresolved"]) is open_


def test_properties_file(tmp_path, backend):
    files = publisher('"${x}"')
    files["src/main/resources/application.properties"] = "# comment\nx=from-props\n"
    assert targets(extract(setup_repo(tmp_path, files))) == ["topic:from-props"]


def test_profile_override_uses_base_and_asks(tmp_path, backend):
    files = publisher('"${x}"')
    files["src/main/resources/application.yml"] = "x: base-value\n"
    files["src/main/resources/application-prod.yml"] = "x: prod-value\n"
    central = setup_repo(tmp_path, files)
    assert targets(extract(central)) == ["topic:base-value"]
    match = [q for q in questions(central)["questions"] if q["id"] == "profile-override:svc:x"]
    assert match[0]["values"] == {"base": "base-value", "prod": "prod-value"}


def test_value_only_in_a_profile_stays_open_and_is_shown(tmp_path, backend):
    files = publisher('"${x}"')
    files["src/main/resources/application-prod.yml"] = "x: prod-value\n"
    central = setup_repo(tmp_path, files)
    entry = extract(central)
    assert entry["unresolved"] == ["topic:${x}"]
    match = [q for q in questions(central)["questions"] if q["id"] == "unresolved:svc:topic:${x}"]
    assert match[0]["onlyInProfiles"] == {"x": {"prod": "prod-value"}}


def test_multi_document_yml_profile_section(tmp_path, backend):
    files = publisher('"${x}"')
    files["src/main/resources/application.yml"] = (
        "x: base\n---\nspring:\n  config:\n    activate:\n      on-profile: dev\nx: dev-value\n"
    )
    central = setup_repo(tmp_path, files)
    assert targets(extract(central)) == ["topic:base"]
    assert "profile-override:svc:x" in [q["id"] for q in questions(central)["questions"]]


# -- REST, Mongo, messaging shapes the fixture lacks -----------------------------------------------


def _java(body, name="C"):
    return {f"src/main/java/com/x/{name}.java": f"package com.x;\n{body}\n"}


def test_multi_line_chain_reports_the_uri_line(tmp_path, backend):
    body = """public class C {
    private final WebClient web = WebClient.builder().baseUrl("https://a.test/").build();
    void go() {
        web
            .post()
            .uri("/p")
            .retrieve();
    }
}"""
    edge = extract(setup_repo(tmp_path, _java(body)))["edges"][0]
    assert edge["to"] == "endpoint:POST https://a.test/p" and edge["provenance"]["line"] == 7


@pytest.mark.parametrize(
    ("body", "expected", "open_"),
    [
        (
            'class C { RestClient r; void g() { r.get().uri("/p").retrieve(); } }',
            "endpoint:<C.base-url>/p",
            True,
        ),
        (
            'class C { RestClient r = RestClient.builder().baseUrl("http://a").build();'
            ' RestClient s = RestClient.builder().baseUrl("http://b").build();'
            ' void g() { r.get().uri("/p").retrieve(); } }',
            "endpoint:<C.base-url>/p",
            True,
        ),
        (
            'class C { RestClient r; void g() { r.get().uri("https://abs.test/p").retrieve(); } }',
            "endpoint:GET https://abs.test/p",
            False,
        ),
        (
            'class C { RestClient r = RestClient.create("http://a"); void g(String u) { '
            "r.get().uri(u).retrieve(); } }",
            "endpoint:http://a/<C.u>",
            True,
        ),
        (
            'class C { RestTemplate t; void g() { t.getForObject("http://a/x", String.class); } }',
            "endpoint:GET http://a/x",
            False,
        ),
        (
            'class C { RestTemplate t; void g() { t.exchange("http://a/x", HttpMethod.PUT, null, '
            "String.class); } }",
            "endpoint:PUT http://a/x",
            False,
        ),
        (
            '@FeignClient(name = "n", url = "${f.url:http://f}") interface C { @GetMapping("/p") String '
            "g(); }",
            "endpoint:GET http://f/p",
            False,
        ),
        (
            '@FeignClient(name = "n") interface C { @GetMapping("/p") String g(); }',
            "endpoint:<C.url>/p",
            True,
        ),
    ],
)
def test_outbound_rest_shapes(tmp_path, backend, body, expected, open_):
    entry = extract(setup_repo(tmp_path, _java(body)))
    assert targets(entry, "CALLS_ENDPOINT") == [expected]
    assert bool(entry["unresolved"]) is open_


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            '@RestController class C { @RequestMapping(value = "/a", method = RequestMethod.PUT) void g() '
            "{} }",
            ["endpoint:PUT /a"],
        ),
        ('@RestController class C { @RequestMapping(path = "/a") void g() {} }', ["endpoint:ANY /a"]),
        (
            '@RestController @RequestMapping({"/a", "/b"}) class C { @GetMapping("c") void g() {} }',
            ["endpoint:GET /a/c", "endpoint:GET /b/c"],
        ),
        ('@RestController @RequestMapping("/a/") class C { @GetMapping void g() {} }', ["endpoint:GET /a/"]),
        ("@RestController class C { @GetMapping void g() {} }", ["endpoint:GET /"]),
        ('class NotAController { @GetMapping("/a") void g() {} }', []),
    ],
)
def test_inbound_rest_shapes(tmp_path, backend, body, expected):
    assert targets(extract(setup_repo(tmp_path, _java(body))), "EXPOSES") == expected


def test_mongo_shapes(tmp_path, backend):
    files = _java('@Document(collection = "orders") public class Order { String id; }', "Order")
    files |= _java(
        """@org.springframework.stereotype.Repository public class C {
    private final MongoTemplate m = null;
    void a(Query q) { m.find(q, Order.class); }
    void b(Order o) { m.save(o); }
    void c(Query q, String dyn) { m.remove(q, dyn); }
    void d(Object o) { m.save(o); }
    void e() { m.indexOps("ignored"); }
}"""
    )
    entry = extract(setup_repo(tmp_path, files))
    assert sorted(
        (e["kind"], e["to"]) for e in entry["edges"] if e["provenance"]["extractor"].startswith("mongo")
    ) == [
        ("READS_COLLECTION", "collection:orders"),
        ("WRITES_COLLECTION", "collection:<C.dyn>"),
        ("WRITES_COLLECTION", "collection:<C:7>"),
        ("WRITES_COLLECTION", "collection:orders"),
    ]


def test_repository_of_unknown_type_is_not_guessed(tmp_path, backend):
    files = _java("public interface C extends MongoRepository<Outside, String> { }")
    entry = extract(setup_repo(tmp_path, files))
    assert entry["unresolved"] == ["collection:<C.Outside>"]


def test_repository_through_a_local_base_interface(tmp_path, backend):
    files = _java('@Document("things") public class Thing { }', "Thing")
    files |= _java("public interface Base<T> extends MongoRepository<T, String> { }", "Base")
    files |= _java("public interface C extends Base<Thing> { }")
    entry = extract(setup_repo(tmp_path, files))
    extractors = [
        (e["from"], e["to"]) for e in entry["edges"] if e["provenance"]["extractor"] == "spring-data-generic"
    ]
    assert extractors == [("class:com.x.C", "collection:things")] and entry["unresolved"] == []


def test_document_without_a_name_uses_springs_rule(tmp_path, backend):
    entry = extract(setup_repo(tmp_path, _java("@Document public class C { }")))
    assert targets(entry) == ["collection:c"]


def test_messaging_defaults_and_receive(tmp_path, backend):
    body = """public class C {
    private final JmsTemplate jms = null;
    private final KafkaTemplate<String, String> kafka = null;
    void a(String p) { jms.convertAndSend(p); }
    void b() { jms.receiveAndConvert("IN.Q"); }
    void c() { kafka.sendDefault("v"); }
    void d(ProducerRecord<String, String> record) { kafka.send(record); }
    @KafkaListener(topics = {"t1", "t2"}) void e() { }
    @KafkaListener(topicPattern = "pat.*") void f() { }
    @KafkaListener(id = "x") void g() { }
}"""
    entry = extract(setup_repo(tmp_path, _java(body)))
    assert sorted((e["kind"], e["to"]) for e in entry["edges"]) == [
        ("CONSUMES", "queue:IN.Q"),
        ("CONSUMES", "topic:<C:11>"),
        ("CONSUMES", "topic:pat.*"),
        ("CONSUMES", "topic:t1"),
        ("CONSUMES", "topic:t2"),
        ("PUBLISHES", "queue:<C:5>"),
        ("PUBLISHES", "topic:<C:8>"),
    ]


def test_flat_file_setter_and_missing_resource(tmp_path, backend):
    body = """public class C {
    FlatFileItemReader<String> a(@Value("${in.path:/in.csv}") String path) {
        FlatFileItemReader<String> reader = new FlatFileItemReader<>();
        reader.setResource(new FileSystemResource(path));
        return reader;
    }
    Object b() { return new FlatFileItemWriterBuilder<String>().name("w").build(); }
    Object c() {
        return new FlatFileItemReaderBuilder<String>().resource(new ClassPathResource("c.csv")).build();
    }
}"""
    entry = extract(setup_repo(tmp_path, _java(body)))
    assert sorted((e["kind"], e["to"]) for e in entry["edges"]) == [
        ("READS_FILE", "file:/in.csv"),
        ("READS_FILE", "file:classpath:c.csv"),
        ("WRITES_FILE", "file:<C:8>"),
    ]


def test_old_job_builder_factory(tmp_path, backend):
    body = 'public class C { JobBuilderFactory f; Object a() { return f.get("oldJob").start(s).build(); } }'
    assert targets(extract(setup_repo(tmp_path, _java(body)))) == ["job:oldJob"]


def test_annotations_on_a_nested_type_belong_to_it(tmp_path, backend):
    body = """public class C {
    @Document(collection = "inner") public static class In { }
}"""
    edge = extract(setup_repo(tmp_path, _java(body)))["edges"][0]
    assert edge["from"] == "class:com.x.C.In"


# -- modules, stack, layout ----------------------------------------------------------------------------------


def test_declared_modules_are_walked_and_undeclared_nested_projects_are_not(tmp_path, backend):
    pom = """<project><modules><module>core</module></modules>
    <properties><maven.compiler.release>17</maven.compiler.release></properties></project>"""
    source = 'package com.x;\n@Document(collection = "{}") public class D {{ }}\n'
    files = {
        "core/pom.xml": "<project><dependencies><dependency><artifactId>spring-kafka</artifactId>"
        "</dependency></dependencies></project>",
        "core/src/main/java/com/x/D.java": source.format("declared"),
        "other/pom.xml": "<project/>",
        "other/src/main/java/com/x/D.java": source.format("separate"),
    }
    central = setup_repo(tmp_path, files, pom=pom)
    entry = extract(central)
    assert targets(entry) == ["collection:declared"]
    assert entry["edges"][0]["provenance"]["file"].startswith("core/src/main/java")
    code, out, _ = run_cli("extract-stack", "--central", str(central), "--json")
    row = json.loads(out)["repos"][0]
    assert row["java"] == "17" and row["messaging"] == "kafka"
    assert any("other has its own build file" in w for w in questions(central)["warnings"])


def _stack_row(central):
    code, out, err = run_cli("extract-stack", "--central", str(central), "--json")
    assert code == 0, err
    document = json.loads(out)
    jsonschema.validate(document, schema("stack-detected"))
    return document["repos"][0]


def _bare_repo(tmp_path, files):
    repo = tmp_path / "svc"
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    central = tmp_path / "central"
    write_project(central, [("svc", "../svc")])
    return central


def test_gradle_groovy_with_commented_dependency(tmp_path):
    gradle = """plugins { id 'org.springframework.boot' version '3.2.1' }
sourceCompatibility = '17'
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    // implementation 'org.springframework.kafka:spring-kafka'
    /* implementation 'org.springframework.boot:spring-boot-starter-batch' */
    testImplementation 'org.testcontainers:mongodb:1.2'
    testImplementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
}"""
    row = _stack_row(_bare_repo(tmp_path, {"build.gradle": gradle, "gradlew": "#!/bin/sh\n"}))
    assert row["build"] == "gradle" and row["buildCmd"] == "./gradlew build"
    assert row["java"] == "17" and row["springBoot"] == "3.2.1" and row["web"] == "spring-webflux"
    assert row["messaging"] == "unknown" and row["batch"] is False and row["datastore"] == "unknown"


def test_maven_values_come_from_detected_text_never_defaults(tmp_path):
    pom = """<project xmlns="http://maven.apache.org/POM/4.0.0">
    <parent><artifactId>corporate-parent</artifactId><version>9</version></parent>
    <properties><java.version>${inherited.java}</java.version></properties>
    <!-- <dependency><artifactId>spring-kafka</artifactId></dependency> -->
    <dependencies>
      <dependency><artifactId>spring-boot-starter-batch</artifactId><scope>test</scope></dependency>
    </dependencies>
    <dependencyManagement><dependencies>
      <dependency><artifactId>spring-boot-starter-web</artifactId></dependency>
    </dependencies></dependencyManagement>
    </project>"""
    row = _stack_row(_bare_repo(tmp_path, {"pom.xml": pom}))
    assert row["buildCmd"] == "mvn -q verify"
    assert row["java"] == "unknown" and row["springBoot"] == "unknown"
    assert row["batch"] is False and row["messaging"] == "unknown" and row["web"] == "unknown"


def test_boot_version_through_property_and_bom(tmp_path):
    pom = """<project><properties><boot>3.4.0</boot></properties>
    <dependencyManagement><dependencies>
      <dependency><artifactId>spring-boot-dependencies</artifactId><version>${boot}</version></dependency>
    </dependencies></dependencyManagement></project>"""
    assert _stack_row(_bare_repo(tmp_path, {"pom.xml": pom}))["springBoot"] == "3.4.0"


def test_no_build_file_is_all_unknown(tmp_path):
    central = _bare_repo(tmp_path, {"README.md": "hello"})
    row = _stack_row(central)
    assert row["build"] == "unknown" and row["buildFileSha256"] == "unknown" and row["archunit"] == "missing"
    assert "stack:svc:build" in [q["id"] for q in questions(central)["questions"]]


def test_both_build_tools_is_a_question(tmp_path):
    central = _bare_repo(tmp_path, {"pom.xml": "<project/>", "build.gradle": ""})
    assert _stack_row(central)["build"] == "unknown"
    assert any(q["id"].startswith("build-file:svc:both") for q in questions(central)["questions"])


def test_malformed_package_json(tmp_path):
    central = _bare_repo(tmp_path, {"package.json": "{not json"})
    row = _stack_row(central)
    assert row["build"] == "npm" and row["ui"] == "unknown" and row["buildCmd"] == "unknown"


@pytest.mark.parametrize(
    ("files", "expected", "note"),
    [
        (
            {"a/C1": "@Service", "b/C2": "@Service", "c/C3": "@Document"},
            {"adapters": "unknown", "application": "unknown", "domain": "com.x.c"},
            "split across a, b",
        ),
        (
            {"a/C1": "@Service", "a/C2": "@Document"},
            {"adapters": "unknown", "application": "unknown", "domain": "unknown"},
            "shares com.x.a",
        ),
    ],
)
def test_layout_that_cannot_be_settled_is_unknown(tmp_path, backend, files, expected, note):
    sources = {"src/main/java/com/x/App.java": "package com.x;\n@SpringBootApplication class App { }"}
    for rel, annotation in files.items():
        package, name = rel.split("/")
        sources[f"src/main/java/com/x/{package}/{name}.java"] = (
            f"package com.x.{package};\n{annotation} class {name} {{ }}"
        )
    central = setup_repo(tmp_path, sources)
    assert _stack_row(central)["layout"] == expected
    match = [q for q in questions(central)["questions"] if q["id"] == "layout:svc"]
    assert any(note in text for text in match[0]["detail"])


# -- missing input ---------------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["extract-stack", "extract", "onboard"])
def test_missing_repo_path_is_exit_2_and_writes_nothing(tmp_path, command):
    central = tmp_path / "central"
    write_project(central, [("gone", "../gone")])
    code, _, err = run_cli(command, "--central", str(central))
    assert code == 2 and "gone" in err
    for name in GENERATED_FILES:
        assert not (central / name).exists()


@pytest.mark.parametrize("command", ["extract-stack", "extract"])
def test_unknown_repo_name_is_exit_2(fixture_central, command):
    code, _, err = run_cli(command, "--central", str(fixture_central), "--repo", "nope")
    assert code == 2 and "nope" in err


@pytest.mark.parametrize("command", ["extract-stack", "extract", "onboard"])
def test_no_project_md_is_exit_2(tmp_path, command):
    assert run_cli(command, "--central", str(tmp_path))[0] == 2


def test_project_md_without_a_repo_table_is_exit_2(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile/project.md").write_text("| Key | Value |\n| --- | --- |\n| a | b |\n")
    assert run_cli("extract", "--central", str(tmp_path))[0] == 2


def test_path_column_alone_names_the_repo(tmp_path):
    make_java_repo(tmp_path, "svc", {})
    central = tmp_path / "central"
    (central / "profile").mkdir(parents=True)
    (central / "profile/project.md").write_text(
        "| Key | Value |\n| --- | --- |\n| project.name | S |\n\n## Repos\n"
        "| Path | What it is |\n| --- | --- |\n| `../svc` | x |\n"
    )
    assert extract(central)["repo"] == "svc"


# -- commit ----------------------------------------------------------------------------------------


def test_commit_comes_from_git_when_the_repo_is_its_own(tmp_path, backend):
    central = setup_repo(tmp_path, publisher('"t"'))
    repo = tmp_path / "svc"
    git(repo, "init", "-q")
    assert extract(central)["commit"] == "unknown"  # no commits yet: nothing to name
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "x")
    expected = git(repo, "rev-parse", "--short=7", "HEAD")
    assert extract(central)["commit"] == expected
    assert not any(q["id"].startswith("commit:") for q in questions(central)["questions"])
    (repo / "pom.xml").write_text(" ")
    assert any("uncommitted" in w for w in questions(central)["warnings"])


def test_commit_is_unknown_when_not_a_git_repo(tmp_path, backend):
    central = setup_repo(tmp_path, publisher('"t"'))
    assert extract(central)["commit"] == "unknown"
    match = [q for q in questions(central)["questions"] if q["id"] == "commit:svc"]
    assert "not a git repository" in match[0]["ask"]


def test_a_folder_inside_another_repo_does_not_borrow_its_commit(fixture_central, backend):
    code, out, _ = run_cli("extract", "--central", str(fixture_central), "--json")
    assert {r["commit"] for r in json.loads(out)["repos"]} == {"unknown"}


def test_hook_git_environment_does_not_leak_into_the_commit(tmp_path, monkeypatch):
    central = setup_repo(tmp_path, publisher('"t"'))
    repo = tmp_path / "svc"
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "x")
    expected = git(repo, "rev-parse", "--short=7", "HEAD")
    monkeypatch.setenv("GIT_DIR", str(ROOT / ".git"))
    assert extract(central)["commit"] == expected


# -- repeatability ---------------------------------------------------------------------------------


def _strip_generated(text):
    return "\n".join(ln for ln in text.splitlines() if not ln.startswith("generated:"))


def test_two_runs_are_identical_apart_from_the_generated_line(fixture_central, backend):
    contents = []
    for _ in range(2):
        assert run_cli("onboard", "--allow-sample", "--central", str(fixture_central))[0] == 0
        contents.append({n: (fixture_central / n).read_text() for n in GENERATED_FILES})
    for name in GENERATED_FILES:
        assert _strip_generated(contents[0][name]) == _strip_generated(contents[1][name])


def test_both_backends_write_the_same_edges(fixture_central, monkeypatch):
    if not javaparser_backend.available():
        pytest.skip("no JDK on the PATH")

    def edges():
        assert run_cli("extract", "--central", str(fixture_central))[0] == 0
        return [
            {k: v for k, v in r.items() if k != "parser"}
            for r in miniyaml.load_file(str(fixture_central / "profile/dependencies.yaml"))["repos"]
        ]

    with_ast = edges()
    monkeypatch.setenv("BATON_JAVA_PARSER", "regex")
    assert edges() == with_ast


def test_generated_line_format(fixture_central):
    run_cli("extract-stack", "--central", str(fixture_central))
    text = (fixture_central / "profile/stack-detected.md").read_text()
    assert re.search(r"^generated: \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ by baton extract-stack \S+$", text, re.M)
    assert (
        text.count("\n|") == 3
    )  # header, separator, then the second row; the first row follows the first newline


# -- a partial run ---------------------------------------------------------------------------------


def test_repo_option_keeps_the_other_repos(fixture_central, backend):
    assert run_cli("extract", "--central", str(fixture_central))[0] == 0
    before = miniyaml.load_file(str(fixture_central / "profile/dependencies.yaml"))
    code, _, _ = run_cli("extract", "--central", str(fixture_central), "--repo", "sample-react-repo")
    assert code == 0
    after = miniyaml.load_file(str(fixture_central / "profile/dependencies.yaml"))
    assert after["repos"] == before["repos"]
    assert len(miniyaml.load_file(str(fixture_central / "profile/aggregates.yaml"))["aggregates"]) == 2
    code, out, _ = run_cli(
        "extract-stack", "--central", str(fixture_central), "--repo", "sample-react-repo", "--json"
    )
    rows = json.loads(out)["repos"]
    jsonschema.validate({"generated": "x", "repos": rows}, schema("stack-detected"))
    assert [r["repo"] for r in rows] == ["sample-java-repo", "sample-react-repo"]
    assert rows[0]["batch"] is True and rows[0]["layout"]["domain"] == "com.example.sample.domain"


# -- what a human reviewed survives ----------------------------------------------------------------


def _doc(name, extra=""):
    return {
        f"src/main/java/com/x/{name}.java": f'package com.x;\n@Document(collection = "{name.lower()}") '
        f"public record {name}(String id{extra}) {{ }}\n"
    }


def test_confirmed_aggregate_survives_and_unconfirmed_is_regenerated(tmp_path, backend):
    central = setup_repo(tmp_path, _doc("Alpha") | _doc("Beta", ", String alphaId"))
    assert run_cli("extract", "--central", str(central))[0] == 0
    path = central / "profile/aggregates.yaml"
    text = path.read_text().replace(
        "name: Alpha\n    root: class:com.x.Alpha\n    collection: alpha\n    members: []\n    references: "
        "[]\n"
        "    confirmed: false",
        "name: Renamed\n    root: class:com.x.Alpha\n    collection: alpha\n    members: []\n    "
        "references: []\n"
        "    confirmed: true",
    )
    assert "Renamed" in text
    path.write_text(text)
    (tmp_path / "svc/src/main/java/com/x/Beta.java").write_text(
        '@Document(collection = "beta") public record Beta(String id) { }\n'.replace(
            "@Document", "package com.x;\n@Document"
        )
    )
    assert run_cli("extract", "--central", str(central))[0] == 0
    entries = {a["root"]: a for a in miniyaml.load_file(str(path))["aggregates"]}
    assert (
        entries["class:com.x.Alpha"]["name"] == "Renamed"
        and entries["class:com.x.Alpha"]["confirmed"] is True
    )
    assert entries["class:com.x.Beta"]["references"] == []


def test_all_confirmed_files_keep_their_bytes(tmp_path, backend):
    central = setup_repo(tmp_path, _doc("Alpha"))
    assert run_cli("extract", "--central", str(central))[0] == 0
    path = central / "profile/aggregates.yaml"
    edited = "# my own comment\n" + path.read_text().replace("confirmed: false", "confirmed: true")
    path.write_text(edited)
    assert run_cli("extract", "--central", str(central))[0] == 0
    assert path.read_text() == edited


def test_reviewed_zone_survives_and_new_paths_are_asked_about(tmp_path, backend):
    source = "package com.x;\nimport java.math.BigDecimal;\nclass Fee { BigDecimal b; }\n"
    central = setup_repo(tmp_path, {"src/main/java/com/x/Fee.java": source})
    assert run_cli("extract", "--central", str(central))[0] == 0
    path = central / "profile/risk-zones.yaml"
    path.write_text(
        'zones:\n  - name: money\n    paths: ["**/Fee.java"]\n    cap: 40\n'
        "  - name: my-own\n    paths: [x/**]\n    cap: 30\n"
    )
    first = questions(central)
    assert "confirm-risk-zones" not in [q["id"] for q in first["questions"]]
    assert "risk-zone-new-paths:money" not in [q["id"] for q in first["questions"]]
    (tmp_path / "svc/src/main/java/com/x/Other.java").write_text(source.replace("Fee", "Other"))
    report = questions(central)
    zones = {z["name"]: z for z in miniyaml.load_file(str(path))["zones"]}
    assert zones["money"]["cap"] == 40 and zones["money"]["paths"] == ["**/Fee.java"] and "my-own" in zones
    match = [q for q in report["questions"] if q["id"] == "risk-zone-new-paths:money"]
    assert match[0]["seeds"] == ["src/main/java/com/x/Other.java"]


def test_auth_migration_and_money_seeds(tmp_path, backend):
    files = {
        "src/main/java/com/x/Sec.java": "package com.x;\nimport "
        "org.springframework.security.core.Authentication;\nclass Sec { }\n",
        "src/main/java/com/x/security/Filter.java": "package com.x.security;\nclass Filter { }\n",
        "src/main/java/com/x/Chg.java": 'package com.x;\n@ChangeUnit(id = "1") class Chg { }\n',
        "src/main/resources/db/migration/V1__a.sql": "select 1;\n",
        "src/main/java/com/x/Dec.java": "package com.x;\nimport org.bson.types.Decimal128;\nclass Dec { "
        "Decimal128 d; }\n",
    }
    central = setup_repo(tmp_path, files)
    assert run_cli("extract", "--central", str(central))[0] == 0
    document = miniyaml.load_file(str(central / "profile/risk-zones.yaml"))
    jsonschema.validate(document, schema("risk-zones"))
    assert {z["name"]: z["paths"] for z in document["zones"]} == {
        "auth": ["src/main/java/com/x/Sec.java", "src/main/java/com/x/security/Filter.java"],
        "migration": ["src/main/java/com/x/Chg.java", "src/main/resources/db/migration/V1__a.sql"],
        "money": ["src/main/java/com/x/Dec.java"],
    }


def test_aggregate_seed_embedded_member_dbref_and_unknown_id(tmp_path, backend):
    files = {
        "src/main/java/com/x/AlphaDoc.java": (
            'package com.x;\nimport java.util.List;\n@Document("alpha") public class AlphaDoc {\n'
            "  String betaId; String customerRef; List<Line> lines; @DBRef GammaDocument gamma;\n}\n"
        ),
        "src/main/java/com/x/BetaDoc.java": 'package com.x;\n@Document("beta") class BetaDoc { }\n',
        "src/main/java/com/x/GammaDocument.java": 'package com.x;\n@Document("gamma") class GammaDocument '
        "{ }\n",
        "src/main/java/com/x/Line.java": "package com.x;\nclass Line { }\n",
    }
    central = setup_repo(tmp_path, files)
    assert run_cli("extract", "--central", str(central))[0] == 0
    entries = {
        a["name"]: a for a in miniyaml.load_file(str(central / "profile/aggregates.yaml"))["aggregates"]
    }
    assert entries["Alpha"]["references"] == ["Beta", "Gamma"] and entries["Alpha"]["members"] == [
        "class:com.x.Line"
    ]
    assert all(a["confirmed"] is False for a in entries.values())


def test_confirmed_aggregate_whose_root_is_gone_is_asked_about(tmp_path, backend):
    central = setup_repo(tmp_path, _doc("Alpha"))
    (central / "profile/aggregates.yaml").write_text(
        "aggregates:\n  - name: Old\n    root: class:com.x.Old\n    collection: old\n    confirmed: true\n"
    )
    report = questions(central)
    assert "stale-aggregate:class:com.x.Old" in [q["id"] for q in report["questions"]]
    assert [
        a["name"] for a in miniyaml.load_file(str(central / "profile/aggregates.yaml"))["aggregates"]
    ] == ["Alpha", "Old"]


@pytest.mark.parametrize("name", ["aggregates.yaml", "risk-zones.yaml"])
def test_unreadable_reviewed_file_refuses_and_changes_nothing(tmp_path, name):
    central = setup_repo(tmp_path, _doc("Alpha"))
    path = central / "profile" / name
    path.write_text("aggregates:\n  - name: x\n bad indent: [\n: :\n")
    before = path.read_text()
    code, _, err = run_cli("extract", "--central", str(central))
    assert code == 1 and name in err
    assert path.read_text() == before and not (central / "profile/dependencies.yaml").exists()


# -- the YAML writer -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "plain",
        "1234567",
        "12.5",
        "true",
        "no",
        "null",
        "~",
        "",
        " spaced ",
        "a: b",
        "a #b",
        "#start",
        "- x",
        "[x]",
        "{x}",
        "endpoint:GET /a/{b}",
        "endpoint:${x:y}/z",
        "topic:<C.a b>",
        "a,b",
        'has "double"',
        "it's",
        "*star",
        "file:/data/a b.csv",
        "@at",
        "x:",
        "%p",
        "!b",
        "|",
        ">",
        "`t`",
        "a\tb",
        "ünï",
    ],
)
def test_writer_round_trips_awkward_scalars(value):
    document = {
        "s": value,
        "l": [value, "z"],
        "m": {"provenance": {"file": value, "line": 3}},
        "e": [{"a": value, "b": [value]}, {"a": 1, "b": []}],
    }
    assert miniyaml.loads(yamlio.dumps(document)) == document


def test_writer_refuses_what_it_cannot_represent():
    with pytest.raises(ValueError):
        yamlio.dumps({"s": "line one\nline two"})


def test_all_digit_commit_stays_a_string():
    document = {"repos": [{"repo": "r", "commit": "1234567", "edges": []}]}
    assert miniyaml.loads(yamlio.dumps(document))["repos"][0]["commit"] == "1234567"


# -- the CLI as a process --------------------------------------------------------------------------


def test_help_works_and_says_what_it_does():
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    for command, phrase in (
        ("extract-stack", "build files"),
        ("extract", "dependencies.yaml"),
        ("onboard", "open questions"),
    ):
        done = subprocess.run(
            [sys.executable, str(Path(ROOT) / "tools/baton/cli.py"), command, "--help"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert done.returncode == 0, done.stderr
        assert phrase in done.stdout and "--central" in done.stdout and "--json" in done.stdout
