import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ItemCard } from "./ItemCard";

test("shows the key and the text of the item", () => {
  render(<ItemCard item={{ itemKey: "k1", text: "hello" }} />);
  expect(screen.getByRole("heading").textContent).toBe("k1");
  expect(screen.getByText("hello")).toBeTruthy();
});
