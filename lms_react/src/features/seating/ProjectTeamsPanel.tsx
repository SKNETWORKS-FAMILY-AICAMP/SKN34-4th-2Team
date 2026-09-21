import { useState, type CSSProperties } from 'react';

import {
  createProjectTeam,
  deleteProjectTeam,
  replaceProjectTeams,
  updateProjectTeam,
  useProjectTeams,
} from '../../data/repository';
import { TEAM_MIN_MEMBERS, partitionMembers, teamAccent, teamSizeLabel } from '../../domain/projectTeams';
import type { ProjectTeam, User } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { Button, Dialog, TextInput } from '../../ui/components';
import { useDragDrop } from './useDragDrop';

/**
 * 좌석 배치 — 프로젝트 팀 탭 (widgets/project_teams_panel.dart)
 *
 * 왼쪽 미배정 학생을 팀 카드로 끌어 넣거나 ＋로 팀을 골라 넣는다. 「랜덤 구성」은
 * 전원을 섞어 4~5명씩 다시 나눈다. 팀 색은 배치 편집에서 좌석을 물들이는 데 쓰인다.
 */
export function ProjectTeamsPanel({
  cohortId,
  students,
  onFlash,
}: {
  cohortId: string;
  students: User[];
  onFlash(text: string): void;
}) {
  const teams = useProjectTeams(cohortId);
  const [query, setQuery] = useState('');
  const [picking, setPicking] = useState<User | null>(null);
  const [renaming, setRenaming] = useState<ProjectTeam | null>(null);
  const [deleting, setDeleting] = useState<ProjectTeam | null>(null);
  const [confirmRandom, setConfirmRandom] = useState(false);
  const dnd = useDragDrop<string>();

  const byId = new Map(students.map((s) => [s.uid, s]));
  // 퇴소한 학생은 팀 인원에서 뺀다. 팀 문서에는 남아 있어도 화면에는 없다.
  const visibleMembers = (team: ProjectTeam) =>
    team.memberIds.flatMap((id) => {
      const s = byId.get(id);
      return s === undefined ? [] : [s];
    });

  const assigned = new Set(teams.flatMap((t) => t.memberIds));
  const unassignedAll = students.filter((s) => !assigned.has(s.uid));
  const unassigned = unassignedAll
    .filter((s) => query === '' || s.displayName.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => a.displayName.localeCompare(b.displayName, 'ko'));
  const completeCount = teams.filter((t) => visibleMembers(t).length >= TEAM_MIN_MEMBERS).length;

  const addMember = (team: ProjectTeam, uid: string) => {
    if (team.memberIds.includes(uid)) return;
    // 넣는 김에 퇴소한 학생 id는 걷어 낸다.
    const valid = team.memberIds.filter((id) => byId.has(id));
    updateProjectTeam({ ...team, memberIds: [...valid, uid] });
  };

  const removeMember = (team: ProjectTeam, uid: string) =>
    updateProjectTeam({ ...team, memberIds: team.memberIds.filter((id) => id !== uid) });

  const addTeam = () => createProjectTeam(cohortId, `${teams.length + 1}팀`, teams.length, teams.length);

  const randomize = () => {
    setConfirmRandom(false);
    const partitions = partitionMembers(students.map((s) => s.uid));
    const sorted = [...teams].sort((a, b) => a.sortOrder - b.sortOrder);
    const upserts: ProjectTeam[] = partitions.map((memberIds, i) =>
      i < sorted.length
        ? { ...sorted[i], memberIds, sortOrder: i }
        : { id: '', cohortId, name: `${i + 1}팀`, memberIds, sortOrder: i, colorIndex: i },
    );
    replaceProjectTeams(
      cohortId,
      upserts,
      sorted.slice(partitions.length).map((t) => t.id),
    );
    onFlash(`${partitions.length}개 팀으로 랜덤 구성했습니다.`);
  };

  return (
    <div className="teams">
      <section className="teams-hero">
        <div>
          <h2>프로젝트 팀</h2>
          <p>팀당 4~5명으로 구성하세요. 배치 편집에서 팀끼리 앉힐 수 있습니다.</p>
          <div className="teams-hero__stats">
            <span>팀 {teams.length}</span>
            <span>완료 {completeCount}</span>
            <span>미배정 {unassignedAll.length}</span>
          </div>
        </div>
        <div className="teams-hero__actions">
          <button
            type="button"
            className="teams-hero__ghost"
            onClick={() => {
              if (students.length === 0) onFlash('배정할 학생이 없습니다.');
              else setConfirmRandom(true);
            }}
          >
            <Icon name="casino" size={18} />
            랜덤 구성
          </button>
          <button type="button" className="teams-hero__solid" onClick={addTeam}>
            <Icon name="add" size={18} />
            팀 추가
          </button>
        </div>
      </section>

      <div className="teams__body">
        <section className="teams-pool">
          <header className="teams-pool__head">
            <Icon name="person_search" size={18} />
            <strong>미배정 학생</strong>
            <span className="spacer" />
            <span className="hint">{unassigned.length}명</span>
          </header>
          <div className="teams-pool__search">
            <Icon name="search" size={18} />
            <input
              className="input"
              placeholder="이름 검색"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          {unassigned.length === 0 ? (
            <p className="teams-pool__empty">모두 팀에 배정되었습니다</p>
          ) : (
            <ul className="teams-pool__list">
              {unassigned.map((s) => (
                <li
                  key={s.uid}
                  className={`teams-pool__item${dnd.dragging === s.uid ? ' is-dragging' : ''}`}
                  {...dnd.source(s.uid)}
                >
                  <span className="teams-avatar">{s.displayName.slice(0, 1)}</span>
                  <span className="teams-pool__name">{s.displayName}</span>
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`${s.displayName} 팀에 추가`}
                    title="팀에 추가"
                    onClick={() => {
                      if (teams.length === 0) onFlash('팀이 없습니다. 팀을 먼저 추가하세요.');
                      else setPicking(s);
                    }}
                  >
                    <Icon name="add_circle" size={20} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="teams-board">
          {teams.length === 0 ? (
            <div className="teams-board__empty">
              <Icon name="groups_2" size={48} />
              <strong>아직 팀이 없습니다</strong>
              <p>오른쪽 위 「팀 추가」로 시작해 보세요</p>
            </div>
          ) : (
            teams.map((team) => {
              const members = visibleMembers(team);
              const key = `team:${team.id}`;
              const hovering = dnd.over === key;
              return (
                <section
                  key={team.id}
                  className={`team-card${hovering ? ' team-card--hover' : ''}`}
                  style={{ '--team': teamAccent(team.colorIndex) } as CSSProperties}
                  {...dnd.target(key, () => true, (uid) => addMember(team, uid))}
                >
                  <header className="team-card__head">
                    <span className="team-card__dot" />
                    <div className="team-card__title">
                      <strong>{team.name}</strong>
                      <span className={members.length >= TEAM_MIN_MEMBERS ? 'is-complete' : ''}>
                        {teamSizeLabel(members.length)}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label="이름 변경"
                      title="이름 변경"
                      onClick={() => setRenaming(team)}
                    >
                      <Icon name="edit" size={18} />
                    </button>
                    <button
                      type="button"
                      className="icon-btn team-card__delete"
                      aria-label="삭제"
                      title="삭제"
                      onClick={() => setDeleting(team)}
                    >
                      <Icon name="delete" size={18} />
                    </button>
                  </header>
                  <div className="team-card__body">
                    {members.length === 0 ? (
                      <p className="team-card__drop">
                        {hovering ? '여기에 놓기' : '학생을 드래그하거나 + 로 추가'}
                      </p>
                    ) : (
                      <div className="team-card__members">
                        {members.map((m) => (
                          <span key={m.uid} className="team-chip">
                            <span className="teams-avatar">{m.displayName.slice(0, 1)}</span>
                            {m.displayName}
                            <button
                              type="button"
                              aria-label={`${m.displayName} 빼기`}
                              onClick={() => removeMember(team, m.uid)}
                            >
                              <Icon name="close" size={14} />
                            </button>
                          </span>
                        ))}
                        {Array.from({ length: Math.max(0, TEAM_MIN_MEMBERS - members.length) }, (_, i) => (
                          <span key={`slot-${i}`} className="team-slot">
                            <Icon name="add" size={14} />
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </section>
              );
            })
          )}
        </div>
      </div>

      {picking !== null && (
        <Dialog title={`${picking.displayName} 팀 선택`} onClose={() => setPicking(null)} width={520}>
          <ul className="list">
            {teams.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  className="team-pick"
                  style={{ '--team': teamAccent(t.colorIndex) } as CSSProperties}
                  onClick={() => {
                    addMember(t, picking.uid);
                    setPicking(null);
                  }}
                >
                  <span className="teams-avatar teams-avatar--team">{t.name.slice(0, 1) || 'T'}</span>
                  <span className="team-pick__text">
                    <strong>{t.name}</strong>
                    <span className="hint">{teamSizeLabel(visibleMembers(t).length)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Dialog>
      )}

      {renaming !== null && (
        <RenameDialog
          team={renaming}
          onClose={() => setRenaming(null)}
          onSave={(name) => {
            if (name !== '' && name !== renaming.name) updateProjectTeam({ ...renaming, name });
            setRenaming(null);
          }}
        />
      )}

      {deleting !== null && (
        <Dialog
          title={`${deleting.name} 삭제`}
          onClose={() => setDeleting(null)}
          actions={
            <>
              <Button variant="text" onClick={() => setDeleting(null)}>
                취소
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  deleteProjectTeam(deleting.id);
                  setDeleting(null);
                }}
              >
                삭제
              </Button>
            </>
          }
        >
          <p>팀 구성이 삭제됩니다. 학생 계정은 그대로 둡니다.</p>
        </Dialog>
      )}

      {confirmRandom && (
        <Dialog
          title="랜덤 팀 구성"
          onClose={() => setConfirmRandom(false)}
          actions={
            <>
              <Button variant="text" onClick={() => setConfirmRandom(false)}>
                취소
              </Button>
              <Button onClick={randomize}>구성</Button>
            </>
          }
        >
          <p>
            전체 {students.length}명을 섞어 팀당 4~5명으로 다시 나눕니다.
            <br />
            기존 팀 멤버십은 덮어씁니다.
          </p>
        </Dialog>
      )}
    </div>
  );
}

function RenameDialog({
  team,
  onClose,
  onSave,
}: {
  team: ProjectTeam;
  onClose(): void;
  onSave(name: string): void;
}) {
  const [name, setName] = useState(team.name);
  return (
    <Dialog
      title="팀 이름"
      onClose={onClose}
      actions={
        <>
          <Button variant="text" onClick={onClose}>
            취소
          </Button>
          <Button onClick={() => onSave(name.trim())}>저장</Button>
        </>
      }
    >
      <TextInput
        autoFocus
        aria-label="이름"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') onSave(name.trim());
        }}
      />
    </Dialog>
  );
}
