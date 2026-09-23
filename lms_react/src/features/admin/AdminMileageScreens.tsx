import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { RoutePaths, adminMileageProductEditPath } from '../../app/routePaths';
import {
  adjustMileage,
  deleteMileageProduct,
  reviewPurchaseRequest,
  updateMileageSettings,
  upsertMileageProduct,
  useMileageProducts,
  useMileageSettings,
  useMileageTransactions,
  usePurchaseRequests,
  useStudents,
} from '../../data/repository';
import { nextId } from '../../data/store';
import {
  MileageCategories,
  MileageCategoryLabels,
  PurchaseRequestStatusLabels,
} from '../../domain/constants';
import type { MileageProduct, MileagePricingType } from '../../domain/types';
import {
  Badge,
  Button,
  Card,
  Chip,
  DataTable,
  Dialog,
  Field,
  PageHeader,
  Row,
  Select,
  Spacer,
  TextArea,
  TextInput,
  Toggle,
} from '../../ui/components';
import { formatDateTime, formatMileage } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { MenuRow } from './AdminDashboardScreen';

/** 마일리지 허브 — admin_mileage_hub_screen.dart */
export function AdminMileageHubScreen() {
  return (
    <div className="admin-page">
      <h1 className="admin-page__title">마일리지 관리</h1>
      <p className="admin-page__desc">
        상품 등록, 구매 요청 처리, 마일리지 지급 및 기수 설정을 관리합니다.
      </p>

      <MenuRow
        icon="inventory_2"
        title="상품 관리"
        sub="교환 상품 등록·수정·삭제"
        to={RoutePaths.adminMileageProducts}
      />
      <MenuRow
        icon="shopping_cart_checkout"
        title="구매 요청 처리"
        sub="학생 구매 요청 승인·반려·수정 요청"
        to={RoutePaths.adminMileageRequests}
      />
      <MenuRow
        icon="payments"
        title="마일리지 지급/차감"
        sub="학생별 수동 마일리지 조정"
        to={RoutePaths.adminMileageAdjust}
      />
      <MenuRow
        icon="tune"
        title="기수 설정"
        sub="카테고리 한도 · 미션 적립 안내"
        to={RoutePaths.adminMileageSettings}
      />
    </div>
  );
}

/** 상품 관리 — admin_mileage_products_screen.dart */
export function AdminMileageProductsScreen() {
  const products = useMileageProducts();
  const navigate = useNavigate();

  return (
    <div className="screen__inner">
      <PageHeader
        title="마일리지 상품"
        description="학생이 신청할 수 있는 상품을 관리합니다."
        actions={
          <Link className="btn btn--filled btn--md" to={RoutePaths.adminMileageProductsCreate}>
            상품 등록
          </Link>
        }
      />
      <Card padded={false}>
        <DataTable
          rows={products}
          rowKey={(p) => p.id}
          empty="등록된 상품이 없습니다."
          columns={[
            { key: 'name', header: '상품', render: (p) => p.name },
            {
              key: 'category',
              header: '분류',
              width: '120px',
              render: (p) => MileageCategoryLabels[p.category] ?? p.category,
            },
            {
              key: 'price',
              header: '가격',
              width: '130px',
              align: 'right',
              render: (p) => (p.pricingType === 'fixed' ? formatMileage(p.fixedPrice ?? 0) : '직접 입력'),
            },
            {
              key: 'active',
              header: '판매',
              width: '80px',
              render: (p) => <Toggle checked={p.isActive} onChange={(v) => upsertMileageProduct({ ...p, isActive: v })} />,
            },
            {
              key: 'actions',
              header: '',
              width: '140px',
              align: 'right',
              render: (p) => (
                <Row gap={4} wrap={false}>
                  <Spacer />
                  <Button size="sm" variant="outline" onClick={() => navigate(adminMileageProductEditPath(p.id))}>
                    수정
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => deleteMileageProduct(p.id)}>
                    삭제
                  </Button>
                </Row>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}

/** 상품 등록·수정 — admin_mileage_product_form_screen.dart */
export function AdminMileageProductFormScreen() {
  const { productId } = useParams<{ productId: string }>();
  const products = useMileageProducts();
  const existing = products.find((p) => p.id === productId);
  const navigate = useNavigate();

  const [name, setName] = useState(existing?.name ?? '');
  const [description, setDescription] = useState(existing?.description ?? '');
  const [category, setCategory] = useState(existing?.category ?? MileageCategories[0]);
  const [pricingType, setPricingType] = useState<MileagePricingType>(existing?.pricingType ?? 'fixed');
  const [fixedPrice, setFixedPrice] = useState(String(existing?.fixedPrice ?? ''));
  const [imageUrl, setImageUrl] = useState(existing?.imageUrl ?? '');
  const [sortOrder, setSortOrder] = useState(String(existing?.sortOrder ?? products.length + 1));
  const [isActive, setActive] = useState(existing?.isActive ?? true);
  const [error, setError] = useState<string | null>(null);

  const save = () => {
    if (name.trim() === '') {
      setError('상품 이름을 입력해 주세요.');
      return;
    }
    const product: MileageProduct = {
      id: existing?.id ?? nextId('mp'),
      name: name.trim(),
      description: description.trim(),
      category,
      pricingType,
      fixedPrice: pricingType === 'fixed' ? Number(fixedPrice) : undefined,
      imageUrl: imageUrl.trim() === '' ? undefined : imageUrl.trim(),
      isActive,
      sortOrder: Number(sortOrder) || 0,
    };
    upsertMileageProduct(product);
    navigate(RoutePaths.adminMileageProducts);
  };

  return (
    <div className="screen__inner">
      <PageHeader title={existing === undefined ? '상품 등록' : '상품 수정'} />
      <Card>
        <Field label="상품 이름" error={error ?? undefined}>
          <TextInput value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="설명">
          <TextArea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="grid grid--2">
          <Field label="분류">
            <Select value={category} onChange={(e) => setCategory(e.target.value)}>
              {MileageCategories.map((c) => (
                <option key={c} value={c}>
                  {MileageCategoryLabels[c]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="가격 방식">
            <Select value={pricingType} onChange={(e) => setPricingType(e.target.value as MileagePricingType)}>
              <option value="fixed">정가</option>
              <option value="custom">학생이 직접 입력</option>
            </Select>
          </Field>
          {pricingType === 'fixed' && (
            <Field label="정가(M)">
              <TextInput type="number" value={fixedPrice} onChange={(e) => setFixedPrice(e.target.value)} />
            </Field>
          )}
        </div>
        {/* 원본은 이미지 주소를 받는다(교환소 카드에 쓴다) */}
        <Field label="이미지 주소">
          <TextInput value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} placeholder="https://" />
        </Field>
        <Field label="정렬 순서" hint="작을수록 먼저 보여 줍니다.">
          <TextInput type="number" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} />
        </Field>
        <Toggle checked={isActive} onChange={setActive} label="판매 중" />
        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(RoutePaths.adminMileageProducts)}>
            취소
          </Button>
          <Button onClick={save}>저장</Button>
        </Row>
      </Card>
    </div>
  );
}

/** 구매 요청 — admin_purchase_requests_screen.dart */
export function AdminPurchaseRequestsScreen() {
  const all = usePurchaseRequests();
  const [open, setOpen] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [status, setStatus] = useState('all');
  const [category, setCategory] = useState('all');

  // 원본(admin_purchase_requests_screen.dart)처럼 상태 · 상품 타입으로 거른다
  const requests = all.filter(
    (r) =>
      (status === 'all' || r.status === status) &&
      (category === 'all' || r.items.some((i) => i.category === category)),
  );
  const target = all.find((r) => r.id === open);

  return (
    <div className="screen__inner">
      <PageHeader title="구매 요청" description="학생 구매 요청을 승인·반려합니다. 승인하면 마일리지가 차감됩니다." />

      <Row wrap>
        <span className="muted">상태</span>
        {[['all', '전체'], ['pending', '대기'], ['approved', '승인'], ['modify_requested', '수정 요청'], ['rejected', '반려'], ['cancelled', '취소']].map(
          ([id, label]) => (
            <Chip key={id} selected={status === id} onClick={() => setStatus(id)}>
              {label}
            </Chip>
          ),
        )}
      </Row>
      <Row wrap>
        <span className="muted">상품 타입</span>
        {[['all', '전체'], ...MileageCategories.map((c) => [c, MileageCategoryLabels[c]])].map(([id, label]) => (
          <Chip key={id} selected={category === id} onClick={() => setCategory(id)}>
            {label}
          </Chip>
        ))}
      </Row>

      <Card padded={false}>
        <DataTable
          rows={requests}
          rowKey={(r) => r.id}
          empty="구매 요청이 없습니다."
          onRowClick={(r) => {
            setOpen(r.id);
            setComment(r.reviewComment ?? '');
          }}
          columns={[
            { key: 'student', header: '학생', width: '110px', render: (r) => r.userDisplayName },
            { key: 'items', header: '상품', render: (r) => r.items.map((i) => `${i.productName} × ${i.quantity}`).join(', ') },
            { key: 'amount', header: '금액', width: '120px', align: 'right', render: (r) => formatMileage(r.totalAmount) },
            { key: 'at', header: '요청', width: '160px', render: (r) => formatDateTime(r.createdAt) },
            {
              key: 'status',
              header: '상태',
              width: '90px',
              render: (r) => (
                <Badge tone={r.status === 'approved' ? 'success' : r.status === 'pending' ? 'warning' : 'error'}>
                  {PurchaseRequestStatusLabels[r.status]}
                </Badge>
              ),
            },
          ]}
        />
      </Card>

      {target !== undefined && (
        <Dialog
          title={`${target.userDisplayName} 구매 요청`}
          onClose={() => setOpen(null)}
          actions={
            <>
              <Button variant="outline" onClick={() => setOpen(null)}>
                닫기
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  reviewPurchaseRequest(target.id, 'rejected', comment.trim() || undefined);
                  setOpen(null);
                }}
              >
                반려
              </Button>
              <Button
                onClick={() => {
                  reviewPurchaseRequest(target.id, 'approved', comment.trim() || undefined);
                  setOpen(null);
                }}
              >
                승인
              </Button>
            </>
          }
        >
          <ul className="list">
            {target.items.map((item) => (
              <li key={item.productId} className="list__item">
                <span>{item.productName}</span>
                <Spacer />
                <span className="hint">
                  {formatMileage(item.unitPrice)} × {item.quantity}
                </span>
              </li>
            ))}
          </ul>
          <Row gap={8}>
            <strong>합계</strong>
            <Spacer />
            <strong>{formatMileage(target.totalAmount)}</strong>
          </Row>
          <Field label="검토 의견">
            <TextArea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
          </Field>
        </Dialog>
      )}
    </div>
  );
}

/** 수동 조정 — admin_mileage_adjust_screen.dart */
export function AdminMileageAdjustScreen() {
  const admin = useCurrentUser();
  const students = useStudents(admin.cohortId);
  const transactions = useMileageTransactions();

  const [userId, setUserId] = useState(students[0]?.uid ?? '');
  const [studentQuery, setStudentQuery] = useState('');
  const [direction, setDirection] = useState<'grant' | 'deduct'>('grant');
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  // 이름으로 좁혀 고른다(원본은 검색칸 + 목록)
  const shown = students.filter((s) => s.displayName.includes(studentQuery.trim()));

  const submit = () => {
    const entered = Math.abs(Number(amount));
    const value = direction === 'deduct' ? -entered : entered;
    if (userId === '' || Number.isNaN(entered) || entered === 0) {
      setError('학생과 0이 아닌 금액을 지정해 주세요.');
      return;
    }
    if (reason.trim() === '') {
      setError('사유를 적어 주세요. 학생 내역에 그대로 보입니다.');
      return;
    }
    adjustMileage(userId, value, reason.trim(), admin.uid);
    setAmount('');
    setReason('');
    setError(null);
    setDone(true);
    window.setTimeout(() => setDone(false), 2000);
  };

  return (
    <div className="screen__inner">
      <PageHeader title="마일리지 지급/차감" description="학생을 골라 마일리지를 지급하거나 차감합니다." />

      {done && <div className="callout callout--success">조정을 반영했습니다.</div>}

      <Card>
        <Field label="학생 검색 (이름)">
          <TextInput value={studentQuery} onChange={(e) => setStudentQuery(e.target.value)} placeholder="이름" />
        </Field>
        <div className="grid grid--3">
          <Field label="학생">
            <Select value={userId} onChange={(e) => setUserId(e.target.value)}>
              {shown.map((s) => (
                <option key={s.uid} value={s.uid}>
                  {s.displayName} ({formatMileage(s.mileageBalance)})
                </option>
              ))}
            </Select>
          </Field>
          <Field label="금액(M)">
            <TextInput type="number" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="50000" />
          </Field>
        </div>
        <Row>
          {([
            ['grant', '지급'],
            ['deduct', '차감'],
          ] as const).map(([id, label]) => (
            <Chip key={id} selected={direction === id} onClick={() => setDirection(id)}>
              {label}
            </Chip>
          ))}
        </Row>
        <Field label="사유" error={error ?? undefined}>
          <TextInput value={reason} onChange={(e) => setReason(e.target.value)} placeholder="예) 특강 우수 발표 보상" />
        </Field>
        <Row>
          <Spacer />
          <Button onClick={submit}>{direction === 'grant' ? '지급하기' : '차감하기'}</Button>
        </Row>
      </Card>

      <Card padded={false} title="최근 조정 내역">
        <DataTable
          rows={transactions.filter((t) => t.type === 'admin_adjust' || t.type === 'adjust').slice(0, 20)}
          rowKey={(t) => t.id}
          empty="수동 조정 내역이 없습니다."
          columns={[
            { key: 'at', header: '일시', width: '160px', render: (t) => formatDateTime(t.createdAt) },
            { key: 'user', header: '학생', width: '110px', render: (t) => t.userDisplayName },
            { key: 'reason', header: '사유', render: (t) => t.reason },
            {
              key: 'amount',
              header: '금액',
              align: 'right',
              render: (t) => (
                <strong style={{ color: t.amount > 0 ? 'var(--success)' : 'var(--error)' }}>
                  {t.amount > 0 ? '+' : ''}
                  {t.amount.toLocaleString()}
                </strong>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}

/** 마일리지 설정 — admin_mileage_settings_screen.dart */
export function AdminMileageSettingsScreen() {
  const settings = useMileageSettings();
  const [limits, setLimits] = useState(settings.categoryLimits);
  const [rules, setRules] = useState(settings.accrualRules);
  const [saved, setSaved] = useState(false);

  const save = () => {
    updateMileageSettings({ categoryLimits: limits, accrualRules: rules });
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="screen__inner">
      <PageHeader title="마일리지 설정" description="카테고리 한도와 적립 규칙을 정합니다." />

      {saved && <div className="callout callout--success">설정을 저장했습니다.</div>}

      <Card title="카테고리별 한도">
        <div className="grid grid--3">
          {MileageCategories.map((category) => (
            <Field key={category} label={MileageCategoryLabels[category]}>
              <TextInput
                type="number"
                value={limits[category] ?? 0}
                onChange={(e) => setLimits((l) => ({ ...l, [category]: Number(e.target.value) }))}
              />
            </Field>
          ))}
        </div>
      </Card>

      <Card title="적립 규칙">
        <div className="grid grid--3">
          {Object.entries(rules).map(([key, value]) => (
            <Field key={key} label={key}>
              <TextInput
                type="number"
                value={value}
                onChange={(e) => setRules((r) => ({ ...r, [key]: Number(e.target.value) }))}
              />
            </Field>
          ))}
        </div>
        <span className="hint">최근 저장 {formatDateTime(settings.updatedAt)}</span>
      </Card>

      <Row>
        <Spacer />
        <Button onClick={save}>저장</Button>
      </Row>
    </div>
  );
}
