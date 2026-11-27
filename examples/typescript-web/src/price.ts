export interface LineItem {
  unitPrice: number;
  quantity: number;
}

export function subtotal(items: LineItem[]): number {
  return items.reduce((sum, item) => sum + item.unitPrice * item.quantity, 0);
}

export function withTax(amount: number, rate: number): number {
  return Math.round(amount * (1 + rate) * 100) / 100;
}
