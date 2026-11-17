import { Route, Routes } from "react-router-dom";
import { InvoiceList } from "./pages/InvoiceList";

export function App() {
  return (
    <Routes>
      <Route path="/invoices" element={<InvoiceList />} />
    </Routes>
  );
}
