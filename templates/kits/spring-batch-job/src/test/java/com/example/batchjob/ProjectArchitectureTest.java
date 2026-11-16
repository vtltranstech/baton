// TEMPLATE. Copy to src/test/java/<root package>/ProjectArchitectureTest.java in the service repo (decision D5).
// Project rules are added only through `/standards record`, from an observed failure; profile/sensors/README.md
// records each rule, its repo and the incident. Uncomment an example only when that record exists.
// The three examples below run for real in fixtures/sample-java-repo, with planted violations that prove them.
package com.example.batchjob; // <root package>

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
// import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noMethods;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

@AnalyzeClasses(packages = "com.example.batchjob", importOptions = ImportOption.DoNotIncludeTests.class)
class ProjectArchitectureTest {

    // Example 1, single implementation of a named rule: only the named class may declare the rule's method.
    // @ArchTest
    // static final ArchRule singleImplementationOfNamedRule = noMethods()
    //     .that().haveName("calculateFee")
    //     .should().beDeclaredInClassesThat().doNotHaveFullyQualifiedName("com.example.batchjob.service.FeeCalculator")
    //     .because("REMEDIATION: delete this implementation and call FeeCalculator, the one home of the rule");

    // Example 2, thin batch writers: a writer writes its chunk and takes no business decision.
    // @ArchTest
    // static final ArchRule thinBatchWriters = noClasses()
    //     .that().implement("org.springframework.batch.item.ItemWriter")
    //     .should().dependOnClassesThat().resideInAPackage("..service..")
    //     .allowEmptyShould(true)
    //     .because("REMEDIATION: move the decision into a processor or service; a writer only writes its chunk");

    // Example 3, no raw datastore type in services.
    // @ArchTest
    // static final ArchRule noRawDatastoreTypeInServices = noClasses()
    //     .that().resideInAPackage("..service..")
    //     .should().dependOnClassesThat().haveFullyQualifiedName("org.bson.Document")
    //     .because("REMEDIATION: use a typed @Document class behind a port; raw org.bson.Document stays out of services");

    // Keeps the template compiling while every example is commented out. Delete it once a real rule exists.
    @ArchTest
    static final ArchRule placeholder = noClasses().should().dependOnClassesThat()
        .haveFullyQualifiedName("com.example.batchjob.NoSuchType")
        .allowEmptyShould(true)
        .because("REMEDIATION: placeholder, replace with a recorded project rule");
}
