import { Card, Stat } from "@org/atlas";

export interface InvoiceTotalsProps {
  total: string;
  currency: string;
  status: string;
}

export function InvoiceTotals(props: InvoiceTotalsProps) {
  return (
    <Card title="Totals">
      <div data-field="total">
        <Stat label="Total" value={props.total} unit={props.currency} />
      </div>
      <div data-field="status">
        <Stat label="Status" value={props.status} />
      </div>
    </Card>
  );
}
