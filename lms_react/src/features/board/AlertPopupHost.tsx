import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import {
  dismissAlertToday,
  markAlertRead,
  refreshMyAlertPopups,
  useAlertPopups,
  useDb,
  useMyAttendanceRequests,
} from '../../data/repository';
import { dateKeyOf } from '../../data/seed';
import type { AttendanceIssue } from '../../domain/types';
import { useTour } from '../../tour/useTour';
import { Badge, Button, Dialog } from '../../ui/components';
import { RequestStatusLabels, RequestStatusTones, labelOf } from '../attendance/attendanceRequest';
import '../attendance/attendanceRequest.css';
import { useSession } from '../auth/session';

/**
 * 알림 팝업 — features/shell/widgets/alert_popup_host.dart
 *
 * 관리자가 띄운 팝업과 출결 신청 처리 결과를 학생에게 보여 준다. 「오늘 하루 보지 않기」는
 * 날짜별로 기억한다. 온보딩 투어가 떠 있는 동안은 투어가 끝난 뒤에 띄운다.
 * 관리자 · 강사는 「알림 팝업」 메뉴에서 보므로 여기서 띄우지 않는다.
 */
const SHOWN_KEY_PREFIX = 'lms_react_alert_shown:';
const RESULT_SEEN_PREFIX = 'lms_react_attendance_result_seen:';
/** 처음 쓰는 기기에서는 이보다 오래된 처리 결과를 다시 알리지 않는다 */
const RESULT_FRESH_MS = 3 * 24 * 60 * 60 * 1000;
/** 로그인해 둔 학생도 새 (지정) 알림 · 처리 결과를 받게, 화면이 보이는 동안 이 간격으로 다시 받는다 */
const POLL_MS = 60_000;
/** 노출 시작 · 종료 시각이 지나면 다시 그리게 */
const TICK_MS = 30_000;

function readJson<T>(storage: Storage, key: string, fallback: T): T {
  try {
    const raw = storage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

function writeJson(storage: Storage, key: string, value: unknown): void {
  try {
    storage.setItem(key, JSON.stringify(value));
  } catch {
    /* 무시 */
  }
}

/** 처리 결과 알림 — 요청 id → 알린 처리 시각. 한 번 없던 기기면 null */
function readSeenResults(uid: string): Record<string, string> | null {
  return readJson<Record<string, string> | null>(window.localStorage, `${RESULT_SEEN_PREFIX}${uid}`, null);
}

function unseenResults(requests: AttendanceIssue[], seen: Record<string, string> | null, now: Date): AttendanceIssue[] {
  return requests.filter((r) => {
    if (r.status === 'submitted' || r.reviewedAt === undefined) return false;
    if (seen === null) return now.getTime() - r.reviewedAt.getTime() < RESULT_FRESH_MS;
    return seen[r.id] !== r.reviewedAt.toISOString();
  });
}

export function AlertPopupHost() {
  const { user } = useSession();
  const tour = useTour();
  const popups = useAlertPopups();
  const dismissals = useDb((db) => (user === null ? {} : db.alertDismissals[user.uid] ?? {}));
  const requests = useMyAttendanceRequests(user?.uid ?? '');
  const [closed, setClosed] = useState<string[]>(() =>
    user === null ? [] : readJson<string[]>(window.sessionStorage, `${SHOWN_KEY_PREFIX}${user.uid}`, []),
  );
  const [seenResults, setSeenResults] = useState(() => (user === null ? null : readSeenResults(user.uid)));
  const [now, setNow] = useState(() => new Date());
  const navigate = useNavigate();
  const isStudent = user?.role === 'student';

  // 계정마다 따로 기억한다. (관리자가 닫은 기록이 학생에게 넘어가지 않게)
  useEffect(() => {
    if (user === null) {
      setClosed([]);
      setSeenResults(null);
      return;
    }
    setClosed(readJson<string[]>(window.sessionStorage, `${SHOWN_KEY_PREFIX}${user.uid}`, []));
    setSeenResults(readSeenResults(user.uid));
  }, [user?.uid]);

  useEffect(() => {
    if (!isStudent || import.meta.env.MODE === 'test') return;
    const poll = () => {
      if (document.visibilityState === 'visible') refreshMyAlertPopups().catch(() => undefined);
    };
    const timer = window.setInterval(poll, POLL_MS);
    document.addEventListener('visibilitychange', poll);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', poll);
    };
  }, [user?.uid, isStudent]);

  useEffect(() => {
    if (!isStudent) return;
    const timer = window.setInterval(() => setNow(new Date()), TICK_MS);
    return () => window.clearInterval(timer);
  }, [isStudent]);

  // 투어(z-index 1000)가 다이얼로그(900)를 가리므로, 투어가 끝난 뒤에만 띄운다.
  const tourBlocking = tour.active && tour.state !== null;

  if (user === null || !isStudent || tourBlocking) return null;

  const results = unseenResults(requests, seenResults, now);
  if (results.length > 0) {
    const markSeen = () => {
      const next: Record<string, string> = { ...(seenResults ?? {}) };
      requests.forEach((r) => {
        if (r.status !== 'submitted' && r.reviewedAt !== undefined) next[r.id] = r.reviewedAt.toISOString();
      });
      writeJson(window.localStorage, `${RESULT_SEEN_PREFIX}${user.uid}`, next);
      setSeenResults(next);
    };
    const rejected = results.some((r) => r.status === 'rejected');
    return (
      <Dialog
        title="출결 신청 처리 결과"
        onClose={markSeen}
        actions={
          <>
            <Button variant="text" onClick={markSeen}>
              확인
            </Button>
            <Button
              onClick={() => {
                markSeen();
                navigate(RoutePaths.attendanceRequest);
              }}
            >
              {rejected ? '고쳐서 다시 내기' : '출결 신청 보기'}
            </Button>
          </>
        }
      >
        <ul className="attendance-result-list">
          {results.map((r) => (
            <li key={r.id}>
              <div className="attendance-result-list__head">
                <strong>{r.dateKey}</strong>
                <span>{labelOf(r)}</span>
                <Badge tone={RequestStatusTones[r.status]}>{RequestStatusLabels[r.status]}</Badge>
              </div>
              {r.reviewComment && <p className="muted">매니저 메모: {r.reviewComment}</p>}
            </li>
          ))}
        </ul>
        <span className="hint">
          {rejected ? '반려된 신청은 고쳐서 다시 내면 매니저가 다시 확인합니다.' : '승인된 내용은 출석부에 반영됐습니다.'}
        </span>
      </Dialog>
    );
  }

  const today = dateKeyOf(now);
  const nowHm = now.toTimeString().slice(0, 5);

  const visible = popups
    .filter((p) => {
      if (!p.isActive) return false;
      if (p.endDate !== undefined && today > p.endDate) return false;
      if (dismissals[p.id] === today) return false;
      if (closed.includes(p.id)) return false;
      if (p.startTime !== undefined && nowHm < p.startTime) return false;
      if (p.endTime !== undefined && nowHm > p.endTime) return false;
      return true;
    })
    .sort((a, b) => a.sortOrder - b.sortOrder);

  const popup = visible[0];
  if (popup === undefined) return null;

  const closeOne = () => {
    markAlertRead(popup.id);
    setClosed((c) => {
      const next = [...c, popup.id];
      writeJson(window.sessionStorage, `${SHOWN_KEY_PREFIX}${user.uid}`, next);
      return next;
    });
  };

  return (
    <Dialog
      title={popup.title}
      onClose={closeOne}
      actions={
        <>
          <Button
            variant="text"
            onClick={() => {
              dismissAlertToday(user.uid, popup.id);
              closeOne();
            }}
          >
            오늘 하루 보지 않기
          </Button>
          <Button onClick={closeOne}>확인</Button>
        </>
      }
    >
      <p className="muted" style={{ whiteSpace: 'pre-wrap' }}>
        {popup.content}
      </p>
      {popup.linkUrl !== undefined &&
        (popup.linkUrl.startsWith('/') ? (
          <Button
            variant="outline"
            onClick={() => {
              closeOne();
              navigate(popup.linkUrl as string);
            }}
          >
            바로 가기
          </Button>
        ) : (
          <a href={popup.linkUrl} target="_blank" rel="noreferrer" onClick={() => markAlertRead(popup.id)}>
            자세히 보기
          </a>
        ))}
      <span className="hint">{popup.authorName}</span>
    </Dialog>
  );
}
