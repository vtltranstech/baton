package com.example.sample;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noMethods;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

@AnalyzeClasses(packages = "com.example.sample", importOptions = ImportOption.DoNotIncludeTests.class)
class ProjectArchitectureTest {

    @ArchTest
    static final ArchRule singleFeeCalculation = noMethods()
        .that().haveName("calculateFee")
        .should().beDeclaredInClassesThat().doNotHaveFullyQualifiedName(
            "com.example.sample.application.service.FeeCalculator")
        .because("REMEDIATION: delete this implementation and call FeeCalculator, the one home of the fee rule");

    @ArchTest
    static final ArchRule thinBatchWriters = noClasses()
        .that().implement("org.springframework.batch.item.ItemWriter")
        .should().dependOnClassesThat().resideInAPackage("..service..")
        .allowEmptyShould(true)
        .because("REMEDIATION: move the decision into a processor or service; a writer only writes its chunk");

    @ArchTest
    static final ArchRule noRawDatastoreTypeInServices = noClasses()
        .that().resideInAPackage("..service..")
        .should().dependOnClassesThat().haveFullyQualifiedName("org.bson.Document")
        .because("REMEDIATION: use a typed @Document class behind a port; raw org.bson.Document stays out of services");
}
