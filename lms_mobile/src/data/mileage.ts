import { create } from 'zustand';
import type { MileageCartItem, MileageProduct, MileageSettings, MileageTransaction, PurchaseRequest } from '@web/domain/types';

import { http } from './http';
import { runCommand, useDb } from './query';

interface CartState {
  items: MileageCartItem[];
  add: (item: MileageCartItem) => void;
  remove: (productId: string) => void;
  clear: () => void;
}

/** 장바구니는 서버에 없다. 웹과 같이 이 기기 메모리에만 둔다. */
export const useCart = create<CartState>((set) => ({
  items: [],
  add: (item) =>
    set((state) => {
      const found = state.items.find((row) => row.productId === item.productId);
      if (!found) return { items: [...state.items, item] };
      return {
        items: state.items.map((row) =>
          row.productId === item.productId ? { ...row, quantity: row.quantity + item.quantity } : row,
        ),
      };
    }),
  remove: (productId) => set((state) => ({ items: state.items.filter((row) => row.productId !== productId) })),
  clear: () => set({ items: [] }),
}));

export function useProducts(): MileageProduct[] {
  return useDb()?.mileageProducts ?? [];
}

export function useTransactions(uid?: string): MileageTransaction[] {
  const rows = useDb()?.mileageTransactions ?? [];
  return uid === undefined ? rows : rows.filter((row) => row.userId === uid);
}

export function usePurchases(uid?: string): PurchaseRequest[] {
  const rows = useDb()?.purchaseRequests ?? [];
  return uid === undefined ? rows : rows.filter((row) => row.userId === uid);
}

export function useMileageSettings(): MileageSettings {
  return useDb()?.mileageSettings ?? { categoryLimits: {}, accrualRules: {} };
}

export async function saveProduct(product: MileageProduct, cohortId: string): Promise<void> {
  await runCommand('upsert', {
    table: 'mileage_products',
    id: product.id || undefined,
    cohortId,
    name: product.name,
    description: product.description,
    imageUrl: product.imageUrl,
    category: product.category,
    pricingType: product.pricingType,
    fixedPrice: product.fixedPrice ?? null,
    isActive: product.isActive,
    sortOrder: product.sortOrder,
  });
}

export async function deleteProduct(id: string): Promise<void> {
  await runCommand('upsert', { table: 'mileage_products', id, action: 'delete' });
}

export async function createPurchase(request: Omit<PurchaseRequest, 'id' | 'createdAt'>, cohortId: string): Promise<void> {
  await runCommand('savePurchaseRequest', {
    cohortId,
    items: request.items,
    totalAmount: request.totalAmount,
    status: request.status,
  });
}

export async function reviewPurchase(id: string, status: PurchaseRequest['status'], reviewComment?: string): Promise<void> {
  await runCommand('reviewPurchaseRequest', { id, status, managerMemo: reviewComment });
}

export async function adjustMileage(uid: string, amount: number, reason: string): Promise<void> {
  await http.post('/mileage/adjust', { uid, amount, reason });
  const { queryClient, queryKeys } = await import('./query');
  await queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
}

export async function saveMileageSettings(settings: MileageSettings, cohortId: string): Promise<void> {
  await runCommand('saveMileageSettings', { cohortId, ...settings });
}
