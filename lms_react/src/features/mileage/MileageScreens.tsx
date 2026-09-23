import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import {
  createPurchaseRequest,
  useMileageProducts,
  useMileageTransactions,
  usePurchaseRequests,
} from '../../data/repository';
import {
  MileageCategoryLabels,
  PurchaseRequestStatusLabels,
} from '../../domain/constants';
import type { MileageCartItem, MileageProduct, PurchaseRequest } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  Field,
  PageHeader,
  Row,
  Spacer,
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
    <div className="screen__inner mileage-page">
      <header className="mileage-head">
        <div>
          <h1 className="mileage-head__title">마일리지</h1>
          <p className="mileage-head__desc">적립 내역을 확인하고 상품을 교환하세요.</p>
        </div>
        <div className="mileage-head__who">
          <strong>{user.displayName}</strong>
          <span>{user.cohortName}</span>
        </div>
      </header>

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

      {/* 알약 세그먼트 — 고른 칸은 글씨색으로 칠하고 그 위 글씨는 바탕색이다. */}
      <div className="mseg">
        {(
          [
            ['history', '마일리지 내역'],
            ['requests', '구매 요청'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`mseg__btn${tab === id ? ' mseg__btn--on' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

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
    </div>
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

/** 마일리지 상점 — mileage_shop_screen.dart */
export function MileageShopScreen() {
  const products = useMileageProducts().filter((p) => p.isActive);
  const { items, add } = useCart();
  const [category, setCategory] = useState('all');

  const filtered = category === 'all' ? products : products.filter((p) => p.category === category);

  return (
    <div className="screen__inner">
      <PageHeader
        title="마일리지 상점"
        description="적립한 마일리지로 상품을 신청합니다."
        actions={
          <Link className="btn btn--filled btn--md" to={RoutePaths.mileageCart}>
            장바구니 {items.length > 0 ? `(${items.length})` : ''}
          </Link>
        }
      />

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

      <div className="grid grid--3">
        {filtered.map((product) => (
          <ProductCard key={product.id} product={product} onAdd={add} />
        ))}
      </div>
    </div>
  );
}

function ProductCard({
  product,
  onAdd,
}: {
  product: MileageProduct;
  onAdd(item: MileageCartItem): void;
}) {
  const [custom, setCustom] = useState('');
  const variable = product.pricingType === 'variable';
  const price = variable ? Number(custom) : (product.fixedPrice ?? 0);

  return (
    <Card title={product.name}>
      <Badge tone="neutral">{MileageCategoryLabels[product.category] ?? product.category}</Badge>
      <p className="muted">{product.description}</p>
      {variable ? (
        <Field label="금액 직접 입력">
          <TextInput
            type="number"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder="예) 55000"
          />
        </Field>
      ) : (
        <strong className="price">{formatMileage(product.fixedPrice ?? 0)}</strong>
      )}
      <Button
        disabled={price <= 0}
        onClick={() =>
          onAdd({
            productId: product.id,
            productName: product.name,
            category: product.category,
            pricingType: product.pricingType,
            unitPrice: price,
            quantity: 1,
          })
        }
      >
        장바구니 담기
      </Button>
    </Card>
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
