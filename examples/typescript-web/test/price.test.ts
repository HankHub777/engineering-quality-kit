import { test } from "node:test";
import assert from "node:assert/strict";
import { subtotal, withTax } from "../src/price.ts";

test("subtotal", () => {
  assert.equal(subtotal([{ unitPrice: 2, quantity: 3 }, { unitPrice: 1.5, quantity: 2 }]), 9);
});

test("withTax rounds to cents", () => {
  assert.equal(withTax(10, 0.05), 10.5);
});
