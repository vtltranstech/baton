// MANDATORY in every Java repo. Copy to src/test/java/<root package>/ArchitectureTest.java; set the package and BASE.
// Dependency: com.tngtech.archunit:archunit-junit5 (test scope), see pom-snippet.xml / build.gradle.kts.
// The same file serves Java 17 and Java 21: it uses no language feature above 17, and ArchUnit 1.4 reads both class formats.
// Runs with the normal build; a violation fails `mvn verify` / `gradle build`.
// Every rule's `because` starts with REMEDIATION: so the failure text in the surefire report says what to do.
package com.example.mongoservice; // <root package>

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.fields;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noFields;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noMethods;
import static com.tngtech.archunit.library.Architectures.layeredArchitecture;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;
import com.tngtech.archunit.library.GeneralCodingRules;

@AnalyzeClasses(packages = ArchitectureTest.BASE, importOptions = ImportOption.DoNotIncludeTests.class)
class ArchitectureTest {
    static final String BASE = "com.example.mongoservice"; // <root package>

    // stack.md: Controller -> Service -> Repository; nothing skips a layer, nothing points backwards
    @ArchTest
    static final ArchRule layers = layeredArchitecture().consideringOnlyDependenciesInLayers()
        .withOptionalLayers(true)
        .layer("Controller").definedBy("..controller..", "..api..")
        .layer("Service").definedBy("..service..", "..resolver..")
        .layer("Repository").definedBy("..repository..")
        .layer("Batch").definedBy("..batch..")
        .whereLayer("Controller").mayNotBeAccessedByAnyLayer()
        .whereLayer("Service").mayOnlyBeAccessedByLayers("Controller", "Batch")
        .whereLayer("Repository").mayOnlyBeAccessedByLayers("Service", "Batch")
        .because("REMEDIATION: route the call Controller -> Service -> Repository; never skip a layer or point backwards");

    // stack.md: persistence documents/entities never cross the API boundary
    @ArchTest
    static final ArchRule noDocumentsInControllers = noClasses().that().resideInAnyPackage("..controller..", "..api..")
        .should().dependOnClassesThat().resideInAnyPackage("..document..", "..entity..")
        .allowEmptyShould(true)
        .because("REMEDIATION: map the persistence type to a DTO record at the boundary");

    // stack.md: constructor injection only
    @ArchTest
    static final ArchRule noFieldInjection = noFields()
        .should().beAnnotatedWith("org.springframework.beans.factory.annotation.Autowired")
        .allowEmptyShould(true)
        .because("REMEDIATION: remove @Autowired from the field; take the dependency as a final field set in the constructor");

    // no dependency cycles between feature slices
    @ArchTest
    static final ArchRule noCycles = slices().matching(BASE + ".(*)..").should().beFreeOfCycles()
        .allowEmptyShould(true)
        .because("REMEDIATION: break the cycle by moving the shared type down or depending on a port");

    // constructor injection only, whichever annotation is used
    @ArchTest
    static final ArchRule noOtherFieldInjection = noFields()
        .should().beAnnotatedWith("jakarta.inject.Inject")
        .orShould().beAnnotatedWith("jakarta.annotation.Resource")
        .allowEmptyShould(true)
        .because("REMEDIATION: remove the annotation from the field; take the dependency as a final field set in the constructor");

    // stereotypes live in their layer, or the layer rules above never see them
    @ArchTest
    static final ArchRule controllersLiveInTheWebLayer = classes()
        .that().areAnnotatedWith("org.springframework.web.bind.annotation.RestController")
        .or().areAnnotatedWith("org.springframework.stereotype.Controller")
        .should().resideInAnyPackage("..controller..", "..api..").andShould().haveSimpleNameEndingWith("Controller")
        .allowEmptyShould(true)
        .because("REMEDIATION: move the class under ..controller.. or ..api.. and name it <Thing>Controller");

    @ArchTest
    static final ArchRule servicesLiveInTheServiceLayer = classes()
        .that().areAnnotatedWith("org.springframework.stereotype.Service")
        .should().resideInAnyPackage("..service..", "..resolver..")
        .allowEmptyShould(true)
        .because("REMEDIATION: move the class under ..service.., or drop @Service if it is not one");

    @ArchTest
    static final ArchRule repositoriesLiveInTheRepositoryLayer = classes()
        .that().areAnnotatedWith("org.springframework.stereotype.Repository")
        .should().resideInAPackage("..repository..")
        .allowEmptyShould(true)
        .because("REMEDIATION: move the class under ..repository..");

    // the service layer knows nothing about HTTP
    @ArchTest
    static final ArchRule servicesDoNotKnowHttp = noClasses().that().resideInAnyPackage("..service..", "..resolver..")
        .should().dependOnClassesThat().resideInAnyPackage("org.springframework.web..", "org.springframework.http..", "jakarta.servlet..")
        .allowEmptyShould(true)
        .because("REMEDIATION: throw a domain exception and return a plain type; the controller maps them to HTTP");

    // a controller reaches data only through a service
    @ArchTest
    static final ArchRule controllersDoNotTouchTheDatastore = noClasses().that().resideInAnyPackage("..controller..", "..api..")
        .should().dependOnClassesThat().resideInAnyPackage("org.springframework.data..", "org.bson..", "com.mongodb..", "jakarta.persistence..")
        .allowEmptyShould(true)
        .because("REMEDIATION: move the data access behind a service and a repository");

    // a transaction belongs to a business operation
    @ArchTest
    static final ArchRule noTransactionsInControllers = noMethods()
        .that().areDeclaredInClassesThat().resideInAnyPackage("..controller..", "..api..")
        .should().beAnnotatedWith("org.springframework.transaction.annotation.Transactional")
        .allowEmptyShould(true)
        .because("REMEDIATION: put @Transactional on the service method that owns the operation");

    // the domain points at nothing above it
    @ArchTest
    static final ArchRule domainStaysAtTheBottom = noClasses().that().resideInAPackage("..domain..")
        .should().dependOnClassesThat().resideInAnyPackage("..controller..", "..api..", "..service..", "..repository..", "..batch..")
        .allowEmptyShould(true)
        .because("REMEDIATION: move the logic up into a service, or the shared type down into the domain");

    // money is never floating point
    @ArchTest
    static final ArchRule moneyIsNotFloatingPoint = noFields()
        .that().haveNameMatching("(?i).*(amount|fee|price|balance|interest|principal|charge).*")
        .should().haveRawType(double.class).orShould().haveRawType(float.class)
        .orShould().haveRawType(Double.class).orShould().haveRawType(Float.class)
        .allowEmptyShould(true)
        .because("REMEDIATION: use BigDecimal for money; a double cannot hold a decimal amount exactly");

    @ArchTest
    static final ArchRule loggersArePrivateStaticFinal = fields()
        .that().haveRawType("org.slf4j.Logger")
        .should().bePrivate().andShould().beStatic().andShould().beFinal()
        .allowEmptyShould(true)
        .because("REMEDIATION: declare it private static final Logger log = LoggerFactory.getLogger(ThisClass.class)");

    @ArchTest
    static final ArchRule noStandardStreams = noClasses().should(GeneralCodingRules.ACCESS_STANDARD_STREAMS)
        .because("REMEDIATION: use the SLF4J logger; System.out and printStackTrace bypass log masking and levels");

    @ArchTest
    static final ArchRule noGenericExceptions = noClasses().should(GeneralCodingRules.THROW_GENERIC_EXCEPTIONS)
        .because("REMEDIATION: throw a specific exception that names the failure");

    @ArchTest
    static final ArchRule noJavaUtilLogging = noClasses().should(GeneralCodingRules.USE_JAVA_UTIL_LOGGING)
        .because("REMEDIATION: use SLF4J");

    @ArchTest
    static final ArchRule noJodaTime = noClasses().should(GeneralCodingRules.USE_JODATIME)
        .because("REMEDIATION: use java.time");
}
