plugins {
    java
    pmd
    checkstyle
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
    id("info.solidsoft.pitest") version "1.19.0"
}

group = "com.example.samplegradle"
version = "0.0.1"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-mongodb")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
    testImplementation("com.tngtech.archunit:archunit-junit5:1.4.1")
}

tasks.withType<Test> {
    useJUnitPlatform()
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
