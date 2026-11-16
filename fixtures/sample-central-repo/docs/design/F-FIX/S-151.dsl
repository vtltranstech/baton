workspace "S-151 candidate" {
    model {
        overdueJob = container "overdue-job" "Flags overdue invoices" "Spring Batch"
        notices = container "notices" "Notices sent" "MongoDB"
    }
}
