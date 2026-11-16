import { useFeeSummary } from "../hooks/useFeeSummary";

interface FeeSummaryCardProps {
  accountRef: string;
  periodKey: string;
}

export function FeeSummaryCard({ accountRef, periodKey }: FeeSummaryCardProps) {
  const summary = useFeeSummary(accountRef, periodKey);
  if (summary === null) {
    return <p>Loading</p>;
  }
  return <p>{summary.total}</p>;
}
