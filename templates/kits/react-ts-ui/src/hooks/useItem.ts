// Server state through the query client; a selection changes the query key, not a prop chain.
import { useQuery } from "@tanstack/react-query";
import { fetchItem } from "../api/itemClient";
import type { Item } from "../types/item";

export function useItem(itemKey: string) {
  return useQuery<Item, Error>({
    queryKey: ["item", itemKey],
    queryFn: () => fetchItem(itemKey),
  });
}
