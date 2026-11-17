import type { ReactNode } from "react";

export interface CardProps {
  title: string;
  children?: ReactNode;
}

export default function Card({ title, children }: CardProps) {
  return <section aria-label={title}>{children}</section>;
}

export { Card };
