import { afterEach, expect, test, vi } from "vitest";
import { fetchItem } from "./itemClient";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("reads the item from the versioned path", async () => {
  const stub = vi.fn().mockResolvedValue(new Response(JSON.stringify({ itemKey: "k1", text: "hello" })));
  vi.stubGlobal("fetch", stub);
  await expect(fetchItem("k1")).resolves.toEqual({ itemKey: "k1", text: "hello" });
  expect(stub).toHaveBeenCalledWith("/api/v1/items/k1");
});

test("an error status is an error, not an empty item", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 404 })));
  await expect(fetchItem("nope")).rejects.toThrow("HTTP 404");
});
