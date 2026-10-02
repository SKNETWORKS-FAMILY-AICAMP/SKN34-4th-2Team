import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Image, Modal, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import {
  MileageCategories,
  MileageCategoryLabels,
  MileageDefaultLimits,
  PurchaseRequestStatusLabels,
} from '@web/domain/constants';
import type { MileageCartItem, MileageProduct, PurchaseRequest } from '@web/domain/types';

import { useSession } from '../auth/session';
import { absoluteFileUrl } from '../data/http';
import { createPurchase, useCart, useMileageSettings, useProducts, usePurchases } from '../data/mileage';
import { queryClient, queryKeys } from '../data/query';
import { useTheme } from '../theme/Theme';
import { Badge, Btn, Callout, Card, Chip, EmptyState, Field, SectionHeader, Screen, T, fmt } from '../ui/kit';

const won = (value: number) => `${value.toLocaleString('ko-KR')}M`;

function refresh() {
  void queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
}

interface CategoryUsage {
  category: string;
  limit: number;
  approved: number;
  pending: number;
  modifyRequested: number;
  remaining: number;
}

/** 카테고리별 한도 사용량 — 승인 · 대기 · 수정 요청이 한도를 깎는다(반려 · 취소는 빼지 않는다) */
function categoryUsage(requests: PurchaseRequest[], limits: Record<string, number>): CategoryUsage[] {
  return MileageCategories.map((category) => {
    const limit = limits[category] ?? MileageDefaultLimits[category] ?? 0;
    const sum = (status: string) =>
      requests
        .filter((r) => String(r.status) === status)
        .flatMap((r) => r.items)
        .filter((i) => i.category === category)
        .reduce((s, i) => s + i.unitPrice * i.quantity, 0);
    const approved = sum('approved');
    const pending = sum('pending');
    const modifyRequested = sum('modify_requested');
    return {
      category,
      limit,
      approved,
      pending,
      modifyRequested,
      remaining: Math.min(Math.max(limit - approved - pending - modifyRequested, 0), limit),
    };
  });
}

function BalanceCard({ balance, name }: { balance: number; name?: string }) {
  const { palette } = useTheme();
  return (
    <View style={[styles.balance, { backgroundColor: palette.primary }]}>
      <T variant="caption" style={{ color: 'rgba(255,255,255,0.85)', fontWeight: '600' }}>보유 마일리지</T>
      <T variant="hero" style={{ color: '#fff' }}>{won(balance)}</T>
      {name ? <T variant="caption" style={{ color: 'rgba(255,255,255,0.75)' }}>{name}</T> : null}
    </View>
  );
}

function CartButton({ count }: { count: number }) {
  const { palette } = useTheme();
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={`장바구니 ${count}개`} onPress={() => router.push('/(student)/cart' as never)} hitSlop={8}>
      <MaterialIcons name="shopping-cart" size={24} color={palette.text} />
      {count > 0 ? (
        <View style={[styles.dot, { backgroundColor: palette.error }]}>
          <T variant="caption" style={{ color: '#fff', fontSize: 10, fontWeight: '700' }}>{count}</T>
        </View>
      ) : null}
    </Pressable>
  );
}

// ── 교환소 ────────────────────────────────────────

export function ShopPage() {
  const { user } = useSession();
  const { palette } = useTheme();
  const products = useProducts().filter((p) => p.isActive);
  const settings = useMileageSettings();
  const myRequests = usePurchases(user?.uid);
  const items = useCart((state) => state.items);
  const add = useCart((state) => state.add);
  const [category, setCategory] = useState('all');
  const [sort, setSort] = useState<'default' | 'high' | 'low'>('default');
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<MileageProduct | undefined>(undefined);
  const [flash, setFlash] = useState<string | null>(null);

  const usages = categoryUsage(myRequests, settings.categoryLimits);
  const usageOf = (c: string) => usages.find((u) => u.category === c);
  const text = query.trim().toLowerCase();
  const filtered = products.filter((p) => (category === 'all' || p.category === category) && (text === '' || p.name.toLowerCase().includes(text)));
  const priceOf = (p: MileageProduct) => (p.pricingType === 'custom' ? 0 : p.fixedPrice ?? 0);
  const sorted =
    sort === 'default' ? filtered : [...filtered].sort((a, b) => (sort === 'high' ? priceOf(b) - priceOf(a) : priceOf(a) - priceOf(b)));

  return (
    <Screen title="마일리지 교환소" right={<CartButton count={items.length} />} onRefresh={refresh}>
      <T tone="secondary">상품을 선택해 장바구니에 담으세요.</T>
      <BalanceCard balance={user?.mileageBalance ?? 0} name={user?.displayName} />
      {flash ? (
        <Callout tone="success">
          <T>{flash}</T>
          <T variant="caption" tone="primary" style={{ fontWeight: '700', marginTop: 4 }} onPress={() => router.push('/(student)/cart' as never)}>
            장바구니 보기 ›
          </T>
        </Callout>
      ) : null}

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
        {usages.map((u) => (
          <Card key={u.category} style={{ width: 200, gap: 2 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <T variant="subtitle" style={{ flex: 1 }}>{MileageCategoryLabels[u.category] ?? u.category}</T>
              <T variant="caption" tone="hint">한도 {won(u.limit)}</T>
            </View>
            <T variant="title" tone="primary">{won(u.remaining)}</T>
            <T variant="caption" tone="secondary">추가 신청 가능</T>
            <T variant="caption" tone="hint">승인 {won(u.approved)} · 대기 {won(u.pending)} · 수정요청 {won(u.modifyRequested)}</T>
          </Card>
        ))}
      </ScrollView>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        <Chip label={`전체 ${products.length}`} selected={category === 'all'} onPress={() => setCategory('all')} />
        {Object.entries(MileageCategoryLabels).map(([id, label]) => (
          <Chip key={id} label={`${label} ${products.filter((p) => p.category === id).length}`} selected={category === id} onPress={() => setCategory(id)} />
        ))}
      </ScrollView>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        {([
          ['default', '기본'],
          ['high', '높은 순'],
          ['low', '낮은 순'],
        ] as const).map(([id, label]) => (
          <Chip key={id} label={label} selected={sort === id} onPress={() => setSort(id)} />
        ))}
      </View>
      <View style={[styles.search, { borderColor: palette.border, backgroundColor: palette.surface }]}>
        <MaterialIcons name="search" size={20} color={palette.textHint} />
        <TextInput
          accessibilityLabel="상품 검색"
          value={query}
          onChangeText={setQuery}
          placeholder="상품 검색"
          placeholderTextColor={palette.textHint}
          style={{ flex: 1, fontSize: 16, paddingVertical: 8, color: palette.text }}
        />
      </View>

      {sorted.length === 0 ? (
        <Card><EmptyState icon="card-giftcard" text="등록된 상품이 없습니다. 관리자에게 문의해 주세요." /></Card>
      ) : (
        <View style={styles.grid}>
          {sorted.map((product) => (
            <ProductCard key={product.id} product={product} remaining={usageOf(product.category)?.remaining} onPick={() => setPicked(product)} />
          ))}
        </View>
      )}

      {picked ? (
        <AddToCartSheet
          product={picked}
          usage={usageOf(picked.category)}
          balance={user?.mileageBalance ?? 0}
          onClose={() => setPicked(undefined)}
          onAdd={(item) => {
            add(item);
            setPicked(undefined);
            setFlash(`「${item.productName}」을(를) 장바구니에 담았습니다.`);
          }}
        />
      ) : null}
    </Screen>
  );
}

function ProductCard({ product, remaining, onPick }: { product: MileageProduct; remaining?: number; onPick: () => void }) {
  const { palette } = useTheme();
  const custom = product.pricingType === 'custom';
  return (
    <View style={styles.cell}>
      <Card onPress={onPick} style={{ gap: 6, padding: 12 }}>
        <Badge label={MileageCategoryLabels[product.category] ?? product.category} tone="neutral" />
        <View style={[styles.image, { backgroundColor: palette.surfaceVariant }]}>
          {product.imageUrl ? (
            <Image source={{ uri: absoluteFileUrl(product.imageUrl) }} style={StyleSheet.absoluteFill} resizeMode="cover" />
          ) : (
            <MaterialIcons name="card-giftcard" size={32} color={palette.textHint} />
          )}
        </View>
        <T variant="subtitle" numberOfLines={2}>{product.name}</T>
        <T tone="primary" style={{ fontWeight: '700' }}>{custom ? '가격 직접 입력' : won(product.fixedPrice ?? 0)}</T>
        {remaining !== undefined ? <T variant="caption" tone="hint">잔여 {won(remaining)}</T> : null}
      </Card>
    </View>
  );
}

/** 정가 상품은 수량만, 가격 직접 입력 상품은 링크와 가격을 받는다. 가격은 잔여 한도와 잔액을 넘을 수 없다 */
function AddToCartSheet({
  product,
  usage,
  balance,
  onAdd,
  onClose,
}: {
  product: MileageProduct;
  usage?: CategoryUsage;
  balance: number;
  onAdd: (item: MileageCartItem) => void;
  onClose: () => void;
}) {
  const { palette } = useTheme();
  const custom = product.pricingType === 'custom';
  const [quantity, setQuantity] = useState(1);
  const [link, setLink] = useState('');
  const [price, setPrice] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    if (!custom) {
      onAdd({ productId: product.id, productName: product.name, category: product.category, pricingType: product.pricingType, unitPrice: product.fixedPrice ?? 0, quantity });
      return;
    }
    const value = Number(price.trim());
    if (link.trim() === '') return setError('링크를 입력해 주세요.');
    if (!link.trim().startsWith('http')) return setError('올바른 URL을 입력해 주세요.');
    if (!Number.isFinite(value) || value <= 0) return setError('올바른 가격을 입력해 주세요.');
    if (usage !== undefined && value > usage.remaining) return setError('카테고리 잔여 한도를 초과합니다.');
    if (value > balance) return setError('마일리지 잔액이 부족합니다.');
    onAdd({
      productId: product.id,
      productName: product.name,
      category: product.category,
      pricingType: product.pricingType,
      unitPrice: value,
      quantity: 1,
      purchaseLink: link.trim(),
    });
  };

  return (
    <Modal transparent animationType="fade" statusBarTranslucent onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={[styles.sheet, { backgroundColor: palette.surface }]} onPress={() => undefined}>
          <T variant="title">{product.name}</T>
          {product.description ? <T tone="secondary">{product.description}</T> : null}
          {usage ? (
            <Callout tone="info">
              <T>{MileageCategoryLabels[product.category] ?? product.category} 잔여 한도: {won(usage.remaining)} / {won(usage.limit)}</T>
            </Callout>
          ) : null}
          {custom ? (
            <>
              <Field
                label={product.category === 'onlineCourse' ? '강의 링크' : '도서 링크'}
                value={link}
                onChangeText={setLink}
                placeholder={product.category === 'onlineCourse' ? 'https://www.inflearn.com/course/...' : 'https://www.yes24.com/...'}
                keyboard="url"
              />
              <Field label="가격 (M)" value={price} onChangeText={(v) => setPrice(v.replace(/[^\d]/g, ''))} placeholder="예) 66000" keyboard="numeric" />
            </>
          ) : (
            <View style={{ gap: 8 }}>
              <T variant="title" tone="primary">{won(product.fixedPrice ?? 0)}</T>
              <QuantityStepper value={quantity} onChange={setQuantity} />
            </View>
          )}
          {error ? <T tone="error">{error}</T> : null}
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ flex: 1 }}><Btn label="취소" tone="ghost" onPress={onClose} /></View>
            <View style={{ flex: 1 }}><Btn label="장바구니에 담기" onPress={submit} /></View>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function QuantityStepper({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  const { palette } = useTheme();
  const step = (delta: number) => onChange(Math.max(1, value + delta));
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
      <Pressable accessibilityLabel="수량 줄이기" disabled={value <= 1} onPress={() => step(-1)} style={[styles.step, { borderColor: palette.border, opacity: value <= 1 ? 0.35 : 1 }]}>
        <MaterialIcons name="remove" size={18} color={palette.text} />
      </Pressable>
      <T variant="subtitle" style={{ minWidth: 32, textAlign: 'center' }}>{value}</T>
      <Pressable accessibilityLabel="수량 늘리기" onPress={() => step(1)} style={[styles.step, { borderColor: palette.border }]}>
        <MaterialIcons name="add" size={18} color={palette.text} />
      </Pressable>
    </View>
  );
}

// ── 장바구니 ───────────────────────────────────────

export function CartPage() {
  const { user } = useSession();
  const { palette } = useTheme();
  const items = useCart((state) => state.items);
  const remove = useCart((state) => state.remove);
  const setQuantity = useCart((state) => state.setQuantity);
  const clear = useCart((state) => state.clear);
  const requests = usePurchases(user?.uid);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const balance = user?.mileageBalance ?? 0;
  const total = items.reduce((sum, item) => sum + item.unitPrice * item.quantity, 0);
  const enough = total <= balance;

  const submit = () => {
    if (!user) return;
    Alert.alert('구매 신청', `${won(total)} 을(를) 신청할까요? 관리자 승인 후 마일리지가 차감됩니다.`, [
      { text: '닫기', style: 'cancel' },
      {
        text: '신청',
        onPress: () => {
          setBusy(true);
          void createPurchase({ userId: user.uid, userDisplayName: user.displayName, items, totalAmount: total, status: 'pending' }, user.cohortId)
            .then(() => {
              clear();
              setMessage({ tone: 'success', text: '구매를 신청했습니다. 관리자 승인 후 마일리지가 차감됩니다.' });
            })
            .catch((error: unknown) => setMessage({ tone: 'error', text: error instanceof Error ? error.message : '신청하지 못했습니다.' }))
            .finally(() => setBusy(false));
        },
      },
    ]);
  };

  return (
    <Screen title="장바구니" onRefresh={refresh}>
      <T tone="secondary">신청하면 관리자 승인 후 마일리지가 차감됩니다.</T>
      {message ? <Callout tone={message.tone}><T>{message.text}</T></Callout> : null}

      {items.length === 0 ? (
        <Card style={{ alignItems: 'center' }}>
          <EmptyState icon="shopping-cart" text="장바구니가 비었습니다" />
          <Btn label="상품 보러 가기" tone="ghost" onPress={() => router.push('/(student)/shop' as never)} />
        </Card>
      ) : (
        <>
          {items.map((item) => (
            <Card key={item.productId} style={{ gap: 8 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <T variant="subtitle" style={{ flex: 1 }}>{item.productName}</T>
                <Pressable accessibilityLabel={`${item.productName} 삭제`} onPress={() => remove(item.productId)} hitSlop={8}>
                  <MaterialIcons name="delete-outline" size={22} color={palette.textSecondary} />
                </Pressable>
              </View>
              <T variant="caption" tone="secondary">{MileageCategoryLabels[item.category] ?? item.category} · 단가 {won(item.unitPrice)}</T>
              {item.purchaseLink ? <T variant="caption" tone="primary" numberOfLines={1}>{item.purchaseLink}</T> : null}
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                {item.pricingType === 'custom' ? (
                  <T variant="caption" tone="hint" style={{ flex: 1 }}>수량 1</T>
                ) : (
                  <View style={{ flex: 1 }}>
                    <QuantityStepper value={item.quantity} onChange={(value) => setQuantity(item.productId, value)} />
                  </View>
                )}
                <T variant="subtitle">{won(item.unitPrice * item.quantity)}</T>
              </View>
            </Card>
          ))}

          <Card style={{ gap: 8 }}>
            <View style={{ flexDirection: 'row' }}>
              <T style={{ flex: 1 }}>보유 마일리지</T>
              <T variant="subtitle">{won(balance)}</T>
            </View>
            <View style={{ flexDirection: 'row' }}>
              <T style={{ flex: 1 }}>신청 합계</T>
              <T variant="subtitle" tone={enough ? 'default' : 'error'}>{won(total)}</T>
            </View>
            {!enough ? <T tone="error">보유 마일리지가 부족합니다.</T> : null}
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 4 }}>
              <View style={{ flex: 1 }}><Btn label="비우기" tone="ghost" onPress={clear} /></View>
              <View style={{ flex: 1 }}><Btn label={busy ? '신청 중…' : '구매 신청'} disabled={!enough || busy} onPress={submit} /></View>
            </View>
          </Card>
        </>
      )}

      <SectionHeader title={`내 구매 요청 ${requests.length}건`} />
      {requests.length === 0 ? (
        <Card><EmptyState icon="receipt-long" text="구매 요청이 없습니다" /></Card>
      ) : (
        requests.map((request) => <PurchaseRequestCard key={request.id} request={request} />)
      )}
    </Screen>
  );
}

function PurchaseRequestCard({ request }: { request: PurchaseRequest }) {
  const qty = request.items.reduce((sum, i) => sum + i.quantity, 0);
  const tone = request.status === 'approved' ? 'success' : request.status === 'pending' ? 'warning' : 'error';
  return (
    <Card style={{ gap: 6 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Badge label={PurchaseRequestStatusLabels[request.status] ?? '대기'} tone={tone} />
        <Badge label={MileageCategoryLabels[request.items[0]?.category ?? 'gifticon'] ?? '상품'} tone="neutral" />
        <View style={{ flex: 1 }} />
        <T variant="caption" tone="hint">{fmt(request.createdAt)}</T>
      </View>
      {request.items.map((item) => (
        <T key={`${item.productId}-${item.productName}`}>
          {item.productName} <T tone="hint">× {item.quantity}</T>
        </T>
      ))}
      <T variant="caption" tone="secondary">신청 금액 {won(request.totalAmount)} · 수량 {qty}개</T>
      {request.reviewComment ? <T variant="caption" tone="secondary">매니저 메모: {request.reviewComment}</T> : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  balance: { borderRadius: 18, padding: 20, gap: 4 },
  dot: { position: 'absolute', top: -6, right: -8, minWidth: 18, height: 18, borderRadius: 9, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4 },
  search: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, minHeight: 44 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: -5 },
  cell: { width: '50%', padding: 5 },
  image: { height: 96, borderRadius: 10, overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'center', padding: 24 },
  sheet: { borderRadius: 18, padding: 20, gap: 12 },
  step: { width: 36, height: 36, borderRadius: 10, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
});
