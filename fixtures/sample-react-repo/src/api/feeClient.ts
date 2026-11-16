import type { FeeSummary } from "../types/fee";

export async function fetchFeeSummary(accountRef: string, periodKey: string): Promise<FeeSummary> {
  const response = await fetch(`/api/v1/fees/${accountRef}?periodKey=${periodKey}`);
  return (await response.json()) as FeeSummary;
}
