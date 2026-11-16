"""Gradle version catalogs (gradle/libs.versions.toml): libs.* dependencies and alias(libs.plugins.*)."""

from __future__ import annotations

from baton.extract.repos import RepoRef, load_sources
from baton.extract.stack import detect_stack

CATALOG = """[versions]
springBoot = "4.0.7"
pitest = "1.19.0"

[libraries]
spring-kafka = { module = "org.springframework.kafka:spring-kafka", version = "4.0.0" }
mongo-starter = { module = "org.springframework.boot:spring-boot-starter-data-mongodb" }
archunit-junit5 = "com.tngtech.archunit:archunit-junit5:1.4.1"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "springBoot" }
pitest = { id = "info.solidsoft.pitest", version.ref = "pitest" }
"""
BUILD = """plugins {
    alias(libs.plugins.spring.boot) apply false
    alias(libs.plugins.pitest)
}
dependencies {
    implementation libs.spring.kafka
    implementation(libs.mongo.starter)
    testImplementation libs.archunit.junit5
}
"""


def test_catalog_resolves_versions_dependencies_and_plugins(tmp_path):
    repo = tmp_path / "svc"
    (repo / "gradle").mkdir(parents=True)
    (repo / "gradle" / "libs.versions.toml").write_text(CATALOG)
    (repo / "build.gradle").write_text(BUILD)
    row = detect_stack(load_sources(RepoRef("svc", repo)))
    assert row["springBoot"] == "4.0.7"
    assert row["messaging"] == "kafka" and row["datastore"] == "mongodb"
    assert row["archunit"] == "installed" and row["pitest"] == "installed"
    assert not any("version catalog" in p for p in row["problems"])
