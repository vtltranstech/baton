import type { FC } from "react";

export interface StatProps {
  label: string;
  value: string;
  unit?: string;
}
export declare const Stat: FC<StatProps>;

export interface ActionBarProps {
  actions: { name: string; label: string }[];
  onAction: (name: string) => void;
}
export declare function ActionBar(props: ActionBarProps): JSX.Element;
