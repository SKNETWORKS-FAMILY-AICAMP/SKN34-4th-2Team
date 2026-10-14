import { useEffect, useMemo, useState, type HTMLAttributes } from 'react';

import {
  deleteSpotCheck,
  saveSpotCheck,
  usePublishedSeating,
  useSpotChecks,
  type SpotCheckDraft,
} from '../../data/repository';
import { dateKeyOf } from '../../data/seed';
import type { SeatPresenceState, SpotCheck, SpotCheckItem, SpotCheckPeriod, SpotCheckState, User } from '../../domain/types';
import { Badge, Button, Row, Select, Spacer, TextInput } from '../../ui/components';
import { formatDateTime } from '../../utils/format';
import { FitWidth, SeatGrid } from '../seating/SeatingScreen';
import { ExportMenu } from '../export/ExportMenu';
import { ABSENT_REASONS } from './spotCheckLabels';
import { SpotCheckPeriodLabels, spotChecksTable } from './studentFilters';
import './manager.css';

/**
 * 불시 자리 점검 — 매니저가 오전 · 오후에 불시에 돌며 학생마다 자리에 있는지(유/무) 적는다.
 * 저장하면 점검 시각 · 점검자와 함께 남고, 이력에서 Excel · CSV · Word · PDF 로 받는다.
 */

export { ABSENT_REASONS };

type Marks = Record<string, { state: SpotCheckState; reason?: string }>;

interface StoredDraft {
  id?: string;
  checkedAt: string;
  period: SpotCheckPeriod;
  periodTouched: boolean;
  note: string;
  marks: Marks;
}

const draftKey = (cohortId: string) => `lms_spot_check_draft:${cohortId}`;

function localInput(at: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

function periodOf(at: Date): SpotCheckPeriod {
  return at.getHours() < 13 ? 'am' : 'pm';
}

function freshDraft(): StoredDraft {
  const now = new Date();
  return { checkedAt: localInput(now), period: periodOf(now), periodTouched: false, note: '', marks: {} };
}

function draftFrom(check: SpotCheck): StoredDraft {
  const marks: Marks = {};
  for (const item of check.items) marks[item.userId] = { state: item.state, reason: item.reason };
  return {
    id: check.id,
    checkedAt: localInput(check.checkedAt),
    period: check.period,
    periodTouched: true,
    note: check.note ?? '',
    marks,
  };
}

function readDraft(cohortId: string): StoredDraft | null {
  try {
    const raw = window.localStorage.getItem(draftKey(cohortId));
    return raw === null ? null : (JSON.parse(raw) as StoredDraft);
  } catch {
    return null;
  }
}

/** 좌석 번호 — 확정된 배치에서 읽고, 없으면 학생 정보의 좌석 번호 */
export function useSeatLabel(cohortId: string, students: User[]) {
  const seating = usePublishedSeating(cohortId);
  return useMemo(() => {
    const seatOf = new Map(Object.entries(seating.assignment?.assignments ?? {}).map(([seat, uid]) => [uid, seat]));
    const numberOf = new Map(students.map((s) => [s.uid, s.seatNumber]));
    return (uid: string) => {
      const seat = seatOf.get(uid) ?? numberOf.get(uid);
      return seat === undefined ? '-' : `${seat}번`;
    };
  }, [seating.assignment, students]);
}

export function SpotCheckRunner({
  cohortId,
  checker,
  students,
  editing,
  onSaved,
  onCancelEdit,
}: {
  cohortId: string;
  checker: User;
  students: User[];
  /** 이력에서 「수정」으로 연 점검 */
  editing?: SpotCheck;
  onSaved(id: string): void;
  onCancelEdit(): void;
}) {
  const seating = usePublishedSeating(cohortId);
  const seatLabelOf = useSeatLabel(cohortId, students);
  const [draft, setDraft] = useState<StoredDraft>(() =>
    editing !== undefined ? draftFrom(editing) : (readDraft(cohortId) ?? freshDraft()),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(editing !== undefined ? draftFrom(editing) : (readDraft(cohortId) ?? freshDraft()));
    setError(null);
  }, [cohortId, editing]);

  // 새 점검은 중간에 화면을 떠나도 이어서 할 수 있게 기기에 적어 둔다
  useEffect(() => {
    if (draft.id !== undefined) return;
    try {
      window.localStorage.setItem(draftKey(cohortId), JSON.stringify(draft));
    } catch {
      /* 무시 */
    }
  }, [cohortId, draft]);

  const roll = useMemo(
    () => [...students].sort((a, b) => a.displayName.localeCompare(b.displayName, 'ko')),
    [students],
  );
  const marks = draft.marks;
  const present = roll.filter((s) => marks[s.uid]?.state === 'present').length;
  const absent = roll.filter((s) => marks[s.uid]?.state === 'absent').length;
  const unchecked = roll.length - present - absent;

  const setMark = (uid: string, state: SpotCheckState | null, reason?: string) =>
    setDraft((d) => {
      const next = { ...d.marks };
      if (state === null) delete next[uid];
      else next[uid] = { state, reason: state === 'absent' ? (reason ?? d.marks[uid]?.reason) : undefined };
      return { ...d, marks: next };
    });

  // 배치도 칸을 누르면 미확인 → 유 → 무 → 유 … 로 돈다
  const cycle = (uid: string) => setMark(uid, marks[uid]?.state === 'present' ? 'absent' : 'present');

  const seatAttrs = (seatId: string, occupied: boolean): HTMLAttributes<HTMLDivElement> => {
    const uid = seating.assignment?.assignments[seatId];
    if (!occupied || uid === undefined) return {};
    return {
      role: 'button',
      tabIndex: 0,
      className: 'spot-seat',
      onClick: () => cycle(uid),
      onKeyDown: (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          cycle(uid);
        }
      },
    };
  };

  const presenceOf = (uid: string): SeatPresenceState =>
    marks[uid]?.state === 'present' ? 'confirmed' : marks[uid]?.state === 'absent' ? 'held' : 'unknown';

  const onTimeChange = (value: string) =>
    setDraft((d) => {
      const at = new Date(value);
      return {
        ...d,
        checkedAt: value,
        period: d.periodTouched || Number.isNaN(at.getTime()) ? d.period : periodOf(at),
      };
    });

  const reset = () => {
    if (!window.confirm('이 점검에 적은 유/무를 모두 지울까요?')) return;
    const fresh = freshDraft();
    setDraft(draft.id === undefined ? fresh : { ...draft, marks: {} });
  };

  const save = () => {
    const at = new Date(draft.checkedAt);
    if (Number.isNaN(at.getTime())) {
      setError('점검 시각을 확인해 주세요.');
      return;
    }
    if (unchecked > 0) {
      setError(`아직 확인하지 않은 학생이 ${unchecked}명 있습니다. 「남은 학생 모두 유」를 누르거나 하나씩 표시해 주세요.`);
      return;
    }
    const items: SpotCheckItem[] = roll.map((s) => ({
      userId: s.uid,
      state: marks[s.uid].state,
      reason: marks[s.uid].state === 'absent' ? marks[s.uid].reason?.trim() || undefined : undefined,
    }));
    const payload: SpotCheckDraft = {
      id: draft.id,
      checkedAt: at,
      period: draft.period,
      note: draft.note.trim() || undefined,
      items,
    };
    setSaving(true);
    setError(null);
    saveSpotCheck(cohortId, payload, checker)
      .then((id) => {
        if (draft.id === undefined) {
          try {
            window.localStorage.removeItem(draftKey(cohortId));
          } catch {
            /* 무시 */
          }
          setDraft(freshDraft());
        }
        onSaved(id);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : '저장하지 못했습니다.'))
      .finally(() => setSaving(false));
  };

  return (
    <div className="spot-check">
      {draft.id !== undefined && (
        <div className="callout callout--warning">
          {formatDateTime(editing?.checkedAt)} 점검을 고치고 있습니다.
          <Button size="sm" variant="text" onClick={onCancelEdit}>
            새 점검으로
          </Button>
        </div>
      )}
      <div className="panel toolbar-card spot-check__toolbar">
        <label className="spot-check__field">
          <span className="hint">점검 시각</span>
          <TextInput type="datetime-local" value={draft.checkedAt} onChange={(e) => onTimeChange(e.target.value)} />
        </label>
        <Button
          size="sm"
          variant="text"
          onClick={() => setDraft((d) => ({ ...d, checkedAt: localInput(new Date()), period: d.periodTouched ? d.period : periodOf(new Date()) }))}
        >
          지금
        </Button>
        <label className="spot-check__field">
          <span className="hint">구분</span>
          <Select
            value={draft.period}
            onChange={(e) => setDraft((d) => ({ ...d, period: e.target.value as SpotCheckPeriod, periodTouched: true }))}
          >
            <option value="am">오전</option>
            <option value="pm">오후</option>
          </Select>
        </label>
        <label className="spot-check__field spot-check__field--grow">
          <span className="hint">메모</span>
          <TextInput
            value={draft.note}
            placeholder="예: 3교시 중 · 특강 진행 중"
            onChange={(e) => setDraft((d) => ({ ...d, note: e.target.value }))}
          />
        </label>
      </div>

      <Row gap={8}>
        <Badge tone="success">유 {present}</Badge>
        <Badge tone="warning">무 {absent}</Badge>
        <Badge tone="neutral">미확인 {unchecked}</Badge>
        <Spacer />
        <Button
          size="sm"
          variant="outline"
          disabled={unchecked === 0}
          onClick={() =>
            setDraft((d) => {
              const next = { ...d.marks };
              for (const s of roll) if (next[s.uid] === undefined) next[s.uid] = { state: 'present' };
              return { ...d, marks: next };
            })
          }
        >
          남은 학생 모두 유
        </Button>
        <Button size="sm" variant="text" onClick={reset}>
          초기화
        </Button>
        <Button size="sm" onClick={save} disabled={saving || roll.length === 0}>
          {saving ? '저장 중' : draft.id === undefined ? '점검 완료 · 저장' : '수정 저장'}
        </Button>
      </Row>
      {error !== null && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}

      <div className="spot-check__body">
        <section className="panel seat-panel">
          <header className="side-card__head">
            <h2 className="card__title">좌석 배치</h2>
            <span className="hint">칸을 누를 때마다 유 → 무로 바뀝니다</span>
          </header>
          {seating.room === undefined || !seating.published || seating.assignment === undefined ? (
            <p className="hint spot-check__empty">확정된 좌석 배치가 없습니다. 오른쪽 명단에서 표시해 주세요.</p>
          ) : (
            <FitWidth>
              <SeatGrid
                grid={seating.room}
                seatUserIds={seating.assignment.assignments}
                seatNames={seating.assignment.seatNames}
                presenceOf={presenceOf}
                presenceLabels={{ confirmed: '유', held: '무' }}
                seatAttrs={seatAttrs}
              />
            </FitWidth>
          )}
        </section>

        <section className="panel panel--flush spot-check__list">
          <table className="table">
            <thead>
              <tr>
                <th>이름</th>
                <th style={{ width: 64 }}>좌석</th>
                <th style={{ width: 112 }}>유/무</th>
                <th>사유(무)</th>
              </tr>
            </thead>
            <tbody>
              {roll.map((s) => {
                const mark = marks[s.uid];
                return (
                  <tr key={s.uid} className={mark === undefined ? 'spot-row--todo' : undefined}>
                    <td>{s.displayName}</td>
                    <td className="hint">{seatLabelOf(s.uid)}</td>
                    <td>
                      <div className="spot-toggle" role="group" aria-label={`${s.displayName} 유무`}>
                        <button
                          type="button"
                          className={`spot-toggle__btn${mark?.state === 'present' ? ' spot-toggle__btn--present' : ''}`}
                          aria-pressed={mark?.state === 'present'}
                          onClick={() => setMark(s.uid, mark?.state === 'present' ? null : 'present')}
                        >
                          유
                        </button>
                        <button
                          type="button"
                          className={`spot-toggle__btn${mark?.state === 'absent' ? ' spot-toggle__btn--absent' : ''}`}
                          aria-pressed={mark?.state === 'absent'}
                          onClick={() => setMark(s.uid, mark?.state === 'absent' ? null : 'absent')}
                        >
                          무
                        </button>
                      </div>
                    </td>
                    <td>
                      {mark?.state === 'absent' && (
                        <div className="spot-reason">
                          <Select
                            aria-label={`${s.displayName} 사유`}
                            value={ABSENT_REASONS.includes(mark.reason as (typeof ABSENT_REASONS)[number]) ? mark.reason : mark.reason ? '__custom' : ''}
                            onChange={(e) =>
                              setMark(s.uid, 'absent', e.target.value === '__custom' ? ' ' : e.target.value)
                            }
                          >
                            <option value="">사유 없음</option>
                            {ABSENT_REASONS.map((r) => (
                              <option key={r} value={r}>
                                {r}
                              </option>
                            ))}
                            <option value="__custom">직접 입력</option>
                          </Select>
                          {mark.reason !== undefined &&
                            mark.reason !== '' &&
                            !ABSENT_REASONS.includes(mark.reason as (typeof ABSENT_REASONS)[number]) && (
                              <TextInput
                                aria-label={`${s.displayName} 사유 직접 입력`}
                                value={mark.reason.trimStart()}
                                maxLength={100}
                                placeholder="사유"
                                onChange={(e) => setMark(s.uid, 'absent', e.target.value || ' ')}
                              />
                            )}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}

export function SpotCheckHistory({
  cohortId,
  cohortName,
  students,
  onEdit,
}: {
  cohortId: string;
  cohortName: string;
  students: User[];
  onEdit(check: SpotCheck): void;
}) {
  const checks = useSpotChecks(cohortId);
  const seatLabelOf = useSeatLabel(cohortId, students);
  const nameOf = useMemo(() => new Map(students.map((s) => [s.uid, s.displayName])), [students]);
  const [to, setTo] = useState(() => dateKeyOf(new Date()));
  const [from, setFrom] = useState(() => dateKeyOf(new Date(Date.now() - 6 * 86_400_000)));
  const [error, setError] = useState<string | null>(null);

  const shown = checks
    .filter((c) => {
      const key = dateKeyOf(c.checkedAt);
      return key >= from && key <= to;
    })
    .sort((a, b) => b.checkedAt.getTime() - a.checkedAt.getTime());

  const exportProps = (list: SpotCheck[], label: string) => ({
    fileName: `불시점검_${cohortName || cohortId}_${label}`,
    build: () => {
      const table = spotChecksTable(list, students, seatLabelOf);
      return { ...table, title: `${table.title} · ${cohortName || cohortId} · ${label}` };
    },
  });

  const remove = (check: SpotCheck) => {
    if (!window.confirm(`${formatDateTime(check.checkedAt)} 점검 기록을 지울까요? 되돌릴 수 없습니다.`)) return;
    setError(null);
    deleteSpotCheck(check.id).catch((err: unknown) => setError(err instanceof Error ? err.message : '지우지 못했습니다.'));
  };

  return (
    <div className="spot-check">
      <div className="panel toolbar-card spot-check__toolbar">
        <label className="spot-check__field">
          <span className="hint">시작일</span>
          <TextInput type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="spot-check__field">
          <span className="hint">종료일</span>
          <TextInput type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} />
        </label>
        <Spacer />
        <ExportMenu label="기간 전체 내려받기" disabled={shown.length === 0} {...exportProps(shown, `${from}~${to}`)} />
      </div>
      {error !== null && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}

      {shown.length === 0 ? (
        <p className="panel panel--empty hint">이 기간에 저장된 점검이 없습니다.</p>
      ) : (
        <ul className="spot-history">
          {shown.map((check) => {
            const absentItems = check.items.filter((i) => i.state === 'absent');
            return (
              <li key={check.id} className="panel spot-history__item">
                <Row gap={8}>
                  <strong>{formatDateTime(check.checkedAt)}</strong>
                  <Badge tone="info">{SpotCheckPeriodLabels[check.period]}</Badge>
                  <Badge tone="success">유 {check.items.length - absentItems.length}</Badge>
                  <Badge tone="warning">무 {absentItems.length}</Badge>
                  {check.checkedByName !== undefined && <span className="hint">점검 {check.checkedByName}</span>}
                  <Spacer />
                  <ExportMenu {...exportProps([check], dateKeyOf(check.checkedAt))} />
                  <Button size="sm" variant="outline" onClick={() => onEdit(check)}>
                    수정
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => remove(check)}>
                    삭제
                  </Button>
                </Row>
                {check.note !== undefined && <p className="hint">메모: {check.note}</p>}
                {absentItems.length > 0 ? (
                  <p className="spot-history__absent">
                    {absentItems
                      .map((i) => `${nameOf.get(i.userId) ?? '(퇴소)'}${i.reason ? `(${i.reason})` : ''}`)
                      .join(' · ')}
                  </p>
                ) : (
                  <p className="hint">모두 자리에 있었습니다.</p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
