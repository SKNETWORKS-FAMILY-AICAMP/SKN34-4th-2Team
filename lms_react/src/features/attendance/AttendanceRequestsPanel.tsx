import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { useHolidays } from '../../data/holidays';
import {
  reviewAttendanceRequests,
  upsertAlertPopup,
  useAlertPopups,
  useAttendanceIssues,
  useDb,
  useSpotChecks,
} from '../../data/repository';
import { dateKeyOf } from '../../data/seed';
import { RoutePaths } from '../../app/routePaths';
import type { AttendanceIssue, AttendanceRequestStatus, User } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { Badge, Button, Chip, Dialog, Spacer, TextArea, TextInput } from '../../ui/components';
import { ExportMenu } from '../export/ExportMenu';
import { matchStudents } from '../manager/studentFilters';
import {
  RequestStatusLabels,
  RequestStatusTones,
  labelOf,
  requestsTable,
} from './attendanceRequest';
import './attendanceRequest.css';

type StatusFilter = 'all' | AttendanceRequestStatus;

const STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: 'submitted', label: '확인 대기' },
  { id: 'approved', label: '승인' },
  { id: 'rejected', label: '반려' },
  { id: 'all', label: '전체' },
];

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return dateKeyOf(d);
}

/** 미제출 학생에게 보내는 알림 — 같은 날 다시 누르면 새로 만들지 않고 이 알림의 대상에 합친다 */
const NUDGE_TITLE = '[출결] 오늘 출결 확인이 필요합니다';
/** 입실 기록은 수업 시작 뒤에야 뜻이 있다 */
const CLASS_START = '09:10';

/**
 * 출결 신청 확인(관리자 · 강사) — 학생이 LMS 에서 낸 예외 출결을 승인 · 반려한다.
 * 승인하면 그날 출석부 상태가 신청 내용(공가 · 결석 · 조퇴 · 지각 · 외출)으로 바뀐다.
 */
export function AttendanceRequestsPanel({
  reviewer,
  students,
}: {
  reviewer: User;
  students: User[];
}) {
  const all = useAttendanceIssues();
  const attendances = useDb((db) => db.attendances);
  const popups = useAlertPopups();
  const spotChecks = useSpotChecks(reviewer.cohortId);
  const today = dateKeyOf(new Date());
  const holidays = useHolidays(Number(today.slice(0, 4)));
  // 확인 대기는 날짜와 상관없이 다 보여야 미리 낸 공가 · 어제 신청이 묻히지 않는다
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [status, setStatus] = useState<StatusFilter>('submitted');
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const [rejecting, setRejecting] = useState<string[] | null>(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string; link?: boolean } | null>(null);

  const nameOf = useMemo(() => {
    const names = new Map(students.map((s) => [s.uid, s.displayName]));
    return (uid: string) => names.get(uid) ?? '(알 수 없음)';
  }, [students]);
  const studentIds = useMemo(() => new Set(students.map((s) => s.uid)), [students]);

  const inRange = all.filter(
    (r) => studentIds.has(r.userId) && (from === '' || r.dateKey >= from) && (to === '' || r.dateKey <= to),
  );
  const rangeLabel =
    from === '' && to === '' ? '전체 기간' : from === to ? from : `${from || '처음'} ~ ${to || '끝'}`;
  const setRange = (start: string, end: string) => {
    setFrom(start);
    setTo(end);
  };
  const q = query.trim();
  const rows = inRange
    .filter((r) => status === 'all' || r.status === status)
    .filter((r) => q === '' || nameOf(r.userId).includes(q))
    .sort((a, b) => b.dateKey.localeCompare(a.dateKey) || nameOf(a.userId).localeCompare(nameOf(b.userId), 'ko'));
  const countOf = (s: StatusFilter) => (s === 'all' ? inRange.length : inRange.filter((r) => r.status === s).length);

  const missing = matchStudents(students, ['missingCheckIn', 'missingAttendanceForm'], today, {
    attendances,
    issues: all,
    spotChecks,
  });
  const weekday = new Date().getDay();
  const offDay = weekday === 0 || weekday === 6 ? '주말' : holidays[today];
  const beforeClass = new Date().toTimeString().slice(0, 5) < CLASS_START;
  const sentToday = popups.find((p) => p.isActive && p.title === NUDGE_TITLE && p.endDate === today);
  const alreadyNudged = new Set(sentToday?.targetUserIds ?? []);
  const newTargets = missing.filter((s) => !alreadyNudged.has(s.uid));

  const shownIds = rows.map((r) => r.id);
  const pickedShown = picked.filter((id) => shownIds.includes(id));
  const allPicked = shownIds.length > 0 && pickedShown.length === shownIds.length;

  const run = (ids: string[], decision: AttendanceRequestStatus, note?: string) => {
    const withdrawing = decision === 'approved' ? 0 : all.filter((r) => ids.includes(r.id) && r.status === 'approved').length;
    if (
      withdrawing > 0 &&
      !window.confirm(`승인된 ${withdrawing}건의 승인을 거둡니다.\n그날 출석부 상태도 신청 전으로 돌아갑니다. 계속할까요?`)
    ) {
      return;
    }
    setBusy(true);
    setMessage(null);
    reviewAttendanceRequests(ids, decision, reviewer, note)
      .then(() => {
        setPicked((p) => p.filter((id) => !ids.includes(id)));
        const verb =
          decision === 'approved'
            ? '승인했습니다. 출석부에 반영했습니다'
            : decision === 'rejected'
              ? '반려했습니다'
              : '확인 대기로 되돌렸습니다';
        const restored = withdrawing > 0 ? ' 승인을 거둔 날은 출석부를 신청 전 상태로 돌렸습니다.' : '';
        setMessage({ tone: 'success', text: `${ids.length}건을 ${verb}.${restored}` });
      })
      .catch((err: unknown) =>
        setMessage({ tone: 'error', text: err instanceof Error ? err.message : '처리하지 못했습니다.' }),
      )
      .finally(() => setBusy(false));
  };

  const confirmReject = () => {
    if (rejecting === null) return;
    run(rejecting, 'rejected', comment);
    setRejecting(null);
    setComment('');
  };

  const nudge = () => {
    if (newTargets.length === 0) return;
    const names = newTargets.map((s) => s.displayName).join(', ');
    const warning = beforeClass ? `\n\n아직 ${CLASS_START} 전이라 입실 기록이 들어오기 전일 수 있습니다.` : '';
    const merge = sentToday !== undefined ? `\n\n오늘 이미 보낸 알림에 이 학생들을 더합니다.` : '';
    if (!window.confirm(`입실 기록도 출결 신청도 없는 ${newTargets.length}명에게 알림을 보낼까요?\n\n${names}${warning}${merge}`)) {
      return;
    }
    setBusy(true);
    setMessage(null);
    upsertAlertPopup(
      sentToday !== undefined
        ? { ...sentToday, targetUserIds: [...alreadyNudged, ...newTargets.map((s) => s.uid)] }
        : {
            id: '',
            title: NUDGE_TITLE,
            content:
              '오늘 입실 기록이 없습니다. 지각 · 외출 · 결석(공가 포함) 등 예외 출결이 있으면 「출결 신청」에서 신청해 주세요.',
            authorName: reviewer.displayName,
            isActive: true,
            sortOrder: 0,
            linkUrl: RoutePaths.attendanceRequest,
            endDate: today,
            targetUserIds: newTargets.map((s) => s.uid),
          },
    )
      .then(() =>
        setMessage({
          tone: 'success',
          text:
            sentToday !== undefined
              ? `오늘 보낸 알림에 ${newTargets.length}명을 더했습니다. 알림은 오늘 하루만 보입니다.`
              : `${newTargets.length}명에게 알림을 보냈습니다. 알림은 오늘 하루만 보입니다.`,
          link: true,
        }),
      )
      .catch((err: unknown) =>
        setMessage({ tone: 'error', text: err instanceof Error ? err.message : '알림을 보내지 못했습니다.' }),
      )
      .finally(() => setBusy(false));
  };

  const exportName = `출결신청_${from || '처음'}_${to || '끝'}`;

  const togglePick = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  return (
    <div className="att-requests" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="panel toolbar-card">
        <div className="att-requests__toolbar">
          <TextInput type="date" aria-label="시작일" style={{ width: 160 }} value={from} onChange={(e) => setFrom(e.target.value)} />
          <span className="hint">~</span>
          <TextInput type="date" aria-label="종료일" style={{ width: 160 }} value={to} onChange={(e) => setTo(e.target.value)} />
          <Chip selected={from === '' && to === ''} onClick={() => setRange('', '')}>
            전체 기간
          </Chip>
          <Chip selected={from === today && to === today} onClick={() => setRange(today, today)}>
            오늘
          </Chip>
          <Chip selected={from === today && to === ''} onClick={() => setRange(today, '')}>
            오늘 이후
          </Chip>
          <Chip selected={from === daysAgo(6) && to === today} onClick={() => setRange(daysAgo(6), today)}>
            최근 7일
          </Chip>
          <Chip selected={from === daysAgo(29) && to === today} onClick={() => setRange(daysAgo(29), today)}>
            최근 30일
          </Chip>
          <Spacer />
          <ExportMenu
            disabled={rows.length === 0}
            fileName={exportName}
            build={() => ({ ...requestsTable(rows, nameOf), title: `출결 신청 · ${rangeLabel}` })}
          />
        </div>
        <div className="att-requests__toolbar">
          {STATUS_FILTERS.map((f) => (
            <Chip key={f.id} selected={status === f.id} onClick={() => setStatus(f.id)}>
              {f.label} {countOf(f.id)}
            </Chip>
          ))}
          <span className="hint">{rangeLabel}</span>
          <Spacer />
          <TextInput
            aria-label="이름 검색"
            placeholder="이름 검색"
            style={{ width: 160 }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="panel toolbar-card">
        <div className="att-requests__toolbar">
          {offDay ? (
            <span className="hint">오늘은 {offDay}이라 입실 확인을 하지 않습니다.</span>
          ) : (
            <>
              <span>
                오늘 입실 기록도 출결 신청도 없는 학생 <strong>{missing.length}명</strong>
              </span>
              {missing.length > 0 && (
                <span className="hint" title={missing.map((s) => s.displayName).join(', ')}>
                  {missing.slice(0, 5).map((s) => s.displayName).join(', ')}
                  {missing.length > 5 ? ` 외 ${missing.length - 5}명` : ''}
                </span>
              )}
              {beforeClass && <Badge tone="warning">{CLASS_START} 전 — 입실 기록이 아직 없을 수 있어요</Badge>}
              <Spacer />
              {sentToday !== undefined && (
                <span className="hint">
                  오늘 {alreadyNudged.size}명에게 보냄 · 읽음 {sentToday.readBy?.length ?? 0}명
                </span>
              )}
              <Button size="sm" variant="outline" onClick={nudge} disabled={busy || newTargets.length === 0}>
                <Icon name="notifications" size={16} />
                {sentToday !== undefined && newTargets.length > 0
                  ? `새로 빠진 ${newTargets.length}명에게 알림`
                  : sentToday !== undefined
                    ? '모두 알림 받음'
                    : '이 학생들에게 알림'}
              </Button>
            </>
          )}
        </div>
      </div>

      {message !== null && (
        <div className={`callout callout--${message.tone === 'success' ? 'success' : 'error'}`} role="status">
          {message.text}
          {message.link && reviewer.role === 'admin' && (
            <>
              {' '}
              <Link to={RoutePaths.adminAlertPopups}>보낸 알림 보기</Link>
            </>
          )}
        </div>
      )}

      {pickedShown.length > 0 && (
        <div className="panel toolbar-card">
          <div className="att-requests__toolbar">
            <span>{pickedShown.length}건 선택</span>
            <Spacer />
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setRejecting(pickedShown)}>
              선택 반려
            </Button>
            <Button size="sm" disabled={busy} onClick={() => run(pickedShown, 'approved')}>
              선택 승인
            </Button>
          </div>
        </div>
      )}

      <div className="panel panel--flush">
        <table className="table att-table">
          <thead>
            <tr>
              <th style={{ width: 40 }}>
                <input
                  type="checkbox"
                  aria-label="모두 고르기"
                  checked={allPicked}
                  onChange={() => setPicked(allPicked ? picked.filter((id) => !shownIds.includes(id)) : [...new Set([...picked, ...shownIds])])}
                />
              </th>
              <th style={{ width: 110 }}>발생일</th>
              <th style={{ width: 100 }}>이름</th>
              <th style={{ width: 200 }}>신청</th>
              <th>사유</th>
              <th style={{ width: 110 }}>상태</th>
              <th style={{ width: 170 }} />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="hint" style={{ textAlign: 'center', padding: 24 }}>
                  조건에 맞는 신청이 없습니다.
                </td>
              </tr>
            )}
            {rows.map((r: AttendanceIssue) => (
              <tr key={r.id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`${nameOf(r.userId)} ${r.dateKey} 고르기`}
                    checked={picked.includes(r.id)}
                    onChange={() => togglePick(r.id)}
                  />
                </td>
                <td>{r.dateKey}</td>
                <td>
                  <strong>{nameOf(r.userId)}</strong>
                </td>
                <td>
                  {labelOf(r)}
                  {r.evidenceUrl && (
                    <a className="att-requests__review-note" href={r.evidenceUrl} target="_blank" rel="noreferrer">
                      <Icon name="attach_file" size={14} />
                      {r.evidenceName ?? '증빙'}
                    </a>
                  )}
                </td>
                <td className="att-requests__reason">{r.reason ?? <span className="hint">-</span>}</td>
                <td>
                  <Badge tone={RequestStatusTones[r.status]}>{RequestStatusLabels[r.status]}</Badge>
                  {r.reviewComment && <span className="hint att-requests__review-note">{r.reviewComment}</span>}
                </td>
                <td style={{ textAlign: 'right' }}>
                  {r.status === 'submitted' ? (
                    <>
                      <Button size="sm" variant="text" disabled={busy} onClick={() => setRejecting([r.id])}>
                        반려
                      </Button>
                      <Button size="sm" disabled={busy} onClick={() => run([r.id], 'approved')}>
                        승인
                      </Button>
                    </>
                  ) : (
                    <Button size="sm" variant="text" disabled={busy} onClick={() => run([r.id], 'submitted')}>
                      {r.status === 'approved' ? '승인 취소' : '반려 취소'}
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {rejecting !== null && (
        <Dialog
          title={`${rejecting.length}건 반려`}
          onClose={() => setRejecting(null)}
          actions={
            <>
              <Button variant="text" onClick={() => setRejecting(null)}>
                닫기
              </Button>
              <Button variant="danger" onClick={confirmReject}>
                반려하기
              </Button>
            </>
          }
        >
          <p className="muted">학생에게 반려 이유가 보입니다. 학생이 고쳐서 다시 낼 수 있습니다.</p>
          <TextArea
            rows={3}
            maxLength={500}
            aria-label="반려 이유"
            placeholder="예: 진단서를 함께 올려 주세요."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </Dialog>
      )}
    </div>
  );
}
