import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

import type { MileageCartItem } from '../../domain/types';

/**
 * 장바구니 — Flutter `mileageCartProvider` 자리.
 *
 * 화면을 옮겨 다니는 동안만 살아 있으면 된다. 저장소에 넣지 않는다.
 */
interface Cart {
  items: MileageCartItem[];
  add(item: MileageCartItem): void;
  remove(productId: string): void;
  setQuantity(productId: string, quantity: number): void;
  clear(): void;
}

const CartContext = createContext<Cart | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<MileageCartItem[]>([]);

  const add = useCallback((item: MileageCartItem) => {
    setItems((current) => {
      const existing = current.find((i) => i.productId === item.productId);
      if (existing === undefined) return [...current, item];
      return current.map((i) =>
        i.productId === item.productId ? { ...i, quantity: i.quantity + item.quantity } : i,
      );
    });
  }, []);

  const remove = useCallback((productId: string) => {
    setItems((current) => current.filter((i) => i.productId !== productId));
  }, []);

  const setQuantity = useCallback((productId: string, quantity: number) => {
    setItems((current) =>
      current.map((i) => (i.productId === productId ? { ...i, quantity } : i)),
    );
  }, []);

  const clear = useCallback(() => setItems([]), []);

  const value = useMemo<Cart>(
    () => ({ items, add, remove, setQuantity, clear }),
    [items, add, remove, setQuantity, clear],
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): Cart {
  const cart = useContext(CartContext);
  if (cart === null) throw new Error('CartProvider 밖에서 useCart를 불렀다');
  return cart;
}
