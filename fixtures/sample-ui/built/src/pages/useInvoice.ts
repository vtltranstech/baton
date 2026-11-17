export function useInvoice() {
  return {
    invoice: {
      customerName: "", billingPeriod: "", total: "", currency: "", status: "", unresolved: false, lines: [],
    },
    state: "ready",
    retry: () => undefined,
    send: () => undefined,
  };
}
