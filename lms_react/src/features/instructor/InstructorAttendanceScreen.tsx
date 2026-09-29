import { useEffect, useRef, useState, type CSSProperties } from 'react';

import {
  setSeatPresence,
  useAttendanceByDate,
  usePublishedSeating,
  useSeatPresence,
  useStudents,
} from '../../data/repository';
import { dateKeyOf } from '../../data/seed';
import { ClassPeriods, attendanceLabel, currentPeriod, nearestPeriod } from '../../domain/constants';
import type { SeatPresenceState, User } from '../../domain/types';
import { InstructorTargets } from '../../tour/targets';
import { useTourTarget } from '../../tour/useTourTarget';
import { Icon } from '../../ui/Icon';
import { Badge } from '../../ui/components';
import { PanelHandle, useStoredSize } from '../resume/ResumeEditScreen';
import { FitWidth, SeatGrid } from '../seating/SeatingScreen';
import { useCurrentUser } from '../auth/session';

/**
 * 자리 확인 — features/instructor/presentation/instructor_attendance_screen.dart
 *
 * 왼쪽에 좌석 배치도, 오른쪽에 호명 순서 목록과 보류 명단을 둔다. 출석 상태는
 * 건드리지 않고 확인·보류만 남긴다. 관리자의 자리 확인도 같은 화면이다.
 */

/** 오른쪽 열(호명 목록·보류) 폭과 보류 카드 높이. 손잡이로 바꾼 크기는 다음에도 쓴다. */
const ROLL_SIDE = {
  initialWidth: 220,
  minWidth: 220,
  maxWidth: 420,
  /** 배치도가 이보다 좁아지게는 못 넓힌다 */
  minSeatWidth: 400,
  handle: 28,
  minHeldHeight: 90,
  /** 보류 카드를 키워도 목록은 이만큼 남긴다 */
  minListHeight: 160,
} as const;

export function InstructorAttendanceScreen() {
  const user = useCurrentUser();
  const students = useStudents(user.cohortId).filter((s) => s.isActive);
  const seating = usePublishedSeating(user.cohortId);
  const summaryRef = useTourTarget(InstructorTargets.attendanceSummary);
  const confirmRef = useTourTarget(InstructorTargets.attendanceConfirm);

  const [dateKey, setDateKey] = useState(() => dateKeyOf(new Date()));
  const [periodId, setPeriodId] = useState(() => nearestPeriod().id);
  const [index, setIndex] = useState(0);
  const [rotated, setRotated] = useState(false);
  const [markError, setMarkError] = useState(false);
  const rollRef = useRef<HTMLDivElement>(null);
  const sideRef = useRef<HTMLDivElement>(null);
  const heldRef = useRef<HTMLElement>(null);
  const listRef = useRef<HTMLOListElement>(null);
  const [sideWidth, setSideWidth] = useStoredSize('instructor_roll_side_width', ROLL_SIDE.initialWidth);
  // 0 이면 보류 카드는 내용만큼(최대 45%)
  const [heldHeight, setHeldHeight] = useStoredSize('instructor_roll_held_height', 0);

  const period = Number(periodId);
  const presence = useSeatPresence(dateKey, period);
  const attendance = useAttendanceByDate(dateKey);
  const running = currentPeriod();

  const stateOf = (uid: string): SeatPresenceState =>
    presence.find((p) => p.userId === uid)?.state ?? 'unknown';

  // 호명은 이름 차례대로. 좌석 순서로 부르면 옆자리가 비었을 때 헷갈린다.
  const roll = [...students].sort((a, b) => a.displayName.localeCompare(b.displayName, 'ko'));
  const current = roll[Math.min(index, roll.length - 1)];
  const confirmed = roll.filter((s) => stateOf(s.uid) === 'confirmed');
  const held = roll.filter((s) => stateOf(s.uid) === 'held');

  // 저장을 기다리지 않고 바로 다음 학생으로 넘어간다. 화면에는 먼저 반영되고, 실패하면 되돌아가며 알린다.
  const mark = (student: User, state: SeatPresenceState, advance = true) => {
    setMarkError(false);
    if (advance) setIndex((i) => Math.min(i + 1, roll.length - 1));
    setSeatPresence(dateKey, period, student.uid, state).catch(() => setMarkError(true));
  };

  // 다음 학생으로 넘어가면 목록 위에서 두 번째 줄에 오게 굴린다. 방금 처리한 학생이 바로 위에 보인다.
  useEffect(() => {
    const list = listRef.current;
    const item = list?.children[index] as HTMLElement | undefined;
    if (list === null || item === undefined) return;
    const prev = item.previousElementSibling as HTMLElement | null;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    list.scrollTo({ top: Math.max(0, item.offsetTop - (prev?.offsetHeight ?? 0)), behavior: reduce ? 'auto' : 'smooth' });
  }, [index]);

  // 좌석 번호는 확정된 배치에서 읽는다. 자리를 옮기면 여기도 따라 바뀐다.
  const seatLabelOf = (uid: string | undefined) => {
    const entry = Object.entries(seating.assignment?.assignments ?? {}).find(([, u]) => u === uid);
    return entry === undefined ? '좌석 없음' : `${entry[0]}번`;
  };

  return (
    <div className="screen__inner">
      <header className="page-head">
        <div>
          <h1 className="page-head__title">자리 확인</h1>
          <p className="page-head__desc">
            {user.cohortName} · 교시마다 자리에 있는지 확인합니다. 학생 조작은 없고, 확인·보류만 기록됩니다.
            (출석 상태는 변경되지 않음)
          </p>
          <p className="running-period">
            진행 중: {running === null ? '쉬는 시간' : `${running.label} 교시`}
          </p>
        </div>
      </header>
      {markError && <p role="alert">자리 확인을 저장하지 못했습니다. 다시 시도해 주세요.</p>}

      <div className="roll-toolbar" ref={summaryRef}>
        <input
          type="date"
          className="input roll-toolbar__date"
          value={dateKey}
          onChange={(e) => setDateKey(e.target.value)}
        />
        <button type="button" className="btn btn--text btn--sm" onClick={() => setDateKey(dateKeyOf(new Date()))}>
          오늘
        </button>
        <Badge tone="success">
          확인 {confirmed.length} / {roll.length}
        </Badge>
        <Badge tone="warning">보류 {held.length}</Badge>
      </div>

      <div className="period-chips">
        {ClassPeriods.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`period-chip${p.id === periodId ? ' period-chip--on' : ''}`}
            onClick={() => setPeriodId(p.id)}
          >
            {p.id === periodId && <Icon name="check" size={15} />}
            {p.label}
          </button>
        ))}
      </div>
      <p className="hint">선택 교시: {ClassPeriods.find((p) => p.id === periodId)?.label} ~ {periodId}:50</p>

      <div className="roll" ref={rollRef} style={{ '--panel-w': `${sideWidth}px` } as CSSProperties}>
        <section className="panel seat-panel">
          <header className="side-card__head">
            <h2 className="card__title">좌석 배치</h2>
            <span className="spacer" />
            <button
              type="button"
              className="btn btn--text btn--sm"
              onClick={() => setRotated((v) => !v)}
            >
              <Icon name="rotate_right" size={16} />
              180도 회전
            </button>
          </header>

          {seating.room === undefined || !seating.published || seating.assignment === undefined ? (
            <p className="hint" style={{ textAlign: 'center', padding: '24px 0' }}>
              확정된 좌석 배치가 없습니다.
            </p>
          ) : (
            // 원본처럼 패널 폭에 맞춰 통째로 줄인다(FittedBox).
            <FitWidth>
              <SeatGrid
                grid={seating.room}
                seatUserIds={seating.assignment.assignments}
                seatNames={seating.assignment.seatNames}
                highlightUserId={current?.uid}
                highlightCaption="지금"
                rotated={rotated}
                presenceOf={(uid) => stateOf(uid)}
              />
            </FitWidth>
          )}
        </section>

        <PanelHandle
          axis="x"
          bodyRef={rollRef}
          size={sideWidth}
          range={(body) => [
            ROLL_SIDE.minWidth,
            Math.max(
              ROLL_SIDE.minWidth,
              Math.min(ROLL_SIDE.maxWidth, body.width - ROLL_SIDE.minSeatWidth - ROLL_SIDE.handle),
            ),
          ]}
          onCommit={setSideWidth}
          onReset={() => setSideWidth(ROLL_SIDE.initialWidth)}
        />

        {/* 오른쪽 열은 배치도 높이까지만 쓴다. 넘치면 목록·보류가 각자 스크롤한다. */}
        <div className="roll-side-wrap">
          <div
            className="roll-side"
            ref={sideRef}
            style={heldHeight > 0 ? ({ '--panel-h': `${heldHeight}px` } as CSSProperties) : undefined}
          >
            <section className="panel panel--flush roll-panel">
              <header className="roll-panel__head">
                <strong>
                  {current?.displayName ?? '—'} · {seatLabelOf(current?.uid)}
                </strong>
              </header>
              <div className="roll-panel__actions">
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => setIndex((i) => Math.max(0, i - 1))}
                  aria-label="이전 학생"
                >
                  <Icon name="chevron_left" size={18} />
                </button>
                <button
                  type="button"
                  className="btn btn--filled btn--md roll-panel__confirm"
                  ref={confirmRef}
                  onClick={() => current !== undefined && mark(current, 'confirmed')}
                  disabled={current === undefined}
                >
                  확인
                </button>
                <button
                  type="button"
                  className="btn btn--outline btn--md roll-panel__hold"
                  onClick={() => current !== undefined && mark(current, 'held')}
                  disabled={current === undefined}
                >
                  보류
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => setIndex((i) => Math.min(roll.length - 1, i + 1))}
                  aria-label="다음 학생"
                >
                  <Icon name="chevron_right" size={18} />
                </button>
              </div>

              <ol className="roll-list" ref={listRef}>
                {roll.map((student, i) => {
                  const state = stateOf(student.uid);
                  return (
                    <li
                      key={student.uid}
                      className={`roll-list__item${i === index ? ' roll-list__item--on' : ''}`}
                    >
                      <span className="roll-list__no">{i + 1}</span>
                      <span className="roll-list__body">
                        <strong>{student.displayName}</strong>
                        <span className="hint">{seatLabelOf(student.uid)}</span>
                      </span>
                      {state === 'confirmed' && <Icon name="check_circle" size={16} className="roll-list__ok" />}
                      {state === 'held' && <Icon name="pause_circle" size={16} className="roll-list__hold" />}
                    </li>
                  );
                })}
              </ol>
            </section>

            <PanelHandle
              axis="y"
              bodyRef={sideRef}
              size={heldHeight > 0 ? heldHeight : (heldRef.current?.offsetHeight ?? ROLL_SIDE.minHeldHeight)}
              range={(body) => [
                ROLL_SIDE.minHeldHeight,
                Math.max(ROLL_SIDE.minHeldHeight, body.height - ROLL_SIDE.minListHeight - ROLL_SIDE.handle),
              ]}
              onCommit={setHeldHeight}
              onReset={() => setHeldHeight(0)}
            />

            <section className="panel roll-held" ref={heldRef}>
              <header className="side-card__head">
                <h2 className="card__title">보류</h2>
                <span className="hint">{held.length}명</span>
              </header>
              {held.length === 0 ? (
                <p className="hint" style={{ textAlign: 'center', padding: '24px 0' }}>
                  보류된 학생이 없습니다.
                </p>
              ) : (
                <ul className="list">
                  {held.map((s) => (
                    <li key={s.uid} className="list__item">
                      <strong>{s.displayName}</strong>
                      <span className="spacer" />
                      <span className="hint">{seatLabelOf(s.uid)}</span>
                      <button
                        type="button"
                        className="btn btn--text btn--sm"
                        onClick={() => mark(s, 'confirmed', false)}
                      >
                        확인으로
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      </div>

      <section className="panel">
        <header className="side-card__head">
          <h2 className="card__title">당일 출석부</h2>
          <span className="hint">조회 전용 · 입퇴실·예외는 관리자 출석부와 동일</span>
        </header>
        <table className="table roll-table">
          <thead>
            <tr>
              <th>이름</th>
              <th style={{ width: 120 }}>호명</th>
              <th style={{ width: 120 }}>입실</th>
              <th style={{ width: 120 }}>퇴실</th>
              <th style={{ width: 140 }}>최종 상태</th>
              <th style={{ width: 120 }}>출처</th>
            </tr>
          </thead>
          <tbody>
            {roll.map((student) => {
              const record = attendance.find((a) => a.userId === student.uid);
              const called = stateOf(student.uid);
              return (
                <tr
                  key={student.uid}
                  className={student.uid === current?.uid ? 'roll-table__row--on' : undefined}
                >
                  <td>{student.displayName}</td>
                  <td className="hint">
                    {called === 'confirmed' ? '확인' : called === 'held' ? '보류' : '-'}
                  </td>
                  <td className="hint">{record?.checkInTime ?? '-'}</td>
                  <td className="hint">{record?.checkOutTime ?? '-'}</td>
                  <td>
                    {record === undefined ? (
                      <span className="hint">-</span>
                    ) : (
                      <Badge tone="neutral">{attendanceLabel(record.status)}</Badge>
                    )}
                  </td>
                  <td className="hint">{record === undefined ? '-' : '관리자 출석부'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
