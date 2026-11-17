import type { ReactNode } from "react";

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  children?: ReactNode;
}

export function PageHeader(props: PageHeaderProps) {
  return <header aria-label={props.title}>{props.children}</header>;
}
