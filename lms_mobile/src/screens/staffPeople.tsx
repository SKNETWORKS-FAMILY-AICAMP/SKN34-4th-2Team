import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';
import { RoutePaths } from '@web/app/routePaths';
import { CohortStatusLabels } from '@web/domain/constants';
import type { CohortStatus, CounselCategory, CounselNote, User, UserRole } from '@web/domain/types';

import { useSession } from '../auth/session';
import { selectCohort } from '../data/cohort';
import { createCohort, createUser, resetPassword, updateCohort, updateProfile, useCohorts, useUsers } from '../data/people';
import { refreshBootstrap } from '../data/query';
import { deleteCounsel, saveCounsel, useCounsel } from '../data/quests';
import { navLabel } from '../nav/webNav';
import {
  ChipRow,
  JobNotice,
  PersonPicker,
  SectionLabel,
  ToggleRow,
  confirmAction,
  dateLabel,
  isDateKey,
  useJob,
} from '../ui/form';
import { Avatar, Badge, Btn, Callout, Card, EmptyState, Field, ListGroup, ListItem, Muted, Screen, T, fmt, goBack, todayKey } from '../ui/kit';

const ROLE_LABEL: Record<UserRole, string> = { student: '학생', instructor: '강사', admin: '관리자' };

function push(path: string) {
  router.push(path as never);
}

export function PeoplePage({ role }: { role: UserRole }) {
  const { user } = useSession();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'active' | 'inactive' | 'all'>('active');
  const people = useUsers()
    .filter((row) => row.role === role && (role === 'instructor' || !user?.cohortId || row.cohortId === user.cohortId))
    .sort((a, b) => a.displayName.localeCompare(b.displayName, 'ko'));
  const q = query.trim().toLowerCase();
  const shown = people.filter(
    (row) =>
      (filter === 'all' || (filter === 'active' ? row.isActive !== false : row.isActive === false)) &&
      (!q || row.displayName.toLowerCase().includes(q) || row.email.toLowerCase().includes(q)),
  );
  const title = role === 'student' ? navLabel(RoutePaths.adminStudents, '학생 관리') : navLabel(RoutePaths.adminInstructors, '강사 관리');
  const active = people.filter((row) => row.isActive !== false).length;

  return (
    <Screen title={title} onRefresh={refreshBootstrap}>
      <T tone="secondary">
        {role === 'student' ? `${user?.cohortName || '전체 기수'} · ` : ''}재직 {active}명 · 전체 {people.length}명
      </T>
      <Btn label={role === 'student' ? '학생 추가' : '강사 추가'} icon="person-add" onPress={() => push(`/(admin)/people/new/${role}`)} />
      <Field label="찾기" value={query} onChangeText={setQuery} placeholder="이름 또는 이메일" />
      <ChipRow
        options={[
          { key: 'active', label: '활성' },
          { key: 'inactive', label: '비활성' },
          { key: 'all', label: '전체' },
        ]}
        value={filter}
        onChange={setFilter}
      />
      {shown.length === 0 ? (
        <Card><EmptyState icon="groups" text={people.length === 0 ? '등록된 사람이 없습니다.' : '조건에 맞는 사람이 없습니다.'} /></Card>
      ) : (
        <ListGroup>
          {shown.map((person) => (
            <ListItem
              key={person.uid}
              title={person.displayName}
              subtitle={[person.email, person.seatNumber ? `좌석 ${person.seatNumber}번` : '', role === 'instructor' ? person.cohortName : ''].filter(Boolean).join(' · ')}
              left={<Avatar name={person.displayName} size={34} />}
              right={person.isActive === false ? <Badge label="비활성" tone="neutral" /> : undefined}
              onPress={() => push(`/(admin)/people/${person.uid}`)}
            />
          ))}
        </ListGroup>
      )}
    </Screen>
  );
}

export function PersonPage({ uid }: { uid: string }) {
  const person = useUsers().find((row) => row.uid === uid);
  const job = useJob();
  const [issued, setIssued] = useState<{ email: string; password: string } | null>(null);
  if (!person) return <Screen title="사용자" empty emptyText="사용자를 찾지 못했습니다." />;

  const info: [string, string][] = [
    ['로그인 이메일', person.email],
    ['기수', person.cohortName || '-'],
    ...(person.role === 'student'
      ? ([
          ['좌석', person.seatNumber ? `${person.seatNumber}번` : '-'],
          ['학력 / 전공', person.educationMajor || '미입력'],
          ['마일리지', `${person.mileageBalance.toLocaleString('ko-KR')} P`],
        ] as [string, string][])
      : []),
    ['개인 이메일', person.personalEmail || '-'],
    ['최근 로그인', person.lastLoginAt ? fmt(person.lastLoginAt) : '기록 없음'],
    ['등록일', dateLabel(person.createdAt)],
  ];

  const setActive = (value: boolean) => {
    const apply = () => void job.run(() => updateProfile(uid, { isActive: value }), value ? '계정을 다시 활성화했습니다.' : '계정을 비활성화했습니다.');
    if (value) apply();
    else confirmAction('계정 비활성화', `${person.displayName}님은 더 이상 로그인할 수 없습니다. 계속할까요?`, apply, '비활성화');
  };

  const reissue = () =>
    confirmAction('비밀번호 재발급', `${person.displayName}님의 비밀번호를 새 임시 비밀번호로 바꿉니다.`, () => {
      void job.run(async () => {
        const result = await resetPassword(uid);
        setIssued({ email: String(result.email ?? person.email), password: String(result.password ?? '') });
      });
    }, '재발급');

  return (
    <Screen title={person.displayName}>
      <Card>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
          <Avatar name={person.displayName} />
          <View style={{ flex: 1, gap: 4 }}>
            <T variant="title">{person.displayName}</T>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <Badge label={ROLE_LABEL[person.role]} />
              {person.isActive === false ? <Badge label="비활성" tone="neutral" /> : <Badge label="활성" tone="success" />}
              {person.mustChangePassword ? <Badge label="비밀번호 변경 대기" tone="warning" /> : null}
            </View>
          </View>
        </View>
      </Card>

      <ListGroup>
        {info.map(([label, value]) => (
          <ListItem key={label} title={value} subtitle={label} />
        ))}
      </ListGroup>

      <JobNotice notice={job.notice} />
      {issued ? (
        <Callout tone="info">
          <T variant="subtitle">임시 비밀번호가 발급되었습니다</T>
          <T>아이디: {issued.email}</T>
          <T>비밀번호: {issued.password}</T>
          <T variant="caption" tone="secondary">지금만 보입니다. 본인에게 전달해 주세요. 다음 로그인 때 비밀번호를 바꾸게 됩니다.</T>
        </Callout>
      ) : null}

      {person.role !== 'admin' ? (
        <Card style={{ gap: 12 }}>
          <ToggleRow label="계정 활성" hint="끄면 로그인할 수 없습니다(퇴소 · 휴직)." value={person.isActive !== false} onChange={setActive} disabled={job.busy} />
          <Btn label="비밀번호 재발급" icon="lock-reset" tone="ghost" disabled={job.busy} onPress={reissue} />
          {person.role === 'student' ? (
            <Btn label="상담 기록 보기" icon="support-agent" tone="soft" onPress={() => push(`/(admin)/counsel/${person.uid}`)} />
          ) : null}
        </Card>
      ) : null}
      {person.role === 'student' ? <Muted>입학 상담지(학력 · 경험 등 상세 항목) 편집은 PC 웹에서 할 수 있습니다.</Muted> : null}
    </Screen>
  );
}

export function PersonFormPage({ role }: { role: UserRole }) {
  const { user } = useSession();
  const job = useJob();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [personalEmail, setPersonalEmail] = useState('');
  const [seat, setSeat] = useState('');
  const [created, setCreated] = useState<{ name: string; email: string; password: string } | null>(null);
  const label = ROLE_LABEL[role];

  const submit = () => {
    if (!user) return;
    const displayName = name.trim();
    if (!displayName) return job.fail('이름을 입력해 주세요.');
    if (email.trim() && !email.includes('@')) return job.fail('로그인 이메일 형식이 올바르지 않습니다.');
    if (personalEmail.trim() && !personalEmail.includes('@')) return job.fail('개인 이메일 형식이 올바르지 않습니다.');
    const seatNumber = seat.trim() ? Number(seat) : undefined;
    if (seatNumber !== undefined && (!Number.isInteger(seatNumber) || seatNumber <= 0)) return job.fail('좌석 번호는 1 이상의 숫자로 입력해 주세요.');
    if (role === 'student' && !user.cohortId) return job.fail('대시보드에서 기수를 먼저 선택해 주세요.');
    void job.run(async () => {
      const result = await createUser({
        email: email.trim(),
        displayName,
        role,
        cohortId: user.cohortId,
        personalEmail: personalEmail.trim() || undefined,
        seatNumber,
        isActive: true,
        skills: [],
        socialLinks: {},
        jobPreferences: { targetRoles: [], regions: [], employmentTypes: [] },
        mileageBalance: 0,
        mustChangePassword: true,
      });
      setCreated({ name: displayName, ...result });
      setName('');
      setEmail('');
      setPersonalEmail('');
      setSeat('');
    });
  };

  return (
    <Screen title={`${label} 추가`}>
      {role === 'student' ? <T tone="secondary">{user?.cohortName || '기수 미선택'}에 등록합니다.</T> : null}
      {created ? (
        <Callout tone="success">
          <T variant="subtitle">{created.name}님 계정을 만들었습니다</T>
          <T>아이디: {created.email}</T>
          <T>임시 비밀번호: {created.password}</T>
          <T variant="caption" tone="secondary">지금만 보입니다. 본인에게 전달해 주세요.</T>
        </Callout>
      ) : null}
      <Card style={{ gap: 12 }}>
        <Field label="이름 *" value={name} onChangeText={setName} />
        <Field label="로그인 이메일" value={email} onChangeText={setEmail} keyboard="email-address" placeholder="비워 두면 자동으로 만듭니다" />
        <Field label="개인 이메일" value={personalEmail} onChangeText={setPersonalEmail} keyboard="email-address" placeholder="구글폼 제출 확인용(선택)" />
        {role === 'student' ? <Field label="좌석 번호" value={seat} onChangeText={setSeat} keyboard="numeric" placeholder="선택" /> : null}
      </Card>
      <JobNotice notice={job.notice} />
      <Btn label={job.busy ? '만드는 중…' : '계정 만들기'} icon="person-add" disabled={job.busy} onPress={submit} />
      {created ? <Btn label="목록으로" tone="ghost" onPress={goBack} /> : null}
    </Screen>
  );
}

const STATUS_TONE: Record<CohortStatus, 'success' | 'info' | 'neutral'> = { active: 'success', planned: 'info', closed: 'neutral' };
const STATUS_ORDER: Record<CohortStatus, number> = { active: 0, planned: 1, closed: 2 };
const STATUS_OPTIONS = (['planned', 'active', 'closed'] as const).map((key) => ({ key, label: CohortStatusLabels[key] ?? key }));

export function CohortsPage() {
  const { user } = useSession();
  const users = useUsers();
  const cohorts = [...useCohorts()].sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || a.name.localeCompare(b.name, 'ko'));
  const job = useJob();
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [classroom, setClassroom] = useState('');
  const [status, setStatus] = useState<CohortStatus>('planned');

  const create = () => {
    const id = code.trim();
    if (!/^[A-Za-z0-9_-]+$/.test(id)) return job.fail('기수 코드는 영문 · 숫자 · _ · - 로 입력해 주세요. 예) cohort_35');
    if (cohorts.some((row) => row.cohortId === id)) return job.fail('이미 있는 기수 코드입니다.');
    if (!name.trim()) return job.fail('기수 이름을 입력해 주세요.');
    void job.run(async () => {
      await createCohort({ cohortId: id, name: name.trim(), classroomName: classroom.trim() || undefined, isActive: true, status, studentCount: 0 });
      setCode('');
      setName('');
      setClassroom('');
      setOpen(false);
    }, '기수를 추가했습니다.');
  };

  return (
    <Screen title={navLabel(RoutePaths.adminCohorts, '기수 관리')} onRefresh={refreshBootstrap}>
      <Btn label={open ? '추가 닫기' : '기수 추가'} icon={open ? 'close' : 'add'} tone={open ? 'ghost' : 'primary'} onPress={() => setOpen((value) => !value)} />
      {open ? (
        <Card style={{ gap: 12 }}>
          <Field label="기수 코드 *" value={code} onChangeText={setCode} placeholder="예) cohort_35" />
          <Field label="기수 이름 *" value={name} onChangeText={setName} placeholder="예) 35기" />
          <Field label="강의실" value={classroom} onChangeText={setClassroom} placeholder="선택" />
          <ChipRow label="상태" options={STATUS_OPTIONS} value={status} onChange={setStatus} />
          <Btn label={job.busy ? '추가 중…' : '추가'} disabled={job.busy} onPress={create} />
        </Card>
      ) : null}
      <JobNotice notice={job.notice} />
      {cohorts.length === 0 ? <Card><EmptyState icon="calendar-month" text="등록된 기수가 없습니다." /></Card> : null}
      {cohorts.map((cohort) => {
        const count = users.filter((row) => row.role === 'student' && row.cohortId === cohort.cohortId && row.isActive !== false).length;
        const selected = user?.cohortId === cohort.cohortId;
        const period = cohort.startDate || cohort.endDate ? `${dateLabel(cohort.startDate)} ~ ${dateLabel(cohort.endDate)}` : '';
        return (
          <Card key={cohort.cohortId} style={{ gap: 10 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <T variant="subtitle" style={{ flex: 1 }}>{cohort.name}</T>
              {selected ? <Badge label="보는 중" /> : null}
              <Badge label={CohortStatusLabels[cohort.status] ?? cohort.status} tone={STATUS_TONE[cohort.status]} />
            </View>
            <T variant="caption" tone="secondary">
              {[cohort.cohortId, cohort.classroomName, `학생 ${count}명`, period].filter(Boolean).join(' · ')}
            </T>
            <ChipRow
              options={STATUS_OPTIONS}
              value={cohort.status}
              onChange={(next) => {
                if (next !== cohort.status) void job.run(() => updateCohort(cohort.cohortId, { status: next }), `${cohort.name} 상태를 바꿨습니다.`);
              }}
            />
            <ToggleRow
              label="사용"
              value={cohort.isActive}
              disabled={job.busy}
              onChange={(value) => {
                const apply = () => void job.run(() => updateCohort(cohort.cohortId, { isActive: value }));
                if (value) apply();
                else confirmAction('기수 사용 중지', `${cohort.name}을(를) 사용 중지할까요?`, apply, '중지');
              }}
            />
            {!selected && user ? (
              <Btn label="이 기수로 보기" tone="soft" icon="swap-horiz" onPress={() => void selectCohort(user.uid, cohort.cohortId)} />
            ) : null}
          </Card>
        );
      })}
    </Screen>
  );
}

const CATEGORY_LABEL: Record<CounselCategory, string> = { regular: '정기', adhoc: '수시', career: '진로', other: '기타' };
const CATEGORY_OPTIONS = (Object.keys(CATEGORY_LABEL) as CounselCategory[]).map((key) => ({ key, label: CATEGORY_LABEL[key] }));

export function CounselPage({ studentId }: { studentId?: string }) {
  const { user } = useSession();
  const cohortId = user?.cohortId ?? '';
  const students = useUsers().filter((row) => row.role === 'student' && row.cohortId === cohortId && row.isActive !== false);
  const [uid, setUid] = useState(studentId ?? '');
  const summary = useCounsel(cohortId);
  const detail = useCounsel(cohortId, uid || undefined);
  const notes = summary.data ?? [];
  const student = students.find((row) => row.uid === uid);

  const counseled = new Set(notes.map((note) => note.uid));
  const openFollowUps = notes.filter((note) => note.followUp.trim() && !note.followUpDone).length;

  return (
    <Screen
      title={navLabel(RoutePaths.adminCounsel, '상담 현황')}
      loading={summary.isLoading && cohortId !== ''}
      error={summary.error instanceof Error ? summary.error.message : null}
      onRefresh={() => Promise.all([summary.refetch(), detail.refetch()])}
    >
      {!cohortId ? (
        <Card><EmptyState icon="groups" text="대시보드에서 기수를 먼저 선택해 주세요." /></Card>
      ) : (
        <>
          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
            <Badge label={`상담한 학생 ${students.filter((row) => counseled.has(row.uid)).length} / ${students.length}`} tone="success" />
            <Badge label={`후속 조치 남음 ${openFollowUps}`} tone={openFollowUps > 0 ? 'warning' : 'neutral'} />
          </View>
          <Card>
            <PersonPicker label="학생" people={students} value={uid} onChange={setUid} />
          </Card>
          {student ? (
            <StudentCounsel
              key={student.uid}
              student={student}
              notes={(detail.data ?? []).filter((note) => note.uid === student.uid)}
              loading={detail.isLoading}
            />
          ) : (
            <StudentSummary students={students} notes={notes} onPick={setUid} />
          )}
        </>
      )}
    </Screen>
  );
}

function StudentSummary({ students, notes, onPick }: { students: User[]; notes: CounselNote[]; onPick: (uid: string) => void }) {
  if (students.length === 0) return <Card><EmptyState icon="groups" text="이 기수에 학생이 없습니다." /></Card>;
  const rows = [...students].sort((a, b) => a.displayName.localeCompare(b.displayName, 'ko'));
  return (
    <>
      <SectionLabel title="학생별 상담" />
      <ListGroup>
        {rows.map((row) => {
          const mine = notes.filter((note) => note.uid === row.uid).sort((a, b) => b.counseledOn.localeCompare(a.counseledOn));
          return (
            <ListItem
              key={row.uid}
              title={row.displayName}
              subtitle={mine.length === 0 ? '상담 기록 없음' : `${mine.length}회 · 최근 ${mine[0].counseledOn}`}
              left={<Avatar name={row.displayName} size={32} />}
              right={mine.length === 0 ? <Badge label="미상담" tone="warning" /> : undefined}
              onPress={() => onPick(row.uid)}
            />
          );
        })}
      </ListGroup>
    </>
  );
}

function StudentCounsel({ student, notes, loading }: { student: User; notes: CounselNote[]; loading: boolean }) {
  const job = useJob();
  const [editing, setEditing] = useState<CounselNote | 'new' | null>(null);
  const sorted = [...notes].sort((a, b) => b.round - a.round || b.counseledOn.localeCompare(a.counseledOn));
  const nextRound = notes.reduce((max, note) => Math.max(max, note.round), 0) + 1;

  return (
    <>
      <Card style={{ gap: 6 }}>
        <T variant="subtitle">{student.displayName}</T>
        <T variant="caption" tone="secondary">학력 / 전공: {student.educationMajor || '미입력'}</T>
        {editing === null ? <Btn label="새 상담 기록" icon="add" onPress={() => setEditing('new')} /> : null}
      </Card>
      {editing !== null ? (
        <CounselForm
          key={editing === 'new' ? 'new' : editing.id}
          uid={student.uid}
          note={editing === 'new' ? undefined : editing}
          nextRound={nextRound}
          onDone={() => setEditing(null)}
        />
      ) : null}
      <JobNotice notice={job.notice} />
      <SectionLabel title={`상담 기록 ${notes.length}건`} />
      {loading ? <Muted>불러오는 중…</Muted> : null}
      {!loading && sorted.length === 0 ? <Card><EmptyState icon="support-agent" text="상담 기록이 없습니다." /></Card> : null}
      {sorted.map((note) => (
        <Card key={note.id} style={{ gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <T variant="subtitle" style={{ flex: 1 }}>{note.round}차 · {note.counseledOn}</T>
            <Badge label={CATEGORY_LABEL[note.category] ?? note.category} tone="info" />
          </View>
          {note.counselorName ? <T variant="caption" tone="secondary">상담 {note.counselorName}</T> : null}
          {note.content ? <T>{note.content}</T> : null}
          {note.followUp.trim() ? (
            <ToggleRow
              label={`후속 조치: ${note.followUp}`}
              hint={note.followUpDone ? '완료' : '진행 전'}
              value={note.followUpDone}
              disabled={job.busy}
              onChange={(value) => void job.run(() => saveCounsel(student.uid, { followUpDone: value }, note.id))}
            />
          ) : null}
          {note.nextOn ? <T variant="caption" tone="secondary">다음 상담 예정 {note.nextOn}</T> : null}
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ flex: 1 }}><Btn label="수정" tone="ghost" onPress={() => setEditing(note)} /></View>
            <View style={{ flex: 1 }}>
              <Btn
                label="삭제"
                tone="danger"
                disabled={job.busy}
                onPress={() =>
                  confirmAction('상담 기록 삭제', `${note.round}차(${note.counseledOn}) 상담 기록을 삭제할까요? 되돌릴 수 없습니다.`, () =>
                    void job.run(() => deleteCounsel(note.id), '삭제했습니다.'),
                  )
                }
              />
            </View>
          </View>
        </Card>
      ))}
    </>
  );
}

function CounselForm({ uid, note, nextRound, onDone }: { uid: string; note?: CounselNote; nextRound: number; onDone: () => void }) {
  const job = useJob();
  const [counseledOn, setCounseledOn] = useState(note?.counseledOn ?? todayKey());
  const [category, setCategory] = useState<CounselCategory>(note?.category ?? 'regular');
  const [round, setRound] = useState(String(note?.round ?? nextRound));
  const [content, setContent] = useState(note?.content ?? '');
  const [followUp, setFollowUp] = useState(note?.followUp ?? '');
  const [followUpDone, setFollowUpDone] = useState(note?.followUpDone ?? false);
  const [nextOn, setNextOn] = useState(note?.nextOn ?? '');

  const save = () => {
    const roundNo = Number(round);
    if (!isDateKey(counseledOn)) return job.fail('상담일을 YYYY-MM-DD 형식으로 입력해 주세요.');
    if (!Number.isInteger(roundNo) || roundNo < 1) return job.fail('회차는 1 이상의 숫자로 입력해 주세요.');
    if (!content.trim()) return job.fail('상담 내용을 입력해 주세요.');
    if (content.length > 5000) return job.fail('상담 내용은 5000자까지 입력할 수 있습니다.');
    if (nextOn.trim() && !isDateKey(nextOn.trim())) return job.fail('다음 상담일을 YYYY-MM-DD 형식으로 입력해 주세요.');
    void job.run(async () => {
      await saveCounsel(
        uid,
        { counseledOn, category, round: roundNo, content: content.trim(), followUp: followUp.trim(), followUpDone, nextOn: nextOn.trim() || null },
        note?.id,
      );
      onDone();
    });
  };

  return (
    <Card style={{ gap: 12 }}>
      <T variant="subtitle">{note ? '상담 기록 수정' : '새 상담 기록'}</T>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <View style={{ flex: 2 }}><Field label="상담일" value={counseledOn} onChangeText={setCounseledOn} placeholder="YYYY-MM-DD" /></View>
        <View style={{ flex: 1 }}><Field label="회차" value={round} onChangeText={setRound} keyboard="numeric" /></View>
      </View>
      <ChipRow label="구분" options={CATEGORY_OPTIONS} value={category} onChange={setCategory} />
      <Field label="상담 내용 *" value={content} onChangeText={setContent} multiline />
      <Field label="후속 조치" value={followUp} onChangeText={setFollowUp} placeholder="선택" />
      {followUp.trim() ? <ToggleRow label="후속 조치 완료" value={followUpDone} onChange={setFollowUpDone} /> : null}
      <Field label="다음 상담일" value={nextOn} onChangeText={setNextOn} placeholder="YYYY-MM-DD (선택)" />
      <JobNotice notice={job.notice} />
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <View style={{ flex: 1 }}><Btn label="취소" tone="ghost" onPress={onDone} /></View>
        <View style={{ flex: 1 }}><Btn label={job.busy ? '저장 중…' : '저장'} disabled={job.busy} onPress={save} /></View>
      </View>
    </Card>
  );
}
