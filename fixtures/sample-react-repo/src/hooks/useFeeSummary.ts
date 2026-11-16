import { useEffect, useState } from "react";
import { fetchFeeSummary } from "../api/feeClient";
import type { FeeSummary } from "../types/fee";

export function useFeeSummary(accountRef: string, periodKey: string): FeeSummary | null {
  const [summary, setSummary] = useState<FeeSummary | null>(null);
  useEffect(() => {
    fetchFeeSummary(accountRef, periodKey).then(setSummary);
  }, [accountRef, periodKey]);
  return summary;
}
