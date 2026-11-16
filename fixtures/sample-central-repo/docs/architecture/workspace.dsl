workspace "Sample Product" "Records invoices and their payments" {
    model {
        clerk = person "Billing Clerk" "Uses the product"
        product = softwareSystem "Sample Product" "Records invoices" {
            invoiceService = container "invoice-service" "Invoice APIs" "Spring Boot"
            db = container "datastore" "invoices" "MongoDB"
            overdueJob = container "overdue-job" "Flags overdue invoices" "Spring Batch" {
                tags "F-FIX"
                properties {
                    "baton.story" "S-151"
                    "baton.feature" "F-FIX"
                    "baton.since" "2026-11-05"
                }
            }
            notices = container "notices" "Notices sent" "MongoDB" {
                tags "F-FIX"
                properties {
                    "baton.story" "S-151"
                    "baton.feature" "F-FIX"
                    "baton.since" "2026-11-05"
                }
            }
        }
        clerk -> invoiceService "invoice id" "REST/JSON"
        invoiceService -> db "reads invoices" "Mongo"
        overdueJob -> db "reads invoices" "Mongo" {
            tags "F-FIX"
            properties {
                "baton.story" "S-151"
                "baton.feature" "F-FIX"
                "baton.since" "2026-11-05"
            }
        }
        overdueJob -> notices "writes notices" "Mongo" {
            tags "F-FIX"
            properties {
                "baton.story" "S-151"
                "baton.feature" "F-FIX"
                "baton.since" "2026-11-05"
            }
        }
        clerk -> notices "reads notices" "REST/JSON" {
            tags "F-FIX"
            properties {
                "baton.story" "S-151"
                "baton.feature" "F-FIX"
                "baton.since" "2026-11-05"
            }
        }
    }
    views {
        container product "Containers" {
            include *
            autoLayout lr
        }
    }
}
