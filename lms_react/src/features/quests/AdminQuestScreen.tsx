import { useState } from 'react';

import {
  createQuest,
  reviewQuestSubmission,
  updateQuest,
  useQuestSubmissions,
  useQuests,
  type QuestDraft,
} from '../../data/repository';
import { readApiError } from '../../data/http';
import type { Quest, QuestApproval, QuestEvidenceType, QuestSubmission } from '../../domain/types';
import {
  Badge,
  Button,
  Checkbox,
  DataTable,
  Dialog,
  EmptyState,
  Field,
  Row,
  Select,
  TabPage,
  Tabs,
  TextArea,
  TextInput,
} from '../../ui/components';
import { Icon } from '../../ui/Icon';
import { formatDateTime, formatMileage } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { APPROVAL_LABEL, EVIDENCE_LABEL, STATUS_LABEL, STATUS_TONE, periodLabel } from './questLabels';

type Tab = 'quests' | 'review';

/** 관리자 마일리지 미션 — 등록 · 수정 · 마감, 제출 심사(승인하면 마일리지 자동 지급) */
export function AdminQuestScreen() {
  const user = useCurrentUser();
  const [tab, setTab] = useState<Tab>('quests');
  const quests = useQuests(user.cohortId);
  const pendingCount = (quests.data?.quests ?? []).reduce((sum, q) => sum + (q.counts?.pending ?? 0), 0);
  const [editing, setEditing] = useState<Quest | 'new' | null>(null);

  return (
    <TabPage
      title="마일리지 미션"
      description="기록실 기본 미션 외에 추가 미션을 만들고 학생 제출을 심사합니다. 승인되면 마일리지가 자동으로 지급돼요."
      actions={
        <Button icon={<Icon name="add" size={18} />} onClick={() => setEditing('new')}>
          마일리지 미션 추가
        </Button>
      }
      tabs={
        <Tabs
          active={tab}
          onChange={(id) => setTab(id as Tab)}
          items={[
            { id: 'quests', label: '미션 목록', count: quests.data?.quests.length ?? 0 },
            { id: 'review', label: '심사', count: pendingCount },
          ]}
        />
      }
    >
      {tab === 'quests' ? (
        <QuestList query={quests} onEdit={setEditing} />
      ) : (
        <ReviewPanel cohortId={user.cohortId} />
      )}
      {editing !== null && (
        <QuestDialog
          cohortId={user.cohortId}
          quest={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </TabPage>
  );
}

function QuestList({ query, onEdit }: { query: ReturnType<typeof useQuests>; onEdit(q: Quest): void }) {
  if (query.isLoading) return <p className="hint quest__pad">마일리지 미션을 불러오고 있어요…</p>;
  if (query.isError) return <p className="field__error quest__pad">마일리지 미션을 불러오지 못했습니다.</p>;
  const list = query.data?.quests ?? [];
  if (list.length === 0) return <EmptyState message="아직 추가한 마일리지 미션이 없습니다. 「마일리지 미션 추가」로 시작해 보세요." />;
  return (
    <DataTable
      rows={list}
      rowKey={(q) => q.id}
      onRowClick={onEdit}
      columns={[
        { key: 'title', header: '미션', render: (q) => <strong>{q.title}</strong> },
        { key: 'reward', header: '보상', width: '110px', render: (q) => formatMileage(q.reward) },
        { key: 'period', header: '기간', width: '200px', render: (q) => periodLabel(q) },
        {
          key: 'how',
          header: '인증 · 지급',
          width: '190px',
          render: (q) => `${EVIDENCE_LABEL[q.evidenceType]} · ${q.approval === 'auto' ? '즉시' : '승인 후'}`,
        },
        {
          key: 'counts',
          header: '완료 / 대기',
          width: '110px',
          align: 'center',
          render: (q) => `${q.counts?.approved ?? 0} / ${q.counts?.pending ?? 0}`,
        },
        {
          key: 'state',
          header: '상태',
          width: '100px',
          render: (q) =>
            q.closed ? (
              <Badge tone="neutral">마감</Badge>
            ) : !q.published ? (
              <Badge tone="warning">비공개</Badge>
            ) : q.open ? (
              <Badge tone="success">진행 중</Badge>
            ) : (
              <Badge tone="info">기간 외</Badge>
            ),
        },
      ]}
    />
  );
}

const EMPTY_DRAFT: QuestDraft = {
  title: '',
  description: '',
  reward: 10000,
  evidenceType: 'file',
  approval: 'manual',
  maxCompletions: 1,
  startOn: null,
  endOn: null,
  published: false,
  closed: false,
};

function QuestDialog({ cohortId, quest, onClose }: { cohortId: string; quest?: Quest; onClose(): void }) {
  const [draft, setDraft] = useState<QuestDraft>(() => (quest === undefined ? EMPTY_DRAFT : { ...quest }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const set = <K extends keyof QuestDraft>(key: K, value: QuestDraft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const granted = (quest?.counts?.approved ?? 0) > 0;

  const save = async () => {
    if (draft.title.trim() === '') return setError('제목을 적어 주세요.');
    if (draft.approval === 'auto' && draft.endOn === null) return setError('제출 즉시 지급 미션은 마감일을 꼭 정해 주세요.');
    setBusy(true);
    setError('');
    try {
      if (quest === undefined) await createQuest(cohortId, draft);
      else await updateQuest(quest.id, draft);
      onClose();
    } catch (e) {
      setError(await readApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      title={quest === undefined ? '마일리지 미션 추가' : '마일리지 미션 수정'}
      onClose={onClose}
      width={600}
      actions={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={() => void save()} disabled={busy}>
            {busy ? '저장 중…' : '저장'}
          </Button>
        </>
      }
    >
      <Field label="제목">
        <TextInput maxLength={100} value={draft.title} onChange={(e) => set('title', e.target.value)} />
      </Field>
      <Field label="설명" hint="무엇을 하면 되는지, 인증 방법을 적어 주세요">
        <TextArea rows={4} maxLength={3000} value={draft.description} onChange={(e) => set('description', e.target.value)} />
      </Field>
      <Row gap={12} wrap={false}>
        <Field label="보상 (M)" hint={granted ? '바꾸면 이후 지급분부터 적용돼요' : undefined}>
          <TextInput
            type="number"
            min={1}
            value={draft.reward}
            onChange={(e) => set('reward', Number(e.target.value))}
          />
        </Field>
        <Field label="받을 수 있는 횟수">
          <TextInput
            type="number"
            min={1}
            max={100}
            value={draft.maxCompletions}
            onChange={(e) => set('maxCompletions', Number(e.target.value))}
          />
        </Field>
      </Row>
      <Row gap={12} wrap={false}>
        <Field label="인증 방식">
          <Select value={draft.evidenceType} onChange={(e) => set('evidenceType', e.target.value as QuestEvidenceType)}>
            {(Object.keys(EVIDENCE_LABEL) as QuestEvidenceType[]).map((k) => (
              <option key={k} value={k}>
                {EVIDENCE_LABEL[k]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="완료 방식">
          <Select value={draft.approval} onChange={(e) => set('approval', e.target.value as QuestApproval)}>
            {(Object.keys(APPROVAL_LABEL) as QuestApproval[]).map((k) => (
              <option key={k} value={k}>
                {APPROVAL_LABEL[k]}
              </option>
            ))}
          </Select>
        </Field>
      </Row>
      <Row gap={12} wrap={false}>
        <Field label="시작일" hint="비우면 바로 시작">
          <TextInput
            type="date"
            value={draft.startOn ?? ''}
            onChange={(e) => set('startOn', e.target.value === '' ? null : e.target.value)}
          />
        </Field>
        <Field label="마감일" hint={draft.approval === 'auto' ? '즉시 지급은 필수' : '비우면 마감 없음'}>
          <TextInput
            type="date"
            value={draft.endOn ?? ''}
            onChange={(e) => set('endOn', e.target.value === '' ? null : e.target.value)}
          />
        </Field>
      </Row>
      <Row gap={16}>
        <Checkbox checked={draft.published} onChange={(v) => set('published', v)} label="학생에게 공개" />
        {quest !== undefined && (
          <Checkbox checked={draft.closed} onChange={(v) => set('closed', v)} label="마감(더 이상 제출 불가)" />
        )}
      </Row>
      {draft.approval === 'auto' && (
        <p className="hint">제출 즉시 지급은 검토 없이 마일리지가 들어갑니다. 횟수와 마감일을 꼭 확인해 주세요.</p>
      )}
      {error !== '' && <p className="field__error">{error}</p>}
    </Dialog>
  );
}

type ReviewFilter = 'pending' | 'approved' | 'rejected' | 'revoked' | '';

function ReviewPanel({ cohortId }: { cohortId: string }) {
  const [status, setStatus] = useState<ReviewFilter>('pending');
  const { data = [], isLoading, isError } = useQuestSubmissions(cohortId, status);
  const [acting, setActing] = useState<{ submission: QuestSubmission; decision: 'reject' | 'revoke' } | null>(null);
  const [busyId, setBusyId] = useState('');
  const [error, setError] = useState('');

  const approve = async (s: QuestSubmission) => {
    setBusyId(s.id);
    setError('');
    try {
      await reviewQuestSubmission(s.id, 'approve');
    } catch (e) {
      setError(await readApiError(e));
    } finally {
      setBusyId('');
    }
  };

  return (
    <div className="quest-review">
      <Row gap={12}>
        <Field label="상태">
          <Select value={status} onChange={(e) => setStatus(e.target.value as ReviewFilter)}>
            <option value="pending">검토 중</option>
            <option value="approved">완료</option>
            <option value="rejected">반려</option>
            <option value="revoked">승인 취소</option>
            <option value="">전체</option>
          </Select>
        </Field>
      </Row>
      {error !== '' && <p className="field__error">{error}</p>}
      {isLoading ? (
        <p className="hint quest__pad">제출을 불러오고 있어요…</p>
      ) : isError ? (
        <p className="field__error quest__pad">제출을 불러오지 못했습니다.</p>
      ) : (
        <DataTable
          rows={data}
          rowKey={(s) => s.id}
          empty={status === 'pending' ? '검토할 제출이 없습니다.' : '제출이 없습니다.'}
          columns={[
            { key: 'who', header: '학생', width: '110px', render: (s) => <strong>{s.studentName}</strong> },
            { key: 'quest', header: '미션', render: (s) => s.questTitle },
            { key: 'evidence', header: '인증', render: (s) => <Evidence submission={s} /> },
            { key: 'at', header: '제출', width: '150px', render: (s) => (s.submittedAt ? formatDateTime(new Date(s.submittedAt)) : '-') },
            {
              key: 'status',
              header: '상태',
              width: '150px',
              render: (s) => (
                <span className="quest-review__status">
                  <Badge tone={STATUS_TONE[s.status]}>{STATUS_LABEL[s.status]}</Badge>
                  {s.grantedAmount > 0 && <span className="hint">+{formatMileage(s.grantedAmount)}</span>}
                </span>
              ),
            },
            {
              key: 'act',
              header: '',
              width: '170px',
              align: 'right',
              render: (s) =>
                s.status === 'pending' ? (
                  <Row gap={6} wrap={false}>
                    <Button size="sm" disabled={busyId === s.id} onClick={() => void approve(s)}>
                      승인
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setActing({ submission: s, decision: 'reject' })}>
                      반려
                    </Button>
                  </Row>
                ) : s.status === 'approved' ? (
                  <Button size="sm" variant="outline" onClick={() => setActing({ submission: s, decision: 'revoke' })}>
                    승인 취소
                  </Button>
                ) : null,
            },
          ]}
        />
      )}
      {acting !== null && <DecisionDialog {...acting} onClose={() => setActing(null)} />}
    </div>
  );
}

function Evidence({ submission: s }: { submission: QuestSubmission }) {
  return (
    <div className="quest-evidence">
      {s.text !== '' && <p className="quest-evidence__text">{s.text}</p>}
      {s.link !== '' && (
        <a href={s.link} target="_blank" rel="noreferrer noopener">
          {s.link}
        </a>
      )}
      {s.files.map(
        (f, i) =>
          f.url !== null && (
            <a key={f.key} href={f.url} target="_blank" rel="noreferrer noopener">
              파일 {i + 1}
            </a>
          ),
      )}
      {s.text === '' && s.link === '' && s.files.length === 0 && <span className="hint">인증 없음</span>}
    </div>
  );
}

function DecisionDialog({
  submission,
  decision,
  onClose,
}: {
  submission: QuestSubmission;
  decision: 'reject' | 'revoke';
  onClose(): void;
}) {
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const reject = decision === 'reject';

  const run = async () => {
    if (reject && comment.trim() === '') return setError('반려 사유를 적어 주세요. 학생에게 보여요.');
    setBusy(true);
    setError('');
    try {
      await reviewQuestSubmission(submission.id, decision, comment);
      onClose();
    } catch (e) {
      setError(await readApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      title={reject ? '제출 반려' : '승인 취소'}
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            닫기
          </Button>
          <Button variant="danger" onClick={() => void run()} disabled={busy}>
            {reject ? '반려' : '승인 취소'}
          </Button>
        </>
      }
    >
      <p>
        {submission.studentName} · {submission.questTitle}
      </p>
      {!reject && (
        <p className="hint">
          지급한 {formatMileage(submission.grantedAmount)}을 회수합니다. 잔액이 부족하면 마이너스가 될 수 있어요.
        </p>
      )}
      <Field label={reject ? '반려 사유 (학생에게 보여요)' : '취소 사유 (선택)'}>
        <TextArea rows={3} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} />
      </Field>
      {error !== '' && <p className="field__error">{error}</p>}
    </Dialog>
  );
}
