import { DataTable, PageHeader } from "@org/atlas";

export function InvoiceList() {
  return (
    <PageHeader title="Invoices">
      <DataTable rows={[]} columns={[{ key: "customerName", header: "Customer" }]} caption="Invoices" />
    </PageHeader>
  );
}
