import { ActionBar, DataTable, PageHeader, StatePanel } from "@org/atlas";
import { InvoiceTotals } from "../components/InvoiceTotals";
import { useInvoice } from "./useInvoice";

export function InvoiceSummary() {
  const { invoice, state, retry, send } = useInvoice();
  if (state !== "ready") {
    return (
      <>
        <div data-state="loading" hidden={state !== "loading"}><StatePanel state="loading" /></div>
        <div data-state="empty" hidden={state !== "empty"}><StatePanel state="empty" message="No lines for this period" /></div>
        <div data-state="error" hidden={state !== "error"}><StatePanel state="error" onRetry={retry} /></div>
        <div data-state="no-permission" hidden={state !== "no-permission"}><StatePanel state="no-permission" /></div>
      </>
    );
  }
  return (
    <PageHeader title="Invoice">
      <span data-field="customerName">Customer: {invoice.customerName}</span>
      <span data-field="billingPeriod">Billing period: {invoice.billingPeriod}</span>
      <InvoiceTotals total={invoice.total} currency={invoice.currency} status={invoice.status} />
      <div data-state="partial" hidden={!invoice.unresolved}>Unresolved lines are flagged</div>
      <DataTable
        caption="Invoice lines"
        rows={invoice.lines}
        columns={[
          { key: "description", header: "Description" },
          { key: "amount", header: "Amount" },
        ]}
      />
      <span data-field="description" hidden />
      <span data-field="amount" hidden />
      <ActionBar actions={[{ name: "send", label: "Send" }]} onAction={send} />
      <button type="button" data-action="send" hidden>Send</button>
    </PageHeader>
  );
}
