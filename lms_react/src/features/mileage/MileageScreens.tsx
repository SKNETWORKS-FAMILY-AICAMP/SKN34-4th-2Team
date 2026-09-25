import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import {
  createPurchaseRequest,
  useMileageProducts,
  useMileageSettings,
  useMileageTransactions,
  usePurchaseRequests,
} from '../../data/repository';
import {
  MileageCategories,
  MileageCategoryLabels,
  MileageDefaultLimits,
  PurchaseRequestStatusLabels,
} from '../../domain/constants';
import type { MileageCartItem, MileageProduct, PurchaseRequest } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import {
  Badge,
  Button,
  Card,
  Chip,
  DataTable,
  Dialog,
  EmptyState,
  Field,
  PageHeader,
  Row,
  Spacer,
  TabPage,
  Tabs,
  TextInput,
} from '../../ui/components';
import { formatDate, formatDateTime, formatMileage, formatSigned } from '../../utils/format';
import { dateKeyOf } from '../../data/seed';
import { useCurrentUser } from '../auth/session';
import { MileageCreditCard } from './MileageCreditCard';
import { useCart } from './cart';

/**
 * 마일리지 — features/mileage/presentation/mileage_screen.dart
 *
 * 카드를 화면 가운데 크게 놓고, 그 아래로 소멸 안내와 「마일리지 사용하기」를 둔다.
 * 내역과 구매 요청은 알약 모양 2탭으로 갈린다. 내역 탭에는 기간 필터가 붙는다.
 */
function monthAgo(d: Date): Date {
  const x = new Date(d);
  x.setMonth(x.getMonth() - 1);
  return x;
}

// 내 PC 시각 기준 — toISOString 은 세계 표준시라 오후에 고른 날짜가 하루 앞으로 밀린다
const isoDay = (d: Date) => dateKeyOf(d);

export function MileageScreen() {
  const user = useCurrentUser();
  const transactions = useMileageTransactions(user.uid);
  const requests = usePurchaseRequests(user.uid);
  const [tab, setTab] = useState<'history' | 'requests'>('history');

  // 기본은 최근 한 달. 날짜를 직접 고르면 프리셋이 풀린다.
  const today = new Date();
  const [range, setRange] = useState<{ start: string; end: string } | null>({
    start: isoDay(monthAgo(today)),
    end: isoDay(today),
  });
  const [preset, setPreset] = useState<'month' | 'all' | 'none'>('month');

  const filtered = transactions.filter((t) => {
    if (range === null || t.createdAt === undefined) return true;
    const day = isoDay(t.createdAt);
    return day >= range.start && day <= range.end;
  });

  return (
    <TabPage
      title="마일리지"
      description="적립 내역을 확인하고 상품을 교환하세요."
      actions={
        <div className="mileage-head__who">
          <strong>{user.displayName}</strong>
          <span>{user.cohortName}</span>
        </div>
      }
    >

      <div className="mileage-hero">
        <MileageCreditCard balance={user.mileageBalance} holderName={user.displayName} width={420} />
      </div>
      <p className="mileage-expiry">
        모든 마일리지는 종강일 기준 2주까지 사용 가능하며, 이후 자동 소멸됩니다.
      </p>

      <div className="mileage-use">
        <Link className="btn btn--filled btn--md mileage-use__btn" to={RoutePaths.mileageShop}>
          <Icon name="shopping_bag" size={16} />
          마일리지 사용하기
        </Link>
      </div>

      <Tabs
        active={tab}
        onChange={(id) => setTab(id as typeof tab)}
        items={[
          { id: 'history', label: '마일리지 내역' },
          { id: 'requests', label: '구매 요청', count: requests.length },
        ]}
      />

      {tab === 'history' ? (
        <div className="mileage-history">
          <div className="mdate">
            <label className="mdate__field">
              <span>시작일</span>
              <input
                type="date"
                className="input"
                value={range?.start ?? ''}
                onChange={(e) => {
                  setPreset('none');
                  setRange({ start: e.target.value, end: range?.end ?? isoDay(today) });
                }}
              />
            </label>
            <span className="mdate__tilde">~</span>
            <label className="mdate__field">
              <span>종료일</span>
              <input
                type="date"
                className="input"
                value={range?.end ?? ''}
                onChange={(e) => {
                  setPreset('none');
                  setRange({ start: range?.start ?? isoDay(monthAgo(today)), end: e.target.value });
                }}
              />
            </label>
          </div>

          <div className="mdate__presets">
            <button
              type="button"
              className={`mpreset${preset === 'month' ? ' mpreset--on' : ''}`}
              onClick={() => {
                setPreset('month');
                setRange({ start: isoDay(monthAgo(today)), end: isoDay(today) });
              }}
            >
              1개월
            </button>
            <button
              type="button"
              className={`mpreset${preset === 'all' ? ' mpreset--on' : ''}`}
              onClick={() => {
                setPreset('all');
                setRange(null);
              }}
            >
              전체
            </button>
            <button type="button" className="btn btn--filled btn--sm">
              조회
            </button>
          </div>

          <hr className="mileage-rule" />

          {filtered.length === 0 ? (
            <p className="mileage-none">거래 내역이 없습니다</p>
          ) : (
            <ul className="mtx">
              {filtered.map((t) => (
                <li key={t.id} className="mtx__row">
                  <span className="mtx__date">{formatDate(t.createdAt)}</span>
                  <strong className={`mtx__amount${t.amount < 0 ? ' mtx__amount--out' : ''}`}>
                    {formatSigned(t.amount)}
                  </strong>
                  <span className="mtx__reason">{t.reason}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <PurchaseRequestsTab requests={requests} />
      )}
    </TabPage>
  );
}

/** 구매 요청 탭 — 요약 칸 넷, 상태·상품 타입 칩, 요청 카드 */
function PurchaseRequestsTab({ requests }: { requests: PurchaseRequest[] }) {
  const [status, setStatus] = useState('all');
  const [category, setCategory] = useState('all');

  const count = (fn: (r: PurchaseRequest) => boolean) => requests.filter(fn).length;
  const shown = requests
    .filter((r) => status === 'all' || r.status === status)
    .filter((r) => category === 'all' || r.items.some((i) => i.category === category));

  return (
    <div className="mreq">
      <div className="mreq__summary">
        {(
          [
            ['전체 요청', requests.length],
            ['대기', count((r) => r.status === 'pending')],
            ['승인', count((r) => r.status === 'approved')],
            [
              '수정/반려/취소',
              count((r) => ['modify_requested', 'rejected', 'cancelled'].includes(r.status)),
            ],
          ] as const
        ).map(([label, n]) => (
          <span key={label} className="mreq__sum">
            <span className="mreq__sum-label">{label}</span>
            <strong>{n}건</strong>
          </span>
        ))}
      </div>

      <FilterChipRow
        label="상태"
        selected={status}
        onSelect={setStatus}
        options={[
          ['all', '전체'],
          ['pending', '대기'],
          ['approved', '승인'],
          ['modify_requested', '수정 요청'],
          ['rejected', '반려'],
          ['cancelled', '취소'],
        ]}
      />
      <FilterChipRow
        label="상품 타입"
        selected={category}
        onSelect={setCategory}
        options={[
          ['all', '전체'],
          ['gifticon', '기프티콘'],
          ['book', '도서'],
          ['onlineCourse', '인터넷 강의'],
        ]}
      />

      {shown.length === 0 ? (
        <p className="mileage-none">구매 요청이 없습니다</p>
      ) : (
        shown.map((r) => <PurchaseRequestCard key={r.id} request={r} />)
      )}
    </div>
  );
}

function FilterChipRow({
  label,
  selected,
  onSelect,
  options,
}: {
  label: string;
  selected: string;
  onSelect(v: string): void;
  options: readonly (readonly [string, string])[];
}) {
  return (
    <div className="mchips">
      <span className="mchips__label">{label}</span>
      {options.map(([value, text]) => (
        <button
          key={value}
          type="button"
          className={`mchip${selected === value ? ' mchip--on' : ''}`}
          onClick={() => onSelect(value)}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

function PurchaseRequestCard({ request }: { request: PurchaseRequest }) {
  const qty = request.items.reduce((sum, i) => sum + i.quantity, 0);
  const details: [string, string][] = [
    ['신청 금액', formatMileage(request.totalAmount)],
    ['수량', `${qty}개`],
  ];
  if (request.reviewComment !== undefined && request.reviewComment !== '') {
    details.push(['매니저 메모', request.reviewComment]);
  }

  return (
    <article className="mreq__card">
      <header className="mreq__card-head">
        <Badge
          tone={
            request.status === 'approved'
              ? 'success'
              : request.status === 'pending'
                ? 'warning'
                : 'error'
          }
        >
          {PurchaseRequestStatusLabels[request.status]}
        </Badge>
        <span className="mchip mchip--tag">
          {MileageCategoryLabels[request.items[0]?.category ?? 'gifticon']}
        </span>
        <Spacer />
        <span className="hint">{formatDateTime(request.createdAt)}</span>
      </header>

      <ul className="mreq__items">
        {request.items.map((item) => (
          <li key={`${item.productId}-${item.productName}`}>
            {item.productName}
            <span className="hint"> × {item.quantity}</span>
          </li>
        ))}
      </ul>

      <dl className="mreq__details">
        {details.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

/**
 * 마일리지 교환소 — mileage_shop_screen.dart
 *
 * 잔액 카드 → 카테고리별 남은 한도 → 분류 · 정렬 · 검색 → 상품 격자 순서. 원본 그대로다.
 * 한도는 내 구매 요청에서 센다: 승인 · 대기 · 수정 요청이 한도를 깎는다(반려 · 취소는 빼지 않는다).
 */
export function MileageShopScreen() {
  const user = useCurrentUser();
  const products = useMileageProducts().filter((p) => p.isActive);
  const settings = useMileageSettings();
  const myRequests = usePurchaseRequests(user.uid);
  const { items, add } = useCart();
  const [category, setCategory] = useState('all');
  const [sort, setSort] = useState<'default' | 'high' | 'low'>('default');
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<MileageProduct | undefined>(undefined);

  const usages = useCategoryUsage(myRequests, settings.categoryLimits);
  const usageOf = (c: string) => usages.find((u) => u.category === c);

  const text = query.trim().toLowerCase();
  const filtered = products.filter(
    (p) =>
      (category === 'all' || p.category === category) &&
      (text === '' || p.name.toLowerCase().includes(text)),
  );
  // 가격 직접 입력 상품은 값이 없으므로 0 으로 놓고 견준다(원본과 같다)
  const priceOf = (p: MileageProduct) => (p.pricingType === 'custom' ? 0 : p.fixedPrice ?? 0);
  const sorted =
    sort === 'default'
      ? filtered
      : [...filtered].sort((a, b) => (sort === 'high' ? priceOf(b) - priceOf(a) : priceOf(a) - priceOf(b)));

  return (
    <div className="screen__inner">
      <PageHeader
        title="마일리지 교환소"
        description="상품을 선택해 장바구니에 담으세요."
        actions={
          <Link className="btn btn--filled btn--md" to={RoutePaths.mileageCart}>
            장바구니 {items.length > 0 ? `(${items.length})` : ''}
          </Link>
        }
      />

      <div className="shop__credit">
        <MileageCreditCard balance={user.mileageBalance} holderName={user.displayName} />
      </div>

      <div className="grid grid--3 shop__limits">
        {usages.map((u) => (
          <article key={u.category} className="limit-card">
            <Row>
              <strong>{MileageCategoryLabels[u.category] ?? u.category}</strong>
              <Spacer />
              <span className="muted limit-card__cap">한도 {formatMileage(u.limit)}</span>
            </Row>
            <strong className="limit-card__left">{formatMileage(u.remaining)}</strong>
            <span className="muted">추가 신청 가능</span>
            <span className="muted limit-card__break">
              승인 {formatMileage(u.approved)} · 대기 {formatMileage(u.pending)} · 수정요청{' '}
              {formatMileage(u.modifyRequested)}
            </span>
          </article>
        ))}
      </div>

      <Tabs
        items={[
          { id: 'all', label: '전체', count: products.length },
          ...Object.entries(MileageCategoryLabels).map(([id, label]) => ({
            id,
            label,
            count: products.filter((p) => p.category === id).length,
          })),
        ]}
        active={category}
        onChange={setCategory}
      />

      <Row>
        <span className="muted">정렬</span>
        {([
          ['default', '기본'],
          ['high', '높은 순'],
          ['low', '낮은 순'],
        ] as const).map(([id, label]) => (
          <Chip key={id} selected={sort === id} onClick={() => setSort(id)}>
            {label}
          </Chip>
        ))}
        <Spacer />
        <TextInput
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="상품 검색"
          aria-label="상품 검색"
        />
      </Row>

      {sorted.length === 0 ? (
        <EmptyState message="등록된 상품이 없습니다. 관리자에게 문의해 주세요." />
      ) : (
        <div className="grid grid--3">
          {sorted.map((product) => (
            <ProductCard
              key={product.id}
              product={product}
              remaining={usageOf(product.category)?.remaining}
              onPick={() => setPicked(product)}
            />
          ))}
        </div>
      )}

      {picked !== undefined && (
        <AddToCartDialog
          product={picked}
          usage={usageOf(picked.category)}
          balance={user.mileageBalance}
          onClose={() => setPicked(undefined)}
          onAdd={(item) => {
            add(item);
            setPicked(undefined);
          }}
        />
      )}
    </div>
  );
}

interface CategoryUsage {
  category: string;
  limit: number;
  approved: number;
  pending: number;
  modifyRequested: number;
  remaining: number;
}

/** 카테고리별 한도 사용량 — mileage_repository.computeCategoryUsage */
function useCategoryUsage(requests: PurchaseRequest[], limits: Record<string, number>): CategoryUsage[] {
  return MileageCategories.map((category) => {
    const limit = limits[category] ?? MileageDefaultLimits[category] ?? 0;
    const sum = (status: string) =>
      requests
        .filter((r) => r.status === status)
        .flatMap((r) => r.items)
        .filter((i) => i.category === category)
        .reduce((s, i) => s + i.unitPrice * i.quantity, 0);
    const approved = sum('approved');
    const pending = sum('pending');
    const modifyRequested = sum('modify_requested');
    const used = approved + pending + modifyRequested;
    return {
      category,
      limit,
      approved,
      pending,
      modifyRequested,
      remaining: Math.min(Math.max(limit - used, 0), limit),
    };
  });
}

function ProductCard({
  product,
  remaining,
  onPick,
}: {
  product: MileageProduct;
  remaining?: number;
  onPick(): void;
}) {
  const custom = product.pricingType === 'custom';
  return (
    <button type="button" className="product-card" onClick={onPick}>
      <Badge tone="neutral">{MileageCategoryLabels[product.category] ?? product.category}</Badge>
      {product.imageUrl ? (
        <img className="product-card__image" src={product.imageUrl} alt="" />
      ) : (
        <span className="product-card__image product-card__image--empty">
          <Icon name="card_giftcard" />
        </span>
      )}
      <strong className="product-card__name">{product.name}</strong>
      <span className="product-card__price">
        {custom ? '가격 직접 입력' : formatMileage(product.fixedPrice ?? 0)}
      </span>
      {remaining !== undefined && <span className="muted">잔여 {formatMileage(remaining)}</span>}
    </button>
  );
}

/**
 * 장바구니에 담기 — 정가 상품은 수량만, 가격 직접 입력 상품은 링크와 가격을 받는다.
 * 가격은 카테고리 잔여 한도와 내 잔액을 넘을 수 없다(mileage_product_dialogs.dart).
 */
function AddToCartDialog({
  product,
  usage,
  balance,
  onAdd,
  onClose,
}: {
  product: MileageProduct;
  usage?: CategoryUsage;
  balance: number;
  onAdd(item: MileageCartItem): void;
  onClose(): void;
}) {
  const custom = product.pricingType === 'custom';
  const [quantity, setQuantity] = useState(1);
  const [link, setLink] = useState('');
  const [price, setPrice] = useState('');
  const [error, setError] = useState<{ link?: string; price?: string }>({});

  const submit = () => {
    if (!custom) {
      onAdd({
        productId: product.id,
        productName: product.name,
        category: product.category,
        pricingType: product.pricingType,
        unitPrice: product.fixedPrice ?? 0,
        quantity,
      });
      return;
    }
    const value = Number(price.trim());
    const next: { link?: string; price?: string } = {};
    if (link.trim() === '') next.link = '링크를 입력해 주세요.';
    else if (!link.trim().startsWith('http')) next.link = '올바른 URL을 입력해 주세요.';
    if (!Number.isFinite(value) || value <= 0) next.price = '올바른 가격을 입력해 주세요.';
    else if (usage !== undefined && value > usage.remaining) next.price = '카테고리 잔여 한도를 초과합니다.';
    else if (value > balance) next.price = '마일리지 잔액이 부족합니다.';
    setError(next);
    if (next.link !== undefined || next.price !== undefined) return;
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
    <Dialog
      title={product.name}
      onClose={onClose}
      actions={
        <>
          <Button variant="text" onClick={onClose}>
            취소
          </Button>
          <Button onClick={submit}>장바구니에 담기</Button>
        </>
      }
    >
      {usage !== undefined && (
        <p className="notice-banner">
          {MileageCategoryLabels[product.category] ?? product.category} 잔여 한도:{' '}
          {formatMileage(usage.remaining)} / {formatMileage(usage.limit)}
        </p>
      )}
      {custom ? (
        <>
          <Field
            label={product.category === 'onlineCourse' ? '강의 링크' : '도서 링크'}
            error={error.link}
          >
            <TextInput
              value={link}
              onChange={(e) => setLink(e.target.value)}
              placeholder={
                product.category === 'onlineCourse'
                  ? 'https://www.inflearn.com/course/...'
                  : 'https://www.yes24.com/...'
              }
            />
          </Field>
          <Field label="가격 (M)" error={error.price}>
            <TextInput
              type="number"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="예) 66000"
            />
          </Field>
        </>
      ) : (
        <>
          <strong className="price">{formatMileage(product.fixedPrice ?? 0)}</strong>
          <Field label="수량">
            <Row>
              <Button
                variant="text"
                disabled={quantity <= 1}
                onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                aria-label="수량 줄이기"
              >
                −
              </Button>
              <span>{quantity}</span>
              <Button variant="text" onClick={() => setQuantity((q) => q + 1)} aria-label="수량 늘리기">
                +
              </Button>
            </Row>
          </Field>
        </>
      )}
    </Dialog>
  );
}

/** 장바구니 — mileage_cart_screen.dart */
export function MileageCartScreen() {
  const user = useCurrentUser();
  const navigate = useNavigate();
  const { items, remove, setQuantity, clear } = useCart();
  const total = items.reduce((s, i) => s + i.unitPrice * i.quantity, 0);
  const enough = total <= user.mileageBalance;

  const submit = () => {
    createPurchaseRequest({
      userId: user.uid,
      userDisplayName: user.displayName,
      items,
      totalAmount: total,
      status: 'pending',
    });
    clear();
    navigate(RoutePaths.mileage);
  };

  return (
    <div className="screen__inner">
      <PageHeader title="장바구니" description="신청하면 관리자 승인 후 마일리지가 차감됩니다." />

      {items.length === 0 ? (
        <Card>
          <EmptyState
            message="장바구니가 비었습니다"
            action={
              <Link className="btn btn--outline btn--sm" to={RoutePaths.mileageShop}>
                상품 보러 가기
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          <Card padded={false}>
            <DataTable
              rows={items}
              rowKey={(i) => i.productId}
              columns={[
                { key: 'name', header: '상품', render: (i) => i.productName },
                {
                  key: 'category',
                  header: '분류',
                  render: (i) => MileageCategoryLabels[i.category] ?? i.category,
                },
                { key: 'price', header: '단가', align: 'right', render: (i) => formatMileage(i.unitPrice) },
                {
                  key: 'qty',
                  header: '수량',
                  width: '110px',
                  render: (i) => (
                    <TextInput
                      type="number"
                      min={1}
                      value={i.quantity}
                      onChange={(e) => setQuantity(i.productId, Math.max(1, Number(e.target.value)))}
                    />
                  ),
                },
                {
                  key: 'sum',
                  header: '합계',
                  align: 'right',
                  render: (i) => formatMileage(i.unitPrice * i.quantity),
                },
                {
                  key: 'remove',
                  header: '',
                  render: (i) => (
                    <Button variant="text" size="sm" onClick={() => remove(i.productId)}>
                      삭제
                    </Button>
                  ),
                },
              ]}
            />
          </Card>

          <Card>
            <Row gap={8}>
              <span>보유 마일리지</span>
              <Spacer />
              <strong>{formatMileage(user.mileageBalance)}</strong>
            </Row>
            <Row gap={8}>
              <span>신청 합계</span>
              <Spacer />
              <strong style={{ color: enough ? 'var(--text-primary)' : 'var(--error)' }}>
                {formatMileage(total)}
              </strong>
            </Row>
            {!enough && <span className="field__error">보유 마일리지가 부족합니다.</span>}
            <Row>
              <Spacer />
              <Button variant="outline" onClick={clear}>
                비우기
              </Button>
              <Button disabled={!enough} onClick={submit}>
                구매 신청
              </Button>
            </Row>
          </Card>
        </>
      )}
    </div>
  );
}
