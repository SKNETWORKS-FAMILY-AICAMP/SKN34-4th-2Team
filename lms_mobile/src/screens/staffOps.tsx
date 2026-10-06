import { router } from 'expo-router';
import { useState, type ReactNode } from 'react';
import { ActivityIndicator, Linking, View, useWindowDimensions } from 'react-native';
import { RoutePaths } from '@web/app/routePaths';
import { MileageCategories, MileageCategoryLabels, MileagePricingLabels, PurchaseRequestStatusLabels } from '@web/domain/constants';
import type { MileagePricingType, MileageProduct, PurchaseRequest } from '@web/domain/types';

import { useSession } from '../auth/session';
import { askAssistant, executeAssistant, type AssistantAction } from '../data/jobs';
import { adjustMileage, deleteProduct, reviewPurchase, saveProduct, useProducts, usePurchases, useTransactions } from '../data/mileage';
import { syncQualExams, useUsers } from '../data/people';
import { refreshBootstrap, useDb } from '../data/query';
import { replaceTeams, useTeams } from '../data/seating';
import { navLabel } from '../nav/webNav';
import { useTheme } from '../theme/Theme';
import { ChipRow, JobNotice, PersonPicker, SectionLabel, ToggleRow, confirmAction, errorText, useJob } from '../ui/form';
import { SeatGrid } from '../ui/SeatGrid';
import { Badge, Btn, Callout, Card, Chip, Composer, EmptyState, Field, ListGroup, ListItem, Muted, Screen, Segmented, StatTile, T, fmt } from '../ui/kit';

function Actions({ children }: { children: ReactNode }) {
  return <View style={{ flexDirection: 'row', gap: 8 }}>{children}</View>;
}

function Half({ children }: { children: ReactNode }) {
  return <View style={{ flex: 1 }}>{children}</View>;
}

const points = (value: number) => `${value.toLocaleString('ko-KR')} P`;

// ── 마일리지 ───────────────────────────────────────────

type MileageTab = 'requests' | 'products' | 'adjust' | 'history';

export function MileageAdminPage() {
  const { user } = useSession();
  const students = useUsers().filter((row) => row.role === 'student' && (!user?.cohortId || row.cohortId === user.cohortId));
  const ids = new Set(students.map((row) => row.uid));
  const purchases = usePurchases().filter((row) => ids.has(row.userId));
  const [tab, setTab] = useState<MileageTab>('requests');
  const pending = purchases.filter((row) => row.status === 'pending').length;
  return (
    <Screen title={navLabel(RoutePaths.adminMileage, '마일리지')} onRefresh={refreshBootstrap}>
      <Segmented
        options={[
          { key: 'requests', label: pending > 0 ? `요청 ${pending}` : '요청' },
          { key: 'products', label: '상품' },
          { key: 'adjust', label: '조정' },
          { key: 'history', label: '내역' },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === 'requests' ? <PurchaseTab rows={purchases} /> : null}
      {tab === 'products' ? <ProductTab /> : null}
      {tab === 'adjust' ? <AdjustTab /> : null}
      {tab === 'history' ? <HistoryTab ids={ids} /> : null}
    </Screen>
  );
}

function PurchaseTab({ rows }: { rows: PurchaseRequest[] }) {
  const job = useJob();
  const [memos, setMemos] = useState<Record<string, string>>({});
  const sorted = [...rows].sort(
    (a, b) => Number(b.status === 'pending') - Number(a.status === 'pending') || (b.createdAt?.getTime() ?? 0) - (a.createdAt?.getTime() ?? 0),
  );
  const decide = (row: PurchaseRequest, status: 'approved' | 'rejected') => {
    const memo = memos[row.id]?.trim() ?? '';
    if (status === 'rejected' && !memo) return job.fail('반려 사유를 메모에 적어 주세요.');
    const label = status === 'approved' ? '승인' : '반려';
    confirmAction(`구매 ${label}`, `${row.userDisplayName}님의 ${points(row.totalAmount)} 요청을 ${label}할까요?`, () =>
      void job.run(() => reviewPurchase(row.id, status, memo || undefined), `${label}했습니다.`),
    label);
  };
  return (
    <>
      <JobNotice notice={job.notice} />
      {sorted.length === 0 ? <Card><EmptyState icon="shopping-cart" text="구매 요청이 없습니다." /></Card> : null}
      {sorted.map((row) => (
        <Card key={row.id} style={{ gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <T variant="subtitle" style={{ flex: 1 }}>{row.userDisplayName}</T>
            <Badge
              label={PurchaseRequestStatusLabels[row.status] ?? row.status}
              tone={row.status === 'pending' ? 'warning' : row.status === 'approved' ? 'success' : 'neutral'}
            />
          </View>
          {row.items.map((item) => (
            <View key={item.productId} style={{ gap: 2 }}>
              <T>{item.productName} × {item.quantity} · {points(item.unitPrice * item.quantity)}</T>
              {item.purchaseLink ? (
                <T variant="caption" tone="primary" numberOfLines={1} onPress={() => void Linking.openURL(item.purchaseLink!)}>{item.purchaseLink}</T>
              ) : null}
            </View>
          ))}
          <T variant="subtitle">합계 {points(row.totalAmount)}</T>
          <T variant="caption" tone="secondary">{fmt(row.createdAt)}</T>
          {row.status === 'pending' ? (
            <>
              <Field label="메모 (반려 시 필수)" value={memos[row.id] ?? ''} onChangeText={(value) => setMemos((prev) => ({ ...prev, [row.id]: value }))} />
              <Actions>
                <Half><Btn label="반려" tone="ghost" disabled={job.busy} onPress={() => decide(row, 'rejected')} /></Half>
                <Half><Btn label="승인" disabled={job.busy} onPress={() => decide(row, 'approved')} /></Half>
              </Actions>
            </>
          ) : row.reviewComment ? (
            <T variant="caption" tone="secondary">메모: {row.reviewComment}</T>
          ) : null}
        </Card>
      ))}
    </>
  );
}

function ProductTab() {
  const { user } = useSession();
  const products = [...useProducts()].sort((a, b) => a.sortOrder - b.sortOrder || a.name.localeCompare(b.name, 'ko'));
  const job = useJob();
  const [editing, setEditing] = useState<MileageProduct | 'new' | null>(null);
  return (
    <>
      {editing === null ? <Btn label="상품 추가" icon="add" onPress={() => setEditing('new')} /> : null}
      {editing !== null ? (
        <ProductForm key={editing === 'new' ? 'new' : editing.id} product={editing === 'new' ? undefined : editing} order={products.length} onDone={() => setEditing(null)} />
      ) : null}
      <JobNotice notice={job.notice} />
      {products.length === 0 ? <Card><EmptyState icon="card-giftcard" text="등록된 상품이 없습니다." /></Card> : null}
      {products.map((product) => (
        <Card key={product.id} style={{ gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <T variant="subtitle" style={{ flex: 1 }}>{product.name}</T>
            <Badge label={MileageCategoryLabels[product.category] ?? product.category} tone="info" />
          </View>
          <T variant="caption" tone="secondary">
            {product.pricingType === 'fixed' ? points(product.fixedPrice ?? 0) : '가격 직접 입력'}
            {product.description ? ` · ${product.description}` : ''}
          </T>
          <ToggleRow
            label="판매 중"
            value={product.isActive}
            disabled={job.busy || !user}
            onChange={(value) => {
              if (user) void job.run(() => saveProduct({ ...product, isActive: value }, user.cohortId));
            }}
          />
          <Actions>
            <Half><Btn label="수정" tone="ghost" onPress={() => setEditing(product)} /></Half>
            <Half>
              <Btn
                label="삭제"
                tone="danger"
                disabled={job.busy}
                onPress={() => confirmAction('상품 삭제', `「${product.name}」을(를) 삭제할까요?`, () => void job.run(() => deleteProduct(product.id), '삭제했습니다.'))}
              />
            </Half>
          </Actions>
        </Card>
      ))}
    </>
  );
}

function ProductForm({ product, order, onDone }: { product?: MileageProduct; order: number; onDone: () => void }) {
  const { user } = useSession();
  const job = useJob();
  const [name, setName] = useState(product?.name ?? '');
  const [description, setDescription] = useState(product?.description ?? '');
  const [category, setCategory] = useState<string>(product?.category ?? MileageCategories[0]);
  const [pricingType, setPricingType] = useState<MileagePricingType>(product?.pricingType ?? 'fixed');
  const [price, setPrice] = useState(product?.fixedPrice !== undefined ? String(product.fixedPrice) : '');
  const save = () => {
    if (!user) return;
    if (!name.trim()) return job.fail('상품 이름을 입력해 주세요.');
    const fixedPrice = Number(price);
    if (pricingType === 'fixed' && (!Number.isInteger(fixedPrice) || fixedPrice <= 0)) return job.fail('가격을 1 이상의 숫자로 입력해 주세요.');
    void job.run(async () => {
      await saveProduct(
        {
          id: product?.id ?? '',
          name: name.trim(),
          description: description.trim(),
          imageUrl: product?.imageUrl,
          category,
          pricingType,
          fixedPrice: pricingType === 'fixed' ? fixedPrice : undefined,
          isActive: product?.isActive ?? true,
          sortOrder: product?.sortOrder ?? order,
        },
        user.cohortId,
      );
      onDone();
    });
  };
  return (
    <Card style={{ gap: 12 }}>
      <T variant="subtitle">{product ? '상품 수정' : '상품 추가'}</T>
      <Field label="이름 *" value={name} onChangeText={setName} />
      <Field label="설명" value={description} onChangeText={setDescription} multiline />
      <ChipRow label="분류" options={MileageCategories.map((key) => ({ key: key as string, label: MileageCategoryLabels[key] ?? key }))} value={category} onChange={setCategory} />
      <ChipRow
        label="가격 방식"
        options={(['fixed', 'custom'] as const).map((key) => ({ key, label: MileagePricingLabels[key] }))}
        value={pricingType}
        onChange={setPricingType}
      />
      {pricingType === 'fixed' ? <Field label="가격 (P) *" value={price} onChangeText={setPrice} keyboard="numeric" /> : <Muted>학생이 구매할 때 가격을 직접 입력합니다.</Muted>}
      <JobNotice notice={job.notice} />
      <Actions>
        <Half><Btn label="취소" tone="ghost" onPress={onDone} /></Half>
        <Half><Btn label={job.busy ? '저장 중…' : '저장'} disabled={job.busy} onPress={save} /></Half>
      </Actions>
    </Card>
  );
}

function AdjustTab() {
  const { user } = useSession();
  const students = useUsers().filter((row) => row.role === 'student' && row.cohortId === user?.cohortId && row.isActive !== false);
  const job = useJob();
  const [uid, setUid] = useState('');
  const [mode, setMode] = useState<'grant' | 'deduct'>('grant');
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const student = students.find((row) => row.uid === uid);

  const submit = () => {
    if (!student) return job.fail('학생을 골라 주세요.');
    const value = Number(amount);
    if (!Number.isInteger(value) || value <= 0) return job.fail('금액을 1 이상의 숫자로 입력해 주세요.');
    if (!reason.trim()) return job.fail('사유를 입력해 주세요.');
    if (mode === 'deduct' && value > student.mileageBalance) return job.fail(`잔액(${points(student.mileageBalance)})보다 많이 차감할 수 없습니다.`);
    const signed = mode === 'grant' ? value : -value;
    confirmAction('마일리지 조정', `${student.displayName}님에게 ${mode === 'grant' ? '+' : '-'}${points(value)} 를 ${mode === 'grant' ? '지급' : '차감'}할까요?`, () =>
      void job.run(async () => {
        await adjustMileage(student.uid, signed, reason.trim());
        setAmount('');
        setReason('');
      }, '조정했습니다.'),
    mode === 'grant' ? '지급' : '차감');
  };

  return (
    <>
      <Card style={{ gap: 12 }}>
        <PersonPicker label="학생" people={students} value={uid} onChange={setUid} />
        {student ? <T tone="primary" style={{ fontWeight: '600' }}>현재 잔액 {points(student.mileageBalance)}</T> : null}
        <ChipRow options={[{ key: 'grant', label: '지급 (+)' }, { key: 'deduct', label: '차감 (-)' }]} value={mode} onChange={setMode} />
        <Field label="금액 (P)" value={amount} onChangeText={setAmount} keyboard="numeric" />
        <Field label="사유 *" value={reason} onChangeText={setReason} placeholder="예) 스터디 우수 · 오지급 정정" />
        <JobNotice notice={job.notice} />
        <Btn label={job.busy ? '처리 중…' : mode === 'grant' ? '지급하기' : '차감하기'} disabled={job.busy} onPress={submit} />
      </Card>
      {students.length === 0 ? <Muted>대시보드에서 기수를 먼저 선택해 주세요.</Muted> : null}
    </>
  );
}

function HistoryTab({ ids }: { ids: Set<string> }) {
  const { palette } = useTheme();
  const rows = [...useTransactions()]
    .filter((row) => ids.has(row.userId))
    .sort((a, b) => (b.createdAt?.getTime() ?? 0) - (a.createdAt?.getTime() ?? 0))
    .slice(0, 100);
  if (rows.length === 0) return <Card><EmptyState icon="receipt-long" text="마일리지 내역이 없습니다." /></Card>;
  return (
    <>
      <SectionLabel title="최근 100건" />
      <ListGroup>
        {rows.map((row) => (
          <ListItem
            key={row.id}
            title={`${row.userDisplayName} · ${row.reason}`}
            subtitle={fmt(row.createdAt)}
            right={<T style={{ fontWeight: '700', color: row.amount >= 0 ? palette.success : palette.error }}>{row.amount >= 0 ? '+' : ''}{row.amount.toLocaleString('ko-KR')}</T>}
          />
        ))}
      </ListGroup>
    </>
  );
}

// ── LLMOps ─────────────────────────────────────────────

const AI_TYPE_LABEL: Record<string, string> = {
  assessment: '문제생성',
  job_chat: '공고챗봇',
  job_recommend: '추천',
  resume_review: '첨삭',
  student_chatbot: '학생챗봇',
  admin_assistant: '관리자 도우미',
};

export function AiPage() {
  const db = useDb();
  const logs = [...(db?.aiLogs ?? [])].sort((a, b) => (b.createdAt?.getTime() ?? 0) - (a.createdAt?.getTime() ?? 0));
  const evals = [...(db?.aiEvals ?? [])].sort((a, b) => new Date(b.ranAt).getTime() - new Date(a.ranAt).getTime());
  const job = useJob();
  const [synced, setSynced] = useState('');
  const errors = logs.filter((row) => row.status === 'error').length;
  const latency = logs.length ? Math.round(logs.reduce((sum, row) => sum + row.latencyMs, 0) / logs.length) : 0;

  return (
    <Screen title={navLabel(RoutePaths.adminAiQuality, 'LLMOps')} onRefresh={refreshBootstrap}>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <StatTile icon="bolt" label="호출" value={`${logs.length}건`} />
        <StatTile icon="error-outline" label="오류" value={`${errors}건`} tone={errors > 0 ? 'error' : 'neutral'} />
        <StatTile icon="timer" label="평균 응답" value={`${(latency / 1000).toFixed(1)}초`} tone="info" />
      </View>
      <Card style={{ gap: 8 }}>
        <T variant="subtitle">자격 시험 일정</T>
        <Muted>Q-Net 등에서 시험 일정을 다시 가져옵니다.</Muted>
        <Btn
          label={job.busy ? '동기화 중…' : '자격 일정 동기화'}
          icon="sync"
          tone="ghost"
          disabled={job.busy}
          onPress={() =>
            void job.run(async () => {
              const counts = await syncQualExams();
              setSynced(Object.entries(counts ?? {}).map(([key, value]) => `${key} ${value}`).join(' · '));
            }, '동기화했습니다.')
          }
        />
        <JobNotice notice={job.notice} />
        {synced ? <Muted>{synced}</Muted> : null}
      </Card>

      <SectionLabel title={`평가 실행 ${evals.length}건`} />
      {evals.length === 0 ? <Muted>평가 실행 기록이 없습니다.</Muted> : (
        <ListGroup>
          {evals.slice(0, 10).map((row) => (
            <ListItem
              key={row.id}
              title={`${row.suite} · ${row.promptVersion}`}
              subtitle={`${row.caseCount}건 · ${fmt(row.ranAt)}${row.model ? ` · ${row.model}` : ''}`}
              right={<Badge label={`${Math.round(row.passRate * 100)}%`} tone={row.passRate >= 0.8 ? 'success' : row.passRate >= 0.5 ? 'warning' : 'error'} />}
            />
          ))}
        </ListGroup>
      )}

      <SectionLabel title="최근 호출 30건" />
      {logs.length === 0 ? <Card><EmptyState icon="analytics" text="AI 호출 기록이 없습니다." /></Card> : null}
      {logs.slice(0, 30).map((row) => (
        <Card key={row.id} style={{ gap: 4 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <T variant="subtitle" style={{ flex: 1 }}>{AI_TYPE_LABEL[row.type] ?? row.type}</T>
            <Badge label={row.status === 'success' ? '성공' : '오류'} tone={row.status === 'success' ? 'success' : 'error'} />
          </View>
          <T variant="caption" tone="secondary">
            {[row.model, `${(row.latencyMs / 1000).toFixed(1)}초`, row.tokenIn !== undefined ? `토큰 ${row.tokenIn}/${row.tokenOut ?? 0}` : '', row.createdByName, fmt(row.createdAt)].filter(Boolean).join(' · ')}
          </T>
          {row.errorMessage ? <T variant="caption" tone="error" numberOfLines={3}>{row.errorMessage}</T> : null}
        </Card>
      ))}
    </Screen>
  );
}

// ── AI 어시스턴트 ──────────────────────────────────────

type Message = { role: 'user' | 'assistant'; content: string };

const EXAMPLES = ['오늘 결석한 학생 알려줘', '이번 주 지각이 잦은 학생은?', '설문 미응답자에게 알림 보내줘'];

export function AssistantPage() {
  const { user } = useSession();
  const { palette } = useTheme();
  const [text, setText] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [context, setContext] = useState('');
  const [actions, setActions] = useState<AssistantAction[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const job = useJob();

  const send = (input = text) => {
    const content = input.trim();
    if (!user || !content || busy) return;
    const next: Message[] = [...messages, { role: 'user', content }];
    setMessages(next);
    setText('');
    setError('');
    setBusy(true);
    askAssistant(next, context, user.cohortId)
      .then((result) => {
        setMessages([...next, { role: 'assistant', content: result.reply || '(응답이 비어 있습니다)' }]);
        setContext(result.context);
        setActions(result.actions);
      })
      .catch((err: unknown) => setError(errorText(err, '어시스턴트가 응답하지 못했습니다.')))
      .finally(() => setBusy(false));
  };

  const execute = (action: AssistantAction) => {
    if (!user) return;
    confirmAction('작업 실행', `${action.title ?? action.type}\n${action.targets?.length ? `대상 ${action.targets.length}명` : ''}`, () =>
      void job.run(async () => {
        await executeAssistant(action, user.cohortId);
        setActions((prev) => prev.filter((row) => row.id !== action.id));
        setMessages((prev) => [...prev, { role: 'assistant', content: `실행했습니다: ${action.title ?? action.type}` }]);
      }),
    '실행');
  };

  return (
    <Screen
      title="AI 어시스턴트"
      stickToBottom
      footer={<Composer value={text} onChangeText={setText} onSend={() => send()} busy={busy} placeholder="무엇을 도와드릴까요?" />}
    >
      {messages.length === 0 ? (
        <Card style={{ gap: 10 }}>
          <T variant="subtitle">출결 · 공지 · 알림을 말로 처리합니다</T>
          <Muted>실행이 필요한 작업은 확인을 받은 뒤에만 진행됩니다.</Muted>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
            {EXAMPLES.map((example) => <Chip key={example} label={example} onPress={() => send(example)} />)}
          </View>
        </Card>
      ) : null}
      {messages.map((message, index) => {
        const mine = message.role === 'user';
        return (
          <View
            key={index}
            style={{
              alignSelf: mine ? 'flex-end' : 'flex-start',
              maxWidth: '86%',
              borderRadius: 16,
              paddingHorizontal: 14,
              paddingVertical: 10,
              backgroundColor: mine ? palette.primary : palette.surface,
              borderWidth: mine ? 0 : 1,
              borderColor: palette.border,
            }}
          >
            <T style={{ color: mine ? '#fff' : palette.text }}>{message.content}</T>
          </View>
        );
      })}
      {busy ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <ActivityIndicator color={palette.primary} />
          <T tone="secondary">답변을 만드는 중…</T>
        </View>
      ) : null}
      {error ? (
        <Callout tone="error"><T tone="error">{error}</T></Callout>
      ) : null}
      <JobNotice notice={job.notice} />
      {actions.map((action) => (
        <Card key={action.id} style={{ gap: 6, borderColor: palette.primary }}>
          <T variant="label" tone="primary">실행할 작업</T>
          <T variant="subtitle">{action.title ?? action.type}</T>
          {action.content ? <T tone="secondary" numberOfLines={6}>{action.content}</T> : null}
          {action.targets?.length ? <T variant="caption" tone="secondary">대상: {action.targets.map((row) => row.name).join(', ')}</T> : null}
          <Actions>
            <Half><Btn label="건너뛰기" tone="ghost" onPress={() => setActions((prev) => prev.filter((row) => row.id !== action.id))} /></Half>
            <Half><Btn label="실행" disabled={job.busy} onPress={() => execute(action)} /></Half>
          </Actions>
        </Card>
      ))}
    </Screen>
  );
}

// ── 좌석 배치 ──────────────────────────────────────────

export function RoomsPage() {
  const { user } = useSession();
  const db = useDb();
  const { width } = useWindowDimensions();
  const [open, setOpen] = useState<string | null>(null);
  const rooms = (db?.seatingRooms ?? []).filter((room) => !user?.cohortId || room.cohortId === user.cohortId);
  const publishedId = user?.cohortId ? db?.seatingMeta?.[user.cohortId]?.publishedRoomId : undefined;
  return (
    <Screen title={navLabel(RoutePaths.adminSeating, '좌석 배치')} onRefresh={refreshBootstrap}>
      <Muted>배치 편집(자리 바꾸기 · 강의실 틀 만들기)은 넓은 화면이 필요해 PC 웹에서 합니다. 앱에서는 확인만 할 수 있습니다.</Muted>
      {rooms.length === 0 ? <Card><EmptyState icon="event-seat" text="등록된 강의실이 없습니다." /></Card> : null}
      {rooms.map((room) => {
        const assignment = (db?.seatingAssignments ?? []).find((row) => row.roomId === room.id);
        const seats = room.cells.filter((cell) => cell.type === 'seat').length;
        const assigned = Object.keys(assignment?.assignments ?? {}).length;
        const live = room.id === publishedId && assignment?.status === 'published';
        return (
          <Card key={room.id} style={{ gap: 8, paddingHorizontal: open === room.id ? 8 : 16 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: open === room.id ? 8 : 0 }}>
              <T variant="subtitle" style={{ flex: 1 }}>{room.roomNumber?.trim() || '강의실'}</T>
              {live ? <Badge label="학생에게 공개" tone="success" /> : <Badge label={assignment?.status === 'published' ? '확정' : '초안'} tone="neutral" />}
            </View>
            <T variant="caption" tone="secondary" style={{ paddingHorizontal: open === room.id ? 8 : 0 }}>
              좌석 {seats}석 · 배정 {assigned}명 · {room.rows}×{room.cols}
            </T>
            <Btn label={open === room.id ? '배치도 닫기' : '배치도 보기'} tone="soft" onPress={() => setOpen(open === room.id ? null : room.id)} />
            {open === room.id ? (
              <SeatGrid grid={room} seatUserIds={assignment?.assignments ?? {}} seatNames={assignment?.seatNames ?? {}} width={width - 32 - 16 - 2} />
            ) : null}
          </Card>
        );
      })}
      <Btn label="PC 웹에서 편집하기" icon="computer" tone="ghost" onPress={() => router.push('/(admin)/desktop/seating' as never)} />
    </Screen>
  );
}

// ── 팀 편성 ────────────────────────────────────────────

export function TeamEditPage() {
  const { user } = useSession();
  const cohortId = user?.cohortId ?? '';
  const teams = [...useTeams()].filter((team) => team.cohortId === cohortId).sort((a, b) => a.sortOrder - b.sortOrder);
  const students = useUsers()
    .filter((row) => row.role === 'student' && row.cohortId === cohortId && row.isActive !== false)
    .sort((a, b) => a.displayName.localeCompare(b.displayName, 'ko'));
  const job = useJob();
  const [picked, setPicked] = useState<string | null>(null);
  const [name, setName] = useState('');
  const nameOf = (uid: string) => students.find((row) => row.uid === uid)?.displayName ?? '알 수 없음';
  const assigned = new Set(teams.flatMap((team) => team.memberIds));
  const unassigned = students.filter((row) => !assigned.has(row.uid));
  const pickedTeam = teams.find((team) => picked !== null && team.memberIds.includes(picked));

  const payload = (list: typeof teams) =>
    list.map((team, index) => ({ id: team.id, name: team.name, memberIds: team.memberIds, sortOrder: index, colorIndex: team.colorIndex }));

  const commit = (list: typeof teams, deleteIds: string[] = [], success?: string) =>
    void job.run(async () => {
      await replaceTeams(cohortId, payload(list), deleteIds);
      setPicked(null);
    }, success);

  const moveTo = (teamId: string | null) => {
    if (!picked) return;
    commit(
      teams.map((team) => ({
        ...team,
        memberIds: team.id === teamId ? [...new Set([...team.memberIds, picked])] : team.memberIds.filter((id) => id !== picked),
      })),
    );
  };

  const create = () => {
    const title = name.trim() || `${teams.length + 1}팀`;
    if (teams.some((team) => team.name === title)) return job.fail('같은 이름의 팀이 있습니다.');
    void job.run(async () => {
      await replaceTeams(
        cohortId,
        [
          ...payload(teams.map((team) => ({ ...team, memberIds: team.memberIds.filter((id) => id !== picked) }))),
          { name: title, memberIds: picked ? [picked] : [], sortOrder: teams.length, colorIndex: teams.length % 8 },
        ],
        [],
      );
      setName('');
      setPicked(null);
    }, '팀을 만들었습니다.');
  };

  return (
    <Screen title="팀 편성" onRefresh={refreshBootstrap}>
      {!cohortId ? <Card><EmptyState icon="groups" text="기수를 먼저 선택해 주세요." /></Card> : null}
      <Muted>학생을 누른 뒤 넣을 팀의 「여기로」를 누르세요. 권장 인원은 4~5명입니다.</Muted>
      {picked ? (
        <Callout tone="info">
          <T variant="subtitle">선택: {nameOf(picked)}{pickedTeam ? ` (${pickedTeam.name})` : ' (미배정)'}</T>
          <Actions>
            {pickedTeam ? <Half><Btn label="팀에서 빼기" tone="ghost" disabled={job.busy} onPress={() => moveTo(null)} /></Half> : null}
            <Half><Btn label="선택 취소" tone="ghost" onPress={() => setPicked(null)} /></Half>
          </Actions>
        </Callout>
      ) : null}
      <JobNotice notice={job.notice} />

      <SectionLabel title={`미배정 ${unassigned.length}명`} />
      <Card>
        {unassigned.length === 0 ? <Muted>모든 학생이 팀에 배정되었습니다.</Muted> : (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
            {unassigned.map((row) => (
              <Chip key={row.uid} label={row.displayName} selected={picked === row.uid} onPress={() => setPicked(picked === row.uid ? null : row.uid)} />
            ))}
          </View>
        )}
      </Card>

      <SectionLabel title={`팀 ${teams.length}개`} />
      {teams.map((team) => {
        const size = team.memberIds.length;
        return (
          <Card key={team.id} style={{ gap: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <T variant="subtitle" style={{ flex: 1 }}>{team.name}</T>
              <Badge label={`${size}명`} tone={size >= 4 && size <= 5 ? 'success' : 'warning'} />
            </View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
              {size === 0 ? <Muted>아직 팀원이 없습니다.</Muted> : null}
              {team.memberIds.map((uid) => (
                <Chip key={uid} label={nameOf(uid)} selected={picked === uid} onPress={() => setPicked(picked === uid ? null : uid)} />
              ))}
            </View>
            <Actions>
              {picked && !team.memberIds.includes(picked) ? (
                <Half><Btn label={`${nameOf(picked)} 여기로`} disabled={job.busy} onPress={() => moveTo(team.id)} /></Half>
              ) : null}
              <Half>
                <Btn
                  label="팀 삭제"
                  tone="danger"
                  disabled={job.busy}
                  onPress={() =>
                    confirmAction('팀 삭제', `${team.name}을(를) 삭제할까요? 팀원은 미배정으로 돌아갑니다.`, () =>
                      commit(teams.filter((row) => row.id !== team.id), [team.id], '삭제했습니다.'),
                    )
                  }
                />
              </Half>
            </Actions>
          </Card>
        );
      })}

      <Card style={{ gap: 10 }}>
        <Field label="새 팀 이름" value={name} onChangeText={setName} placeholder={`${teams.length + 1}팀`} />
        <Btn label={picked ? `팀 만들고 ${nameOf(picked)} 넣기` : '팀 만들기'} icon="group-add" tone="soft" disabled={job.busy || !cohortId} onPress={create} />
      </Card>
    </Screen>
  );
}
