"""Fast checks on the fixtures and sensor files: no build tool runs here."""
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import jsonschema
import pytest
from w6support import JAVA_FIXTURE, REACT_FIXTURE, ROOT, copy_fixture, git

SENSORS = ROOT / "sensors"
EXPECTED = json.loads((JAVA_FIXTURE / "EXPECTED.json").read_text())
REPOS = [(JAVA_FIXTURE, EXPECTED), (JAVA_FIXTURE / "variants/gradle-kts", EXPECTED["variants"][0])]
CONTRACT_EXTRACTORS = {
    "document-annotation", "spring-data-generic", "mongo-template-literal", "request-mapping",
    "rest-client-base-url", "kafka-listener", "kafka-template", "jms-listener", "jms-template",
    "flatfile-reader", "flatfile-writer", "job-builder",
}
JAVA_MANIFEST = json.loads((JAVA_FIXTURE / "violations/MANIFEST.json").read_text())
REACT_MANIFEST = json.loads((REACT_FIXTURE / "violations/MANIFEST.json").read_text())
# Source text that an extractor turns into an edge: anything here without an edge means EXPECTED is short.
EDGE_TOKENS = re.compile(
    r"@Document\(|extends MongoRepository<|mongo\.(find|insert|save|remove|update)\w*\(|"
    r"@(Get|Post|Put|Delete|Patch|Request)Mapping\(|\.(get|post|put|delete|patch)\(\)\.uri\(|"
    r"@KafkaListener\(|kafka\.send\(|@JmsListener\(|jms\.convertAndSend\(|"
    r"new FlatFileItem(Reader|Writer)Builder|new JobBuilder\("
)
CLASS_LEVEL_MAPPING = '@RequestMapping("/api/v1/fees")'


def edges_of(entry):
    return entry["edges"]


@pytest.mark.parametrize("root,entry", REPOS, ids=["maven", "gradle"])
def test_every_edge_line_is_exact_and_its_anchor_unique(root, entry):
    for edge in edges_of(entry):
        lines = (root / edge["provenance"]["file"]).read_text().splitlines()
        assert edge["anchor"] in lines[edge["provenance"]["line"] - 1], edge
        assert sum(edge["anchor"] in line for line in lines) == 1, edge


@pytest.mark.parametrize("root,entry", REPOS, ids=["maven", "gradle"])
def test_every_edge_source_in_the_tree_is_listed(root, entry):
    listed = {(e["provenance"]["file"], e["provenance"]["line"]) for e in edges_of(entry)}
    found = set()
    for path in (root / "src/main/java").rglob("*.java"):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if EDGE_TOKENS.search(line) and CLASS_LEVEL_MAPPING not in line:
                found.add((path.relative_to(root).as_posix(), number))
    assert found == listed


def test_every_contract_extractor_and_kind_is_planted():
    edges = edges_of(EXPECTED)
    assert {e["provenance"]["extractor"] for e in edges} == CONTRACT_EXTRACTORS
    kinds = json.loads((ROOT / "schemas/dependencies.json").read_text())
    enum = kinds["properties"]["repos"]["items"]["properties"]["edges"]["items"]["properties"]["kind"]["enum"]
    assert {e["kind"] for e in edges} == set(enum)


def test_a_deliberately_unresolvable_target_is_listed_and_absent_from_config():
    target = "endpoint:${ledger.base-url}/v1/postings"
    assert EXPECTED["unresolved"] == [target]
    assert target in {e["to"] for e in EXPECTED["edges"]}
    assert "ledger" not in (JAVA_FIXTURE / "src/main/resources/application.yml").read_text()


def test_yml_resolved_targets_really_come_from_the_yml():
    yml = (JAVA_FIXTURE / "src/main/resources/application.yml").read_text()
    for value in ("fee.events", "https://rates.example.test", "/data/outbound/accruals.csv"):
        assert value in yml


def test_edges_validate_against_the_dependencies_schema():
    schema = json.loads((ROOT / "schemas/dependencies.json").read_text())
    doc = {"generated": "fixture", "repos": [
        {"repo": entry["repo"], "commit": "fixture", "edges": entry["edges"],
         "unresolved": entry["unresolved"]}
        for _root, entry in REPOS
    ]}
    jsonschema.validate(doc, schema)


def test_aggregates_validate_against_their_schema():
    schema = json.loads((ROOT / "schemas/aggregates.json").read_text())
    for _root, entry in REPOS:
        jsonschema.validate({"aggregates": entry["aggregates"]}, schema)


@pytest.mark.parametrize("root,entry,build_file", [
    (JAVA_FIXTURE, EXPECTED, "pom.xml"),
    (JAVA_FIXTURE / "variants/gradle-kts", EXPECTED["variants"][0], "build.gradle.kts"),
    (REACT_FIXTURE, json.loads((REACT_FIXTURE / "EXPECTED.json").read_text()), "package.json"),
], ids=["maven", "gradle", "react"])
def test_stack_facts_validate_and_the_hash_is_current(root, entry, build_file):
    schema = json.loads((ROOT / "schemas/stack-detected.json").read_text())
    jsonschema.validate({"generated": "fixture", "repos": [entry["stack"]]}, schema)
    assert entry["stack"]["buildFileSha256"] == hashlib.sha256((root / build_file).read_bytes()).hexdigest()


def test_collections_match_the_document_annotations():
    for root, entry in REPOS:
        for item in entry["collections"]:
            line = (root / item["file"]).read_text().splitlines()[item["line"] - 1]
            assert f'collection = "{item["name"]}"' in line


def test_money_seed_lists_every_money_file():
    money = next(z for z in EXPECTED["riskZoneSeeds"] if z["reason"] == "money")
    found = {p.relative_to(JAVA_FIXTURE).as_posix() for p in (JAVA_FIXTURE / "src/main/java").rglob("*.java")
             if "BigDecimal" in p.read_text()}
    assert found == set(money["files"])


def test_layout_packages_exist():
    for root, entry in REPOS:
        for package in entry["layout"].values():
            assert (root / "src/main/java" / package.replace(".", "/")).is_dir()


def _copy(tmp_path, source):
    return copy_fixture(source, tmp_path / "repo")


@pytest.mark.parametrize("item", JAVA_MANIFEST["violations"], ids=lambda v: v["patch"])
def test_java_patch_applies_to_the_clean_tree(tmp_path, item):
    repo = _copy(tmp_path, JAVA_FIXTURE)
    git(repo, "apply", "--check", f"violations/{item['patch']}")


@pytest.mark.parametrize("item", REACT_MANIFEST["violations"], ids=lambda v: v["patch"])
def test_react_patch_applies_to_the_clean_tree(tmp_path, item):
    repo = _copy(tmp_path, REACT_FIXTURE)
    git(repo, "apply", "--check", f"violations/{item['patch']}")


def test_all_brief_violations_have_a_patch():
    patches = {v["patch"] for v in JAVA_MANIFEST["violations"]}
    assert {"logic-in-controller.patch", "raw-document-in-service.patch", "second-named-rule.patch",
            "query-without-period-key.patch", "field-injection.patch", "long-method.patch",
            "new-dependency.patch"} <= patches
    assert {p.name for p in (JAVA_FIXTURE / "violations").glob("*.patch")} == patches


@pytest.mark.parametrize("copy", [
    "config/sensors/checkstyle.xml", "config/sensors/pmd-ruleset.xml",
    "variants/gradle-kts/config/sensors/checkstyle.xml",
    "variants/gradle-kts/config/sensors/pmd-ruleset.xml",
])
def test_fixture_runs_the_real_sensor_files(copy):
    assert (JAVA_FIXTURE / copy).read_text() == (SENSORS / copy.rsplit("/", 1)[-1]).read_text()


def test_react_fixture_runs_the_real_eslint_file():
    copied = (REACT_FIXTURE / "config/sensors/eslint-sensors.json").read_text()
    assert copied == (SENSORS / "eslint-sensors.json").read_text()


@pytest.mark.parametrize("target", [
    JAVA_FIXTURE / "src/test/java/com/example/sample/ArchitectureTest.java",
    JAVA_FIXTURE / "variants/gradle-kts/src/test/java/com/example/samplegradle/ArchitectureTest.java",
], ids=["maven", "gradle"])
def test_fixture_architecture_test_differs_only_in_package(target):
    def rules(text):
        return re.sub(r"com\.example\.\w+", "PKG", re.sub(r" *// set from.*", "", text))
    assert rules(target.read_text()) == rules((SENSORS / "ArchitectureTest.java").read_text())


@pytest.mark.parametrize("name", ["checkstyle.xml", "pmd-ruleset.xml"])
def test_every_custom_message_has_remediation(name):
    root = ET.parse(SENSORS / name).getroot()
    if name.startswith("pmd"):
        messages = [e.get("message") for e in root.iter() if e.tag.endswith("rule")]
    else:
        messages = [e.get("value") for e in root.iter("message")]
    assert messages and all("REMEDIATION:" in m for m in messages)
    if name == "checkstyle.xml":
        checks = [m for m in root.iter("module") if m.get("name") not in ("Checker", "TreeWalker")]
        assert all(m.find("message") is not None for m in checks)


def test_eslint_custom_messages_have_remediation():
    rules = json.loads((SENSORS / "eslint-sensors.json").read_text())["rules"]["no-restricted-syntax"][1:]
    assert len(rules) == 2 and all("REMEDIATION:" in r["message"] for r in rules)


def test_architecture_rules_all_have_remediation():
    for name in ("ArchitectureTest.java", "ProjectArchitectureTest.java"):
        text = (SENSORS / name).read_text()
        assert text.count("@ArchTest") == text.count('because("REMEDIATION:'), name


def test_project_template_has_three_commented_examples():
    text = (SENSORS / "ProjectArchitectureTest.java").read_text()
    for rule in ("singleImplementationOfNamedRule", "thinBatchWriters", "noRawDatastoreTypeInServices"):
        assert f"// static final ArchRule {rule}" in text


def test_pit_snippets_set_no_threshold():
    for name in ("pitest-snippet.xml", "build.gradle.kts"):
        assert "mutationThreshold" not in re.sub(r"no mutationThreshold", "", (SENSORS / name).read_text())


def test_no_project_words_in_sensors_or_fixtures():
    words = ROOT / "tools/baton/tests/project_words.py"
    spec = importlib.util.spec_from_file_location("project_words", words)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    words = module.PROJECT_WORDS
    if words is None:
        pytest.skip("no project word list (tools/baton/tests/project-words.local.txt or BATON_PROJECT_WORDS)")
    for base in (SENSORS, JAVA_FIXTURE, REACT_FIXTURE):
        for path in base.rglob("*"):
            ignored = {"node_modules", "target", "build", ".gradle"}.intersection(path.parts)
            if path.is_file() and not ignored and path.name != "package-lock.json":
                assert not words.search(path.read_text(errors="ignore")), path


# Semgrep rules: the engine is not installed, so the regexes run under Python re (see sensors/README.md).
SEMGREP_CASES = {
    "hardcoded-secret": (['String password = "hunter22";', 'api_key: "abcd1234"', 'apiKey = "abcd1234"'],
                         ['String password = "${DB_PASSWORD}";', "String password = System.getenv(\"P\");",
                          "spring.password: ${DB}"]),
    "identifier-in-log": (['log.info("posting {}", accountNumber);', 'logger.error("x " + ssn);'],
                          ['log.debug("x {}", accountNumber);', 'log.info("posted {}", correlationId);']),
    "where-operator-query": (['new Document("$where", "this.a > 1");'], ['new Document("$gt", 1);']),
    "string-built-query": (['em.createNativeQuery("select * from t where a=" + a);',
                            'new BasicQuery("{a: " + a + "}");'],
                           ['em.createNativeQuery("select * from t where a=:a");']),
}


def _semgrep_rules():
    text = (SENSORS / "semgrep/banking.yaml").read_text()
    rules = {}
    for block in text.split("  - id: ")[1:]:
        rules[block.splitlines()[0].strip()] = {
            "regex": re.search(r"^\s*pattern-regex: (.+)$", block, re.M).group(1),
            "message": re.search(r'^\s*message: "(.+)"$', block, re.M).group(1),
        }
    return rules


def test_semgrep_rules_cover_the_brief_and_say_how_to_fix():
    rules = _semgrep_rules()
    assert set(rules) == set(SEMGREP_CASES)
    assert all("REMEDIATION:" in r["message"] for r in rules.values())


@pytest.mark.parametrize("rule", sorted(SEMGREP_CASES))
def test_semgrep_regex_catches_positives_and_passes_negatives(rule):
    regex = re.compile(_semgrep_rules()[rule]["regex"], re.M)
    positives, negatives = SEMGREP_CASES[rule]
    assert all(regex.search(text) for text in positives), positives
    assert not any(regex.search(text) for text in negatives), negatives


def _dep_check(repo, base="main"):
    return subprocess.run([sys.executable, str(SENSORS / "new_dependency_check.py"), "--repo", str(repo),
                           "--base", base], capture_output=True, text=True)


def test_new_dependency_clean_tree_passes(tmp_path):
    done = _dep_check(_copy(tmp_path, JAVA_FIXTURE))
    assert done.returncode == 0 and done.stdout == ""


def test_new_dependency_patch_is_caught_with_remediation(tmp_path):
    repo = _copy(tmp_path, JAVA_FIXTURE)
    git(repo, "apply", "violations/new-dependency.patch")
    done = _dep_check(repo)
    assert done.returncode == 1
    assert "org.apache.commons:commons-lang3" in done.stdout and "REMEDIATION:" in done.stdout


def test_new_dependency_in_gradle_kts_and_package_json(tmp_path):
    repo = _copy(tmp_path, JAVA_FIXTURE)
    build = repo / "variants/gradle-kts/build.gradle.kts"
    build.write_text(build.read_text().replace(
        "dependencies {\n", 'dependencies {\n    implementation("com.example:extra:1.0")\n', 1))
    (repo / "package.json").write_text('{"devDependencies": {"left-pad": "1"}}')
    done = _dep_check(repo)
    assert done.returncode == 1
    assert "com.example:extra" in done.stdout and "left-pad" in done.stdout
    assert done.stdout.count("REMEDIATION:") == 2


def test_new_dependency_bad_ref_exits_2(tmp_path):
    assert _dep_check(_copy(tmp_path, JAVA_FIXTURE), "no-such-ref").returncode == 2


def test_mvnw_is_executable():
    assert shutil.which("mvnw", path=str(JAVA_FIXTURE))
