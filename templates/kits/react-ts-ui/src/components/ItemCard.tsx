// Renders only: typed props in, markup out. No fetch, no data hook.
import type { Item } from "../types/item";

export interface ItemCardProps {
  item: Item;
}

export function ItemCard({ item }: ItemCardProps) {
  return (
    <section aria-label={`item ${item.itemKey}`}>
      <h2>{item.itemKey}</h2>
      <p>{item.text}</p>
    </section>
  );
}
