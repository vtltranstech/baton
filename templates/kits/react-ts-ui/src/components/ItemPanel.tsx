// Reads the data through its hook and hands it to the card.
import { useItem } from "../hooks/useItem";
import { ItemCard } from "./ItemCard";

export interface ItemPanelProps {
  itemKey: string;
}

export function ItemPanel({ itemKey }: ItemPanelProps) {
  const item = useItem(itemKey);
  if (item.isPending) {
    return <p>Loading</p>;
  }
  if (item.isError) {
    return <p role="alert">{item.error.message}</p>;
  }
  return <ItemCard item={item.data} />;
}
