import { useState } from 'react';

import {
  createNotice,
  fillCheckIn,
  fillCheckOut,
  publishSeating,
  setAttendanceStatus,
  useAttendanceByDate,
  useSeating,
  useStudents,
} from '../../data/repository';
import { dateKeyOf } from '../../data/seed';
import {
  AttendanceColorVars,
  AttendanceForm,
  AttendanceLabels,
  AttendanceStatuses,
  attendanceLabel,
} from '../../domain/constants';
import type { AttendanceStatusCode } from '../../domain/types';
import { AdminTargets } from '../../tour/targets';
import { useTourTarget } from '../../tour/useTourTarget';
import { Icon } from '../../ui/Icon';
import {
  Badge,
  Button,
  Dialog,
  Select,
  Spacer,
} from '../../ui/components';
import { SeatGrid } from '../seating/SeatingScreen';
import { useCurrentUser } from '../auth/session';

/** 출석 관리 — features/admin/presentation/admin_attendance_screen.dart */
export function AdminAttendanceScreen() {
  const user = useCurrentUser();
  const students = useStudents(user.cohortId).filter((s) => s.isActive);
  const noticeRef = useTourTarget(AdminTargets.attendanceDailyNotice);

  const [dateKey, setDateKey] = useState(() => dateKeyOf(new Date()));
  const [query, setQuery] = useState('');
  const [posted, setPosted] = useState(false);
  const rows = useAttendanceByDate(dateKey);

  const rowOf = (uid: string) => rows.find((a) => a.userId === uid);
  const count = (status: string) => rows.filter((a) => a.status === status).length;
  const unrecorded = students.filter((s) => rowOf(s.uid)?.status === undefined).length;

  const q = query.trim();
  const shown = q === '' ? students : students.filter((s) => s.displayName.includes(q));

  const postDailyNotice = () => {
    createNotice({
      title: AttendanceForm.dailyNoticeTitle,
      content: `${AttendanceForm.dailyNoticeContent}\n\n${AttendanceForm.url}`,
      authorName: user.displayName,
      authorId: user.uid,
      isFavorite: true,
      priority: 1,
      channelLabel: '출결',
    });
    setPosted(true);
  };

  return (
    <div className="admin-page admin-page--wide">
      <h1 className="admin-page__title">{user.cohortName}</h1>
      <p className="admin-page__desc">
        고용24 입퇴실은 예시 데이터입니다. 지각·조퇴·외출·결석·공가는 당일 구글폼 선택값이 반영됩니다.
      </p>

      {posted && (
        <div className="callout callout--success">오늘 출결 폼 공지를 게시판에 올렸습니다.</div>
      )}

      {/* 날짜와 한 번에 채우는 단추들 */}
      <div className="panel toolbar-card">
        <input
          className="input"
          type="date"
          style={{ width: 170 }}
          value={dateKey}
          onChange={(e) => setDateKey(e.target.value)}
        />
        <button
          type="button"
          className="btn btn--text btn--sm"
          onClick={() => setDateKey(dateKeyOf(new Date()))}
        >
          오늘
        </button>
        <button
          type="button"
          className="btn btn--filled btn--md"
          onClick={() => students.forEach((s) => fillCheckIn(s.uid, dateKey))}
        >
          <Icon name="login" size={18} />
          예시 입실 채우기
        </button>
        <button
          type="button"
          className="btn btn--filled btn--md"
          onClick={() => students.forEach((s) => fillCheckOut(s.uid, dateKey))}
        >
          <Icon name="logout" size={18} />
          예시 퇴실 채우기
        </button>
        <button type="button" className="btn btn--outline btn--md" ref={noticeRef} onClick={postDailyNotice}>
          <Icon name="campaign" size={18} />
          매일 08:30 공지 등록
        </button>
      </div>

      {/* 상태별 숫자와 이름 검색 */}
      <div className="panel toolbar-card toolbar-card--stack">
        <div className="count-chips">
          <span className="count-chip">전체 {students.length}</span>
          {AttendanceStatuses.map((status) => (
            <span
              key={status}
              className="count-chip"
              style={{
                color: AttendanceColorVars[status],
                borderColor: AttendanceColorVars[status],
                background: `color-mix(in srgb, ${AttendanceColorVars[status]} 10%, transparent)`,
              }}
            >
              {AttendanceLabels[status]} {count(status)}
            </span>
          ))}
          <span className="count-chip count-chip--none">미기록 {unrecorded}</span>
        </div>

        <label className="study-search">
          <Icon name="search" size={20} />
          <input
            className="study-search__input"
            value={query}
            placeholder="이름 검색"
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      </div>

      <div className="panel panel--flush">
        <table className="table att-table">
          <thead>
            <tr>
              <th>이름</th>
              <th style={{ width: 110 }}>입실</th>
              <th style={{ width: 110 }}>퇴실</th>
              <th style={{ width: 200 }}>폼</th>
              <th style={{ width: 150 }}>최종 상태</th>
              <th style={{ width: 110 }}>출처</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((s) => {
              const row = rowOf(s.uid);
              const form = [
                row?.formAttendanceType,
                row?.officialLeaveUsed === true ? (row.officialLeaveType ?? '기타') : undefined,
              ]
                .filter((v): v is string => v !== undefined && v !== '')
                .join(' · ');
              return (
                <tr key={s.uid}>
                  <td>
                    <strong>{s.displayName}</strong>
                  </td>
                  <td className="hint">{row?.checkInTime ?? '-'}</td>
                  <td className="hint">{row?.checkOutTime ?? '-'}</td>
                  <td className="hint">{form === '' ? '-' : form}</td>
                  <td>
                    <Select
                      value={row?.status ?? ''}
                      onChange={(e) =>
                        setAttendanceStatus(
                          s.uid,
                          dateKey,
                          (e.target.value || undefined) as AttendanceStatusCode,
                        )
                      }
                    >
                      <option value="">미기록</option>
                      {AttendanceStatuses.map((status) => (
                        <option key={status} value={status}>
                          {AttendanceLabels[status]}
                        </option>
                      ))}
                    </Select>
                  </td>
                  <td className="hint">
                    {row?.statusSource === 'form'
                      ? '구글폼'
                      : row?.statusSource === 'manual'
                        ? '수동'
                        : '-'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** 좌석 배치 — features/seating/presentation/admin_seating_screen.dart */
export function AdminSeatingScreen() {
  const user = useCurrentUser();
  const seating = useSeating();
  const students = useStudents(user.cohortId).filter((s) => s.isActive);
  const [draft, setDraft] = useState(() =>
    seating.seats.map((s) => ({ seatNumber: s.seatNumber, userId: s.userId })),
  );
  const [picking, setPicking] = useState<number | null>(null);
  const [saved, setSaved] = useState(false);
  const [tab, setTab] = useState<'frame' | 'teams' | 'assign'>('frame');

  const nameOf = (uid?: string) => students.find((s) => s.uid === uid)?.displayName;

  const assign = (seatNumber: number, uid: string | undefined) => {
    setDraft((rows) =>
      rows.map((r) =>
        r.seatNumber === seatNumber
          ? { ...r, userId: uid }
          : // 한 학생이 두 자리에 앉을 수는 없다. 옮기면 원래 자리는 빈다.
            r.userId === uid && uid !== undefined
            ? { ...r, userId: undefined }
            : r,
      ),
    );
    setPicking(null);
  };

  const unassigned = students.filter((s) => !draft.some((d) => d.userId === s.uid));

  const publish = () => {
    publishSeating(
      draft.map((d) => ({
        seatNumber: d.seatNumber,
        userId: d.userId,
        userDisplayName: nameOf(d.userId),
      })),
    );
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="seat-admin">
      <header className="seat-admin__bar">
        <h1>좌석 배치 · {user.cohortName}</h1>
        <div className="seat-admin__tabs">
          {(
            [
              ['frame', '좌석 틀 설정'],
              ['teams', '프로젝트 팀'],
              ['assign', '배치 편집'],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`pill${tab === id ? ' pill--on' : ''}`}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </header>

      <div className="seat-admin__body">
        {saved && (
          <div className="callout callout--success">
            좌석 배치를 게시했습니다. 학생 화면에 바로 보입니다.
          </div>
        )}

        {tab === 'frame' && (
          <>
            <p className="seat-admin__note">
              위에서 편집할 강의실을 고른 뒤, {seating.rows}×{seating.cols} 그리드에
              강사석·출입문·테이블을 배치하세요. 학생 배치는「배치 편집」에서 합니다.
            </p>
            <div className="seat-admin__room">
              <Icon name="meeting_room" size={20} />
              <span>{seating.roomNumber ?? '강의실 미지정'} · 좌석 {seating.seats.length}석</span>
              <span className="spacer" />
              <Button>새 강의실</Button>
            </div>
            <SeatGrid layout={seating} />
          </>
        )}

        {tab === 'teams' && (
          <p className="seat-admin__note">프로젝트 팀 편성은 아직 준비 중입니다.</p>
        )}

        {tab === 'assign' && (
          <>
            <div className="seat-admin__actions">
              <strong>미배정 학생 {unassigned.length}명</strong>
              {unassigned.map((s) => (
                <span key={s.uid} className="chip">
                  {s.displayName}
                </span>
              ))}
              <span className="spacer" />
              <Button
                variant="outline"
                onClick={() =>
                  setDraft(seating.seats.map((x) => ({ seatNumber: x.seatNumber, userId: x.userId })))
                }
              >
                되돌리기
              </Button>
              <Button onClick={publish}>배치 게시</Button>
            </div>

            <div className="seatmap seat-admin__map">
              <p className="seatmap__hint">▲ 강사석 방향</p>
              <div
                className="seatmap__grid"
                style={{ gridTemplateColumns: `repeat(${seating.cols}, var(--seat-w))` }}
              >
                {seating.cells.map((cell) => {
                  if (cell.type !== 'seat') {
                    return (
                      <div
                        key={`${cell.row}-${cell.col}`}
                        className={`seat-fixture seat-fixture--${cell.type}`}
                        style={{ gridRow: cell.row + 1, gridColumn: cell.col + 1 }}
                      />
                    );
                  }
                  const seatNumber = Number(cell.label);
                  const uid = draft.find((d) => d.seatNumber === seatNumber)?.userId;
                  return (
                    <button
                      key={`${cell.row}-${cell.col}`}
                      type="button"
                      className={`seat${uid === undefined ? ' seat--empty' : ''}`}
                      style={{ gridRow: cell.row + 1, gridColumn: cell.col + 1 }}
                      onClick={() => setPicking(seatNumber)}
                    >
                      <span className="seat__no">{seatNumber}번</span>
                      <span className="seat__name">{nameOf(uid) ?? '—'}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>

      {picking !== null && (
        <Dialog title={`${picking}번 좌석 배정`} onClose={() => setPicking(null)}>
          <Button variant="outline" onClick={() => assign(picking, undefined)}>
            비우기
          </Button>
          <ul className="list">
            {students.map((s) => (
              <li key={s.uid} className="list__item">
                <span>{s.displayName}</span>
                <Spacer />
                {draft.some((d) => d.userId === s.uid) && <Badge tone="neutral">배정됨</Badge>}
                <Button size="sm" onClick={() => assign(picking, s.uid)}>
                  배정
                </Button>
              </li>
            ))}
          </ul>
        </Dialog>
      )}
    </div>
  );
}

/** 자리 확인(관리자) — 강사 화면과 같은 일을 한다. */
export { InstructorAttendanceScreen as AdminSeatPresenceScreen } from '../instructor/InstructorAttendanceScreen';

export { attendanceLabel };
