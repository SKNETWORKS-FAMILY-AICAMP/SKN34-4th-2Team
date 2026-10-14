import type { ReactNode } from 'react';
import { create } from 'zustand';

import type { MileageCartItem } from '../../domain/types';

interface Cart {
  items: MileageCartItem[];
  add(item: MileageCartItem): void;
  remove(productId: string): void;
  setQuantity(productId: string, quantity: number): void;
  clear(): void;
}

export const useCart = create<Cart>((set) => ({
  items: [],
  add: (item) =>
    set((current) => {
      const existing = current.items.find((i) => i.productId === item.productId);
      if (existing === undefined) return { items: [...current.items, item] };
      return {
        items: current.items.map((i) =>
          i.productId === item.productId ? { ...i, quantity: i.quantity + item.quantity } : i,
        ),
      };
    }),
  remove: (productId) => set((current) => ({ items: current.items.filter((i) => i.productId !== productId) })),
  setQuantity: (productId, quantity) =>
    set((current) => ({
      items: current.items.map((i) => (i.productId === productId ? { ...i, quantity } : i)),
    })),
  clear: () => set({ items: [] }),
}));

export function CartProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
