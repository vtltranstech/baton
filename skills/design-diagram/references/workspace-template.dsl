// docs/architecture/workspace.dsl - the project's C4 model of record.
// Written by /onboard from profile/project.md (repos), the codebase map (components) and
// profile/domain.md (external systems). Promoted by the documentation agent after each Approved story.
// Identifiers are lowerCamel of the codebase-map names and are never renamed once published.
workspace "<project name>" "<one-liner from profile/project.md>" {

    model {
        user = person "<primary persona from profile/project.md>" "Uses the product"

        // one softwareSystem per external / legacy system named in profile/domain.md
        legacySystem = softwareSystem "<Legacy system>" "<what it masters>" {
            tags "External"
        }

        product = softwareSystem "<project name>" "<one-liner>" {
            // one container per repo in the profile's repo table
            ui = container "<ui repo>" "<purpose>" "React"
            apiService = container "<service repo>" "<purpose>" "Spring Boot" {
                // components only for what the codebase map lists
                clientController = component "ClientController" "<path prefix>" "Spring @RestController"
                clientService = component "ClientService" "<responsibility>" "Spring @Service"
                clientRepository = component "ClientRepository" "<collection>" "Spring Data"
            }
            batchLoader = container "<batch repo>" "<purpose>" "Spring Batch" {
                nightlyJob = component "NightlyLoadJob" "<reader -> processor -> writer>" "Spring Batch Job"
            }
            db = container "<datastore>" "<collections or schemas>" "MongoDB" {
                tags "Database"
            }
        }

        // relationships: data that flows, then technology
        user -> ui "selects a client"
        ui -> apiService "clientId" "REST/JSON"
        clientController -> clientService "clientId, periodKey"
        clientService -> clientRepository "query by clientId, periodKey"
        clientRepository -> db "reads <collection>" "Mongo"
        batchLoader -> db "writes <collection> per periodKey" "Mongo"
        legacySystem -> batchLoader "nightly extract" "file"
    }

    views {
        systemContext product "Context" {
            include *
            autoLayout lr
        }
        container product "Containers" {
            include *
            autoLayout lr
        }
        component apiService "ApiComponents" {
            include *
            autoLayout lr
        }
        // per-story dynamic views are added by the architect's delta, named by story id:
        // dynamic apiService "S-010" "..." { ui -> clientController "..."  ... autoLayout lr }
        // (a dynamic view's steps may not use its own scope: inside apiService, name its components)

        styles {
            element "External" {
                background #9aa3b2
                color #ffffff
            }
            element "Database" {
                shape Cylinder
            }
            element "New" {
                background #1f5fa8
                color #ffffff
            }
            element "Changed" {
                background #d9731a
                color #ffffff
            }
        }
    }
}
