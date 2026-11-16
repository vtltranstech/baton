// Merge into each Gradle service's build.gradle.kts. Copy checkstyle.xml and pmd-ruleset.xml to config/sensors/.
// `gradle build` then fails on a violation. PMD and Checkstyle write build/reports/{pmd,checkstyle}/main.xml.
// Proven by fixtures/sample-java-repo/variants/gradle-kts, which uses exactly these settings.
plugins {
    pmd
    checkstyle
    id("info.solidsoft.pitest") version "1.19.0"
}

dependencies {
    testImplementation("com.tngtech.archunit:archunit-junit5:1.4.1")
}

pmd {
    toolVersion = "7.17.0"
    ruleSets = emptyList()
    ruleSetFiles = files("config/sensors/pmd-ruleset.xml")
}

tasks.named("pmdTest") {
    enabled = false
}

checkstyle {
    toolVersion = "10.26.1"
    configFile = file("config/sensors/checkstyle.xml")
}

tasks.named("checkstyleTest") {
    enabled = false
}

// PIT is a confidence signal, not a gate: no mutationThreshold, and the task is not part of `build`.
pitest {
    pitestVersion = "1.30.1"
    junit5PluginVersion = "1.2.3"
    timestampedReports = false
    outputFormats = listOf("XML")
    excludedTestClasses = listOf("*ArchitectureTest")
    failWhenNoMutations = false
    // `baton mutation` passes the changed classes and the test packages here.
    targetClasses = providers.gradleProperty("batonTargetClasses")
        .map { it.split(",") }
        .orElse(listOf("${project.group}.*"))
    targetTests = providers.gradleProperty("batonTargetTests")
        .map { it.split(",") }
        .orElse(listOf("${project.group}.*"))
}
