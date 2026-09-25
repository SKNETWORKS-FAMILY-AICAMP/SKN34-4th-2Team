import { useEffect, useRef, useState } from 'react';

import {
  createSeatingRoom,
  deleteSeatingRoom,
  publishSeatingAssignment,
  saveSeatingDraft,
  saveSeatingRoom,
  useProjectTeams,
  useSeatingAssignment,
  useSeatingRoom,
  useSeatingRooms,
  useStudents,
} from '../../data/repository';
import { assignTeamsToSeats, shuffle, teamAccent } from '../../domain/projectTeams';
import { MAX_COHORT_STUDENTS, emptyGrid, seatCells, seatCount } from '../../domain/seatingLayout';
import type { SeatingGrid, SeatingRoom, User } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { Button, Dialog, Field, Select, TabPage, Tabs, TextInput } from '../../ui/components';
import { useCurrentUser } from '../auth/session';
import { LayoutEditor } from './LayoutEditor';
import { ProjectTeamsPanel } from './ProjectTeamsPanel';
import { SeatGrid } from './SeatingScreen';
import { useDragDrop } from './useDragDrop';

/**
 * 좌석 배치 (관리자) — features/seating/presentation/admin_seating_screen.dart
 *
 * 세 탭이다.
 * - 좌석 틀 설정: 강의실을 만들고, 격자에 강사석·출입문·테이블을 끌어 놓는다.
 * - 프로젝트 팀: 학생을 4~5명 팀으로 묶는다.
 * - 배치 편집: 강의실을 골라 학생을 좌석에 끌어 앉히고, 임시 저장하거나 확정한다.
 *   확정한 강의실 하나만 학생 화면에 보인다.
 */

type Tab = 'frame' | 'teams' | 'assign';

interface Flash {
  tone: 'success' | 'error';
  text: string;
}

export function AdminSeatingScreen() {
  const user = useCurrentUser();
  const rooms = useSeatingRooms(user.cohortId);
  const students = useStudents(user.cohortId).filter((s) => s.isActive);
  const [tab, setTab] = useState<Tab>('frame');
  const [flash, setFlash] = useState<Flash | null>(null);
  const flashTimer = useRef<number>();

  const show = (text: string, tone: Flash['tone'] = 'success') => {
    window.clearTimeout(flashTimer.current);
    setFlash({ tone, text });
    flashTimer.current = window.setTimeout(() => setFlash(null), 3000);
  };
  useEffect(() => () => window.clearTimeout(flashTimer.current), []);

  // 탭을 오가도 편집 중인 강의실은 그대로 둔다.
  const frame = useFrameDraft(rooms);
  const [assignRoomId, setAssignRoomId] = useState<string | undefined>(undefined);
  useEffect(() => {
    if (assignRoomId === undefined || !rooms.some((r) => r.id === assignRoomId)) {
      setAssignRoomId(rooms[0]?.id);
    }
  }, [rooms, assignRoomId]);
  const assignRoom = useSeatingRoom(assignRoomId);

  const titleRoom =
    tab === 'frame' ? frame.draft?.roomNumber : tab === 'assign' ? assignRoom?.roomNumber : undefined;
  const title = ['좌석 배치', user.cohortName, titleRoom?.trim()]
    .filter((v): v is string => v !== undefined && v !== '')
    .join(' · ');

  return (
    <TabPage
      title={title}
      description="강의실 틀을 만들고, 프로젝트 팀을 짜고, 학생을 자리에 앉혀 확정합니다."
      tabs={
        <Tabs
          active={tab}
          onChange={(id) => setTab(id as typeof tab)}
          items={[
            { id: 'frame', label: '좌석 틀 설정' },
            { id: 'teams', label: '프로젝트 팀' },
            { id: 'assign', label: '배치 편집' },
          ]}
        />
      }
    >

      <div className="seat-admin__body">
        {flash !== null && (
          <div className={`callout callout--${flash.tone} seat-admin__flash`} role="status">
            {flash.text}
          </div>
        )}

        {tab === 'frame' && <FrameTab rooms={rooms} frame={frame} cohortId={user.cohortId} onFlash={show} />}
        {tab === 'teams' && <ProjectTeamsPanel cohortId={user.cohortId} students={students} onFlash={show} />}
        {tab === 'assign' && (
          <AssignTab
            rooms={rooms}
            room={assignRoom}
            onSelectRoom={setAssignRoomId}
            students={students}
            cohortId={user.cohortId}
            onFlash={show}
          />
        )}
      </div>
    </TabPage>
  );
}

// ── 좌석 틀 설정 ───────────────────────────────────────

interface FrameDraft {
  grid: SeatingGrid;
  roomNumber?: string;
}

function useFrameDraft(rooms: SeatingRoom[]) {
  const [roomId, setRoomId] = useState<string | undefined>(undefined);
  const [draft, setDraft] = useState<FrameDraft | undefined>(undefined);
  const [dirty, setDirty] = useState(false);
  const groupCounter = useRef(1);

  const select = (room: SeatingRoom | undefined) => {
    setRoomId(room?.id);
    setDraft(room === undefined ? undefined : { grid: room, roomNumber: room.roomNumber });
    setDirty(false);
    // 새 테이블 id가 기존 것과 겹치지 않게 desk-N의 가장 큰 N 다음부터 쓴다.
    const nums = (room?.cells ?? []).map((c) => Number(/^desk-(\d+)$/.exec(c.groupId ?? '')?.[1] ?? 0));
    groupCounter.current = Math.max(0, ...nums) + 1;
  };

  // 처음 들어오면 첫 강의실을, 편집하던 강의실이 지워졌으면 비운다.
  useEffect(() => {
    if (roomId === undefined && !dirty && rooms.length > 0) select(rooms[0]);
    else if (roomId !== undefined && !rooms.some((r) => r.id === roomId)) select(rooms[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rooms, roomId]);

  return {
    roomId,
    draft,
    dirty,
    select,
    update(next: Partial<FrameDraft>) {
      setDraft((d) => (d === undefined ? d : { ...d, ...next }));
      setDirty(true);
    },
    saved() {
      setDirty(false);
    },
    newGroupId: () => `desk-${groupCounter.current++}`,
  };
}

function suggestRoomName(rooms: SeatingRoom[]): string {
  let max = rooms.length;
  for (const r of rooms) {
    const m = /강의실\s*(\d+)/.exec(r.roomNumber ?? '');
    if (m !== null) max = Math.max(max, Number(m[1]));
  }
  return `강의실 ${max + 1}`;
}

function roomLabel(room: SeatingRoom): string {
  const name = room.roomNumber?.trim();
  return `${name === undefined || name === '' ? '이름 없음' : name} (${seatCount(room)}석)`;
}

function FrameTab({
  rooms,
  frame,
  cohortId,
  onFlash,
}: {
  rooms: SeatingRoom[];
  frame: ReturnType<typeof useFrameDraft>;
  cohortId: string;
  onFlash(text: string, tone?: Flash['tone']): void;
}) {
  const [creating, setCreating] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const draft = frame.draft;
  const grid = draft?.grid ?? emptyGrid();

  const create = (name: string) => {
    setCreating(false);
    const id = createSeatingRoom(cohortId, emptyGrid(), name);
    frame.select({ ...emptyGrid(), id, cohortId, roomNumber: name });
    onFlash(`"${name}" 강의실이 생성되었습니다.`);
  };

  const save = () => {
    if (frame.roomId === undefined || draft === undefined) return;
    saveSeatingRoom(frame.roomId, draft.grid, draft.roomNumber);
    frame.saved();
    onFlash('강의실 틀이 저장되었습니다.');
  };

  const remove = () => {
    setConfirmDelete(false);
    if (frame.roomId === undefined) return;
    deleteSeatingRoom(frame.roomId);
    frame.select(undefined);
    onFlash('강의실이 삭제되었습니다.');
  };

  return (
    <div className="seat-admin__col">
      <p className="seat-admin__note">
        위에서 편집할 강의실을 고른 뒤, {grid.rows}×{grid.cols} 그리드에 강사석·출입문·테이블을 배치하세요. 학생
        배치는 「배치 편집」에서 합니다.
      </p>

      {rooms.length === 0 ? (
        <div className="seat-admin__room">
          <Icon name="meeting_room" size={20} />
          <span>아직 강의실이 없습니다. 먼저 만들어 주세요.</span>
          <span className="spacer" />
          <Button icon={<Icon name="add" size={18} />} onClick={() => setCreating(true)}>
            새 강의실
          </Button>
        </div>
      ) : (
        <>
          <div className="seat-admin__toolbar">
            <Field label="편집할 강의실">
              <Select
                value={frame.roomId ?? ''}
                onChange={(e) => frame.select(rooms.find((r) => r.id === e.target.value))}
              >
                {rooms.map((r) => (
                  <option key={r.id} value={r.id}>
                    {roomLabel(r)}
                  </option>
                ))}
              </Select>
            </Field>
            <Button variant="outline" icon={<Icon name="add" size={18} />} onClick={() => setCreating(true)}>
              새 강의실
            </Button>
          </div>

          {draft !== undefined && (
            <div className="seat-admin__toolbar">
              <Field label="표시 이름" hint="드롭다운·상단에 보이는 이름입니다">
                <TextInput
                  placeholder="예: 401호"
                  value={draft.roomNumber ?? ''}
                  onChange={(e) =>
                    frame.update({ roomNumber: e.target.value.trim() === '' ? undefined : e.target.value })
                  }
                />
              </Field>
              <button
                type="button"
                className="icon-btn seat-admin__delete"
                aria-label="이 강의실 삭제"
                title="이 강의실 삭제"
                onClick={() => setConfirmDelete(true)}
              >
                <Icon name="delete" size={20} />
              </button>
              <Button icon={<Icon name="save" size={18} />} onClick={save}>
                틀 저장
              </Button>
            </div>
          )}

          {draft !== undefined && (
            <>
              <p className={`seat-admin__status${frame.dirty ? ' seat-admin__status--dirty' : ''}`}>
                좌석 {seatCount(grid)}석 · 재원 학생 최대 {MAX_COHORT_STUDENTS}명
                {frame.dirty && ' · 저장되지 않은 변경'}
              </p>
              <LayoutEditor
                grid={grid}
                onChange={(next) => frame.update({ grid: next })}
                newGroupId={frame.newGroupId}
              />
            </>
          )}
        </>
      )}

      {creating && (
        <NewRoomDialog suggested={suggestRoomName(rooms)} onClose={() => setCreating(false)} onCreate={create} />
      )}

      {confirmDelete && (
        <Dialog
          title="강의실 삭제"
          onClose={() => setConfirmDelete(false)}
          actions={
            <>
              <Button variant="text" onClick={() => setConfirmDelete(false)}>
                취소
              </Button>
              <Button variant="danger" onClick={remove}>
                삭제
              </Button>
            </>
          }
        >
          <p>이 강의실과 저장된 배치 데이터가 모두 삭제됩니다. 계속할까요?</p>
        </Dialog>
      )}
    </div>
  );
}

function NewRoomDialog({
  suggested,
  onClose,
  onCreate,
}: {
  suggested: string;
  onClose(): void;
  onCreate(name: string): void;
}) {
  const [name, setName] = useState(suggested);
  const submit = () => {
    if (name.trim() !== '') onCreate(name.trim());
  };
  return (
    <Dialog
      title="새 강의실"
      onClose={onClose}
      actions={
        <>
          <Button variant="text" onClick={onClose}>
            취소
          </Button>
          <Button onClick={submit} disabled={name.trim() === ''}>
            만들기
          </Button>
        </>
      }
    >
      <Field label="표시 이름">
        <TextInput
          autoFocus
          placeholder="예: 401호, 강의실 1"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit();
          }}
        />
      </Field>
    </Dialog>
  );
}

// ── 배치 편집 ──────────────────────────────────────────

/** 끄는 학생. 좌석에서 끌어 왔으면 `fromSeatId`가 있다. */
interface SeatDrag {
  userId: string;
  fromSeatId?: string;
}

function AssignTab({
  rooms,
  room,
  onSelectRoom,
  students,
  cohortId,
  onFlash,
}: {
  rooms: SeatingRoom[];
  room: SeatingRoom | undefined;
  onSelectRoom(id: string): void;
  students: User[];
  cohortId: string;
  onFlash(text: string, tone?: Flash['tone']): void;
}) {
  const stored = useSeatingAssignment(room?.id);
  const teams = useProjectTeams(cohortId);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);
  const dnd = useDragDrop<SeatDrag>();

  // 저장된 배치를 편집본으로 불러온다. 손대는 중이면 덮어쓰지 않는다.
  useEffect(() => {
    setDraft({ ...(stored?.assignments ?? {}) });
    setDirty(false);
  }, [room?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!dirty) setDraft({ ...(stored?.assignments ?? {}) });
  }, [stored]); // eslint-disable-line react-hooks/exhaustive-deps

  if (rooms.length === 0) {
    return <p className="seat-admin__center">먼저 "좌석 틀 설정" 탭에서 강의실을 만들어주세요.</p>;
  }

  const edit = (change: (d: Record<string, string>) => Record<string, string>) => {
    setDraft((d) => change({ ...d }));
    setDirty(true);
  };

  const byId = new Map(students.map((s) => [s.uid, s]));
  const assignedUids = new Set(Object.values(draft));
  const unassigned = students.filter((s) => !assignedUids.has(s.uid));
  const seatNames = Object.fromEntries(
    Object.entries(draft).flatMap(([seatId, uid]) => {
      const name = byId.get(uid)?.displayName;
      return name === undefined ? [] : [[seatId, name]];
    }),
  );
  const inactiveSeatIds = new Set(Object.keys(draft).filter((seatId) => !byId.has(draft[seatId])));
  const published = stored?.status === 'published';

  // 팀끼리 뭉쳐 앉았는지 보이게 좌석을 팀 색으로 칠한다.
  const teamColorOf = new Map<string, string>();
  for (const t of teams) for (const uid of t.memberIds) teamColorOf.set(uid, teamAccent(t.colorIndex));
  const seatTints = Object.fromEntries(
    Object.entries(draft).flatMap(([seatId, uid]) => {
      const color = teamColorOf.get(uid);
      return color === undefined ? [] : [[seatId, color]];
    }),
  );

  const assign = (seatId: string, p: SeatDrag) =>
    edit((d) => {
      for (const k of Object.keys(d)) if (d[k] === p.userId) delete d[k];
      if (p.fromSeatId !== undefined) delete d[p.fromSeatId];
      d[seatId] = p.userId;
      return d;
    });

  const swap = (from: string, to: string) =>
    edit((d) => {
      const fromUser = d[from];
      const toUser = d[to];
      if (fromUser === undefined) return d;
      if (toUser !== undefined) d[from] = toUser;
      else delete d[from];
      d[to] = fromUser;
      return d;
    });

  const randomAssign = () => {
    if (room === undefined) return;
    const empty = shuffle(seatCells(room).filter((c) => draft[c.seatId] === undefined).map((c) => c.seatId));
    if (empty.length === 0 || unassigned.length === 0) return;
    edit((d) => {
      unassigned.slice(0, empty.length).forEach((s, i) => (d[empty[i]] = s.uid));
      return d;
    });
  };

  const assignByTeams = () => {
    if (room === undefined) return;
    const withMembers = teams.filter((t) => t.memberIds.length > 0);
    if (withMembers.length === 0) {
      onFlash(
        teams.length === 0
          ? '구성된 프로젝트 팀이 없습니다. 「프로젝트 팀」 탭에서 먼저 만들어 주세요.'
          : '멤버가 있는 팀이 없습니다. 「프로젝트 팀」 탭에서 학생을 배정하세요.',
        'error',
      );
      return;
    }
    setDraft(assignTeamsToSeats(room, withMembers));
    setDirty(true);
    onFlash(`${withMembers.length}개 팀을 인접 좌석에 배치했습니다. 확인 후 저장하세요.`);
  };

  const save = (publish: boolean) => {
    if (room === undefined) return;
    if (new Set(Object.values(draft)).size > students.length) {
      onFlash('배정 인원이 재원 학생 수를 초과할 수 없습니다.', 'error');
      return;
    }
    if (publish) publishSeatingAssignment(room.id, draft, seatNames);
    else saveSeatingDraft(room.id, draft, seatNames);
    setDirty(false);
    onFlash(publish ? '좌석 배치가 확정되었습니다.' : '배치가 저장되었습니다.');
  };

  const unassignHover = dnd.over === 'unassigned';

  return (
    <div className="seat-assign">
      <div className="seat-assign__room">
        <Field label="좌석을 확인할 강의실">
          <Select value={room?.id ?? ''} onChange={(e) => onSelectRoom(e.target.value)}>
            {rooms.map((r) => (
              <option key={r.id} value={r.id}>
                {roomLabel(r)}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {room === undefined ? (
        <p className="seat-admin__center">좌석을 확인할 강의실을 선택해주세요.</p>
      ) : (
        <>
          <div className="seat-assign__actions">
            <span className={`seat-status seat-status--${published ? 'published' : 'draft'}`}>
              {published ? '확정됨' : '작성 중'}
            </span>
            <Button variant="outline" icon={<Icon name="shuffle" size={18} />} onClick={randomAssign}>
              랜덤 배치
            </Button>
            <Button variant="outline" icon={<Icon name="groups" size={18} />} onClick={assignByTeams}>
              팀끼리 앉히기
            </Button>
            <Button
              variant="outline"
              icon={<Icon name="clear_all" size={18} />}
              onClick={() => edit(() => ({}))}
            >
              전체 해제
            </Button>
            <Button icon={<Icon name="save" size={18} />} onClick={() => save(false)}>
              임시 저장
            </Button>
            <Button icon={<Icon name="check_circle" size={18} />} onClick={() => save(true)}>
              {published ? '재확정' : '확정'}
            </Button>
          </div>

          {inactiveSeatIds.size > 0 && (
            <p className="seat-assign__warn">⚠ 퇴소 학생이 배정된 좌석이 {inactiveSeatIds.size}개 있습니다.</p>
          )}

          <div className="seat-assign__body">
            <section
              className={`seat-pool${unassignHover ? ' seat-pool--hover' : ''}`}
              {...dnd.target(
                'unassigned',
                (p) => p.fromSeatId !== undefined,
                (p) => edit((d) => {
                  delete d[p.fromSeatId!];
                  return d;
                }),
              )}
            >
              <header className="seat-pool__head">
                <Icon name="group" size={18} />
                <strong>미배정 ({unassigned.length}명)</strong>
              </header>
              <p className="hint">학생을 좌석으로 드래그하세요</p>
              {unassignHover && <p className="seat-pool__drop">여기에 놓으면 배정 해제</p>}
              {unassigned.length === 0 ? (
                <p className="seat-pool__empty">미배정 학생이 없습니다</p>
              ) : (
                <ul className="seat-pool__list">
                  {unassigned.map((s) => (
                    <li
                      key={s.uid}
                      className={`seat-pool__item${dnd.dragging?.userId === s.uid ? ' is-dragging' : ''}`}
                      {...dnd.source({ userId: s.uid })}
                    >
                      <span className="teams-avatar">{s.displayName.slice(0, 1)}</span>
                      <span className="seat-pool__name">{s.displayName}</span>
                      <Icon name="drag_indicator" size={16} className="seat-pool__grip" />
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <div className="seat-assign__map">
              <SeatGrid
                grid={room}
                seatUserIds={draft}
                seatNames={seatNames}
                inactiveSeatIds={inactiveSeatIds}
                seatTints={seatTints}
                seatAttrs={(seatId, occupied) => {
                  const key = `seat:${seatId}`;
                  const from = dnd.dragging?.fromSeatId;
                  return {
                    className: `seat--editable${dnd.over === key ? ' seat--drop' : ''}${from === seatId ? ' is-dragging' : ''}`,
                    ...dnd.target(
                      key,
                      (p) => p.fromSeatId !== seatId,
                      (p) => {
                        if (p.fromSeatId !== undefined && occupied) swap(p.fromSeatId, seatId);
                        else assign(seatId, p);
                      },
                    ),
                    ...(occupied ? dnd.source({ userId: draft[seatId], fromSeatId: seatId }) : {}),
                  };
                }}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
