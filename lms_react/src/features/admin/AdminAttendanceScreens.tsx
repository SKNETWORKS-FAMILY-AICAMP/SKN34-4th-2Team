import { useState } from 'react';

import {
  createNotice,
  fillCheckIn,
  fillCheckOut,
  setAttendanceStatus,
  useAttendanceByDate,
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
import { Select } from '../../ui/components';
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

/** 좌석 배치 — features/seating/AdminSeatingScreen.tsx 로 옮겼다. */
export { AdminSeatingScreen } from '../seating/AdminSeatingScreen';

/** 자리 확인(관리자) — 강사 화면과 같은 일을 한다. */
export { InstructorAttendanceScreen as AdminSeatPresenceScreen } from '../instructor/InstructorAttendanceScreen';

export { attendanceLabel };
