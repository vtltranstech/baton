// The API client module: the only place that calls the backend. Components read it through a data hook.
import type { Item } from "../types/item";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export async function fetchItem(itemKey: string): Promise<Item> {
  const response = await fetch(`${BASE_URL}/api/v1/items/${encodeURIComponent(itemKey)}`);
  if (!response.ok) {
    throw new Error(`item ${itemKey}: HTTP ${response.status}`);
  }
  return (await response.json()) as Item;
}
