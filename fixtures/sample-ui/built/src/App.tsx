import { Route, Routes } from "react-router-dom";
import { InvoiceList } from "./pages/InvoiceList";
import { InvoiceSummary } from "./pages/InvoiceSummary";

export function App() {
  return (
    <Routes>
      <Route path="/invoices" element={<InvoiceList />} />
      <Route path="/invoices/:invoiceId" element={<InvoiceSummary />} />
    </Routes>
  );
}
