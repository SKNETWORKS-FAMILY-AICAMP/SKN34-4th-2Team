import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { adminStudentDetailPath } from '../../app/routePaths';
import {
  createCounselNote,
  deleteCounselNote,
  updateCounselNote,
  useCohortCounselNotes,
  useStudentCounselNotes,
  useStudents,
  type CounselNoteDraft,
} from '../../data/repository';
import { readApiError } from '../../data/http';
import { dateKeyOf } from '../../data/seed';
import type { CounselCategory, CounselNote, User } from '../../domain/types';
import {
  Badge,
  Button,
  Card,
  Checkbox,
  DataTable,
  Dialog,
  EmptyState,
  Field,
  PageHeader,
  Row,
  Select,
  TextArea,
  TextInput,
} from '../../ui/components';
import { Icon } from '../../ui/Icon';
import { useCurrentUser } from '../auth/session';

const CATEGORY_LABEL: Record<CounselCategory, string> = {
  regular: '정기',
  adhoc: '수시',
  career: '진로',
  other: '기타',
};

const MAX_CONTENT_CHARS = 5000;

const nextRoundOf = (notes: CounselNote[]) => notes.reduce((max, n) => Math.max(max, n.round), 0) + 1;

/** 학생 상세의 「정기 상담」 — 그 학생의 기록을 차수 최신순으로 보고 쓴다 */
export function StudentCounselSection({ student }: { student: User }) {
  const { data: notes = [], isLoading, isError } = useStudentCounselNotes(student.uid);
  const [editing, setEditing] = useState<CounselNote | 'new' | null>(null);
  const [deleting, setDeleting] = useState<CounselNote | null>(null);
  const [error, setError] = useState('');

  const toggleFollowUp = async (note: CounselNote, done: boolean) => {
    try {
      setError('');
      await updateCounselNote(note.id, { followUpDone: done });
    } catch (e) {
      setError(await readApiError(e));
    }
  };

  const remove = async () => {
    if (deleting === null) return;
    try {
      await deleteCounselNote(deleting.id);
      setDeleting(null);
    } catch (e) {
      setError(await readApiError(e));
    }
  };

  return (
    <Card
      title="정기 상담"
      actions={
        <Button icon={<Icon name="edit_note" size={18} />} onClick={() => setEditing('new')}>
          상담 작성
        </Button>
      }
    >
      <p className="hint counsel__major">학력 / 전공: {student.educationMajor ?? '미입력'}</p>
      {error !== '' && <p className="field__error">{error}</p>}
      {isLoading ? (
        <p className="hint">상담 기록을 불러오고 있어요…</p>
      ) : isError ? (
        <p className="field__error">상담 기록을 불러오지 못했습니다.</p>
      ) : notes.length === 0 ? (
        <EmptyState message="아직 상담 기록이 없습니다." />
      ) : (
        <ul className="counsel-list">
          {notes.map((n) => (
            <li key={n.id} className="counsel-item">
              <header className="counsel-item__head">
                <strong>{n.round}차</strong>
                <span>{n.counseledOn}</span>
                <Badge tone={n.category === 'regular' ? 'primary' : 'neutral'}>{CATEGORY_LABEL[n.category]}</Badge>
                {n.counselorName !== '' && <span className="hint">상담 {n.counselorName}</span>}
                <span className="spacer" />
                <button type="button" className="icon-btn" aria-label="수정" title="수정" onClick={() => setEditing(n)}>
                  <Icon name="edit" size={18} />
                </button>
                <button type="button" className="icon-btn" aria-label="삭제" title="삭제" onClick={() => setDeleting(n)}>
                  <Icon name="delete" size={18} />
                </button>
              </header>
              <p className="counsel-item__content">{n.content}</p>
              {n.followUp !== '' && (
                <Checkbox
                  checked={n.followUpDone}
                  onChange={(done) => void toggleFollowUp(n, done)}
                  label={<span className={n.followUpDone ? 'counsel-item__done' : ''}>후속 조치: {n.followUp}</span>}
                />
              )}
              {n.nextOn !== null && <p className="hint">다음 상담 예정 {n.nextOn}</p>}
            </li>
          ))}
        </ul>
      )}

      {editing !== null && (
        <CounselNoteDialog
          uid={student.uid}
          note={editing === 'new' ? undefined : editing}
          nextRound={nextRoundOf(notes)}
          onClose={() => setEditing(null)}
        />
      )}
      {deleting !== null && (
        <Dialog
          title="상담 기록 삭제"
          onClose={() => setDeleting(null)}
          actions={
            <>
              <Button variant="outline" onClick={() => setDeleting(null)}>
                취소
              </Button>
              <Button variant="danger" onClick={() => void remove()}>
                삭제
              </Button>
            </>
          }
        >
          <p>
            {deleting.round}차({deleting.counseledOn}) 상담 기록을 삭제할까요? 되돌릴 수 없습니다.
          </p>
        </Dialog>
      )}
    </Card>
  );
}

function CounselNoteDialog({
  uid,
  note,
  nextRound,
  onClose,
}: {
  uid: string;
  note?: CounselNote;
  nextRound: number;
  onClose(): void;
}) {
  const [draft, setDraft] = useState<CounselNoteDraft>(() => ({
    round: note?.round ?? nextRound,
    counseledOn: note?.counseledOn ?? dateKeyOf(new Date()),
    category: note?.category ?? 'regular',
    content: note?.content ?? '',
    followUp: note?.followUp ?? '',
    followUpDone: note?.followUpDone ?? false,
    nextOn: note?.nextOn ?? null,
  }));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = <K extends keyof CounselNoteDraft>(key: K, value: CounselNoteDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));
  const rounds = Array.from({ length: Math.max(nextRound, draft.round) }, (_, i) => i + 1);

  const save = async () => {
    if ((draft.content ?? '').trim() === '') {
      setError('상담 내용을 입력해 주세요.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      if (note === undefined) await createCounselNote(uid, draft);
      else await updateCounselNote(note.id, draft);
      onClose();
    } catch (e) {
      setError(await readApiError(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      title={note === undefined ? '상담 작성' : '상담 수정'}
      onClose={onClose}
      width={560}
      actions={
        <>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            취소
          </Button>
          <Button onClick={() => void save()} disabled={saving}>
            {saving ? '저장 중…' : '저장'}
          </Button>
        </>
      }
    >
      <Row gap={12} wrap={false}>
        <Field label="차수">
          <Select value={draft.round} onChange={(e) => set('round', Number(e.target.value))}>
            {rounds.map((r) => (
              <option key={r} value={r}>
                {r}차
              </option>
            ))}
          </Select>
        </Field>
        <Field label="상담일">
          <TextInput type="date" value={draft.counseledOn} onChange={(e) => set('counseledOn', e.target.value)} />
        </Field>
        <Field label="유형">
          <Select value={draft.category} onChange={(e) => set('category', e.target.value as CounselCategory)}>
            {(Object.keys(CATEGORY_LABEL) as CounselCategory[]).map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABEL[c]}
              </option>
            ))}
          </Select>
        </Field>
      </Row>
      <Field label="상담 내용" hint={`${(draft.content ?? '').length} / ${MAX_CONTENT_CHARS}자`}>
        <TextArea
          rows={8}
          maxLength={MAX_CONTENT_CHARS}
          value={draft.content}
          onChange={(e) => set('content', e.target.value)}
        />
      </Field>
      <Field label="후속 조치" hint="비워 두면 후속 조치 없음">
        <TextInput maxLength={1000} value={draft.followUp} onChange={(e) => set('followUp', e.target.value)} />
      </Field>
      <Field label="다음 상담 예정일">
        <TextInput
          type="date"
          value={draft.nextOn ?? ''}
          onChange={(e) => set('nextOn', e.target.value === '' ? null : e.target.value)}
        />
      </Field>
      {error !== '' && <p className="field__error">{error}</p>}
    </Dialog>
  );
}

interface CounselRow {
  student: User;
  done?: CounselNote;
  last?: CounselNote;
  openFollowUps: number;
  nextOn: string | null;
}

/** 상담 현황 — 차수를 골라 기수 학생 중 누가 아직 상담을 안 받았는지 본다 */
export function AdminCounselScreen() {
  const user = useCurrentUser();
  const navigate = useNavigate();
  const students = useStudents(user.cohortId).filter((s) => s.isActive);
  const { data: notes = [], isLoading, isError } = useCohortCounselNotes(user.cohortId);
  const latestRound = notes.reduce((max, n) => Math.max(max, n.round), 0);
  const [picked, setPicked] = useState<number | null>(null);
  const [pendingOnly, setPendingOnly] = useState(false);
  const round = picked ?? Math.max(latestRound, 1);
  const rounds = Array.from({ length: Math.max(latestRound + 1, round) }, (_, i) => i + 1);

  const rows: CounselRow[] = students.map((student) => {
    const mine = notes.filter((n) => n.uid === student.uid);
    const today = dateKeyOf(new Date());
    const upcoming = mine.map((n) => n.nextOn).filter((d): d is string => d !== null && d >= today).sort();
    return {
      student,
      done: mine.find((n) => n.round === round),
      last: mine[0],
      openFollowUps: mine.filter((n) => n.followUp !== '' && !n.followUpDone).length,
      nextOn: upcoming[0] ?? null,
    };
  });
  const doneCount = rows.filter((r) => r.done !== undefined).length;
  const shown = pendingOnly ? rows.filter((r) => r.done === undefined) : rows;

  return (
    <div className="screen__inner">
      <PageHeader
        title="상담 현황"
        description="차수별로 정기 상담을 받은 학생과 아직 받지 않은 학생을 봅니다. 학생을 누르면 상담 기록으로 이동해요."
      />
      <Card>
        <Row gap={16}>
          <Field label="차수">
            <Select value={round} onChange={(e) => setPicked(Number(e.target.value))}>
              {rounds.map((r) => (
                <option key={r} value={r}>
                  {r}차
                </option>
              ))}
            </Select>
          </Field>
          <span className="counsel__progress">
            {round}차 완료 <strong>{doneCount}</strong> / {rows.length}명
          </span>
          <span className="spacer" />
          <Checkbox checked={pendingOnly} onChange={setPendingOnly} label="미상담만 보기" />
        </Row>
      </Card>
      <Card padded={false}>
        {isLoading ? (
          <p className="hint counsel__pad">상담 기록을 불러오고 있어요…</p>
        ) : isError ? (
          <p className="field__error counsel__pad">상담 기록을 불러오지 못했습니다.</p>
        ) : (
          <DataTable
            rows={shown}
            rowKey={(r) => r.student.uid}
            onRowClick={(r) => navigate(adminStudentDetailPath(r.student.uid))}
            empty={pendingOnly ? `${round}차 상담을 모두 마쳤습니다.` : '재원 중인 학생이 없습니다.'}
            columns={[
              { key: 'name', header: '학생', render: (r) => <strong>{r.student.displayName}</strong> },
              {
                key: 'major',
                header: '학력 / 전공',
                render: (r) => (
                  <span className="counsel__ellipsis" title={r.student.educationMajor}>
                    {r.student.educationMajor ?? '미입력'}
                  </span>
                ),
              },
              {
                key: 'round',
                header: `${round}차`,
                width: '130px',
                render: (r) =>
                  r.done === undefined ? <Badge tone="warning">미상담</Badge> : <Badge tone="success">{r.done.counseledOn}</Badge>,
              },
              { key: 'last', header: '마지막 상담', width: '120px', render: (r) => r.last?.counseledOn ?? '-' },
              {
                key: 'follow',
                header: '남은 후속 조치',
                width: '120px',
                align: 'center',
                render: (r) => (r.openFollowUps === 0 ? '-' : <Badge tone="error">{r.openFollowUps}건</Badge>),
              },
              { key: 'next', header: '다음 예정', width: '120px', render: (r) => r.nextOn ?? '-' },
            ]}
          />
        )}
      </Card>
    </div>
  );
}
