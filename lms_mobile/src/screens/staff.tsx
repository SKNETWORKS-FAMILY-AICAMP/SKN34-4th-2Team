import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Linking, Pressable, ScrollView, View, useWindowDimensions } from 'react-native';
import { RoutePaths } from '@web/app/routePaths';
import { ClassPeriods, currentPeriod, nearestPeriod } from '@web/domain/constants';
import { RequestStatusLabels, RequestStatusTones, labelOf } from '@web/features/attendance/attendanceRequest';
import {
  APPROVAL_LABEL,
  EVIDENCE_LABEL,
  STATUS_LABEL as QUEST_STATUS_LABEL,
  STATUS_TONE as QUEST_STATUS_TONE,
  periodLabel,
} from '@web/features/quests/questLabels';
import type { Quest, QuestApproval, QuestEvidenceType, SeatPresenceState, User } from '@web/domain/types';

import { useSession } from '../auth/session';
import { reviewAttendanceRequest, setSeatPresence, useAttendance, useIssues, usePresence, useSpotChecks } from '../data/attendance';
import { selectCohort } from '../data/cohort';
import { absoluteFileUrl } from '../data/http';
import { refreshBootstrap, useDb } from '../data/query';
import { useCohorts, useUsers } from '../data/people';
import { reviewQuest, saveQuest, useQuestSubmissions, useQuests } from '../data/quests';
import { MenuButton } from '../nav/StaffDrawer';
import { appNav, navLabel } from '../nav/webNav';
import { useTheme } from '../theme/Theme';
import { ChipRow, JobNotice, SectionLabel, ToggleRow, confirmAction, isDateKey, useJob } from '../ui/form';
import { SeatGrid } from '../ui/SeatGrid';
import { Avatar, Badge, Btn, Callout, Card, Chip, EmptyState, Field, ListGroup, ListItem, Muted, Screen, Segmented, StatTile, T, fmt, todayKey } from '../ui/kit';
import { SettingsPage } from './student';
import { ResumeListPage } from './extra';

export { CohortsPage, CounselPage, PeoplePage, PersonFormPage, PersonPage } from './staffPeople';
export { AlertsAdminPage, CurriculumPage, FormsAdminPage, NoticeAdminPage, SourcesPage, StudyAdminPage } from './staffBoard';
export { ExamDetailPage, ExamEditPage, ExamsAdminPage, GradePage } from './staffExams';
export { AiPage, AssistantPage, MileageAdminPage, RoomsPage, TeamEditPage } from './staffOps';

function push(path: string) {
  router.push(path as never);
}

export function StaffHome({ role }: { role: 'instructor' | 'admin' }) {
  const { user } = useSession();
  const today = todayKey();
  const attendance = useAttendance().filter((row) => row.dateKey === today);
  const issues = useIssues().filter((row) => row.status === 'submitted');
  const home = role === 'admin' ? RoutePaths.admin : RoutePaths.instructor;
  return (
    <Screen title={navLabel(home, role === 'admin' ? '대시보드' : '자리 확인')} back={false} left={<MenuButton />} onRefresh={refreshBootstrap}>
      <Card>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
          <Avatar name={user?.displayName} />
          <View style={{ flex: 1, gap: 2 }}>
            <T variant="caption" tone="primary" style={{ fontWeight: '600' }}>{user?.cohortName || '기수 없음'}</T>
            <T variant="title">{user?.displayName}님</T>
            <T variant="caption" tone="secondary">{role === 'admin' ? '관리자' : '강사'}</T>
          </View>
        </View>
      </Card>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <StatTile icon="fact-check" label="오늘 출결" value={`${attendance.length}건`} tone="success" />
        <StatTile
          icon="pending-actions"
          label="대기 중인 출결 신청"
          value={`${issues.length}건`}
          tone={issues.length > 0 ? 'warning' : 'neutral'}
          onPress={role === 'admin' ? () => push('/(admin)/attendance') : undefined}
        />
      </View>
      {role === 'admin' ? <CohortPicker /> : null}
      <StaffMenuList role={role} />
    </Screen>
  );
}

function StaffMenuList({ role }: { role: 'instructor' | 'admin' }) {
  const { palette } = useTheme();
  const sections = appNav(role).map((section) => ({
    ...section,
    items: section.items.filter((item) => item.webPath !== (role === 'admin' ? RoutePaths.admin : RoutePaths.instructor)),
  }));
  return (
    <>
      {sections
        .filter((section) => section.items.length > 0)
        .map((section) => (
          <View key={section.id} style={{ gap: 8 }}>
            <T variant="label" tone="secondary" style={{ marginLeft: 4, marginTop: 4 }}>{section.title ?? '메뉴'}</T>
            <ListGroup>
              {section.items.map((item) => (
                <ListItem
                  key={item.href + item.label}
                  title={item.label}
                  left={
                    <View style={{ width: 32, height: 32, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.primaryLight }}>
                      <MaterialIcons name={item.icon} size={18} color={palette.primary} />
                    </View>
                  }
                  onPress={() => push(item.href)}
                />
              ))}
            </ListGroup>
          </View>
        ))}
    </>
  );
}

function CohortPicker() {
  const { user } = useSession();
  const cohorts = useCohorts().filter((cohort) => cohort.isActive || cohort.cohortId === user?.cohortId);
  if (!user || cohorts.length === 0) return null;
  return (
    <Card style={{ gap: 8 }}>
      <ChipRow
        label="보고 있는 기수"
        options={cohorts.map((cohort) => ({ key: cohort.cohortId, label: cohort.name }))}
        value={user.cohortId}
        onChange={(cohortId) => void selectCohort(user.uid, cohortId)}
      />
      <T variant="caption" tone="secondary">학생 · 출결 · 자리 확인 등 모든 메뉴가 고른 기수 기준으로 보입니다.</T>
    </Card>
  );
}

export function MenuPage({ role }: { role: 'instructor' | 'admin' }) {
  return (
    <Screen title="메뉴">
      <StaffMenuList role={role} />
    </Screen>
  );
}

// ── 마일리지 미션 ──────────────────────────────────────

export function AdminQuestsPage() {
  const { user } = useSession();
  const cohortId = user?.cohortId ?? '';
  const quests = useQuests(cohortId);
  const submissions = useQuestSubmissions(cohortId);
  const [tab, setTab] = useState<'review' | 'quests'>('review');
  const pending = (submissions.data ?? []).filter((row) => row.status === 'pending').length;
  return (
    <Screen
      title={navLabel(RoutePaths.adminQuests, '마일리지 미션')}
      loading={quests.isLoading && cohortId !== ''}
      error={quests.error instanceof Error ? quests.error.message : null}
      onRefresh={() => Promise.all([quests.refetch(), submissions.refetch()])}
    >
      {!cohortId ? <Card><EmptyState icon="emoji-events" text="대시보드에서 기수를 먼저 선택해 주세요." /></Card> : null}
      <Segmented
        options={[
          { key: 'review', label: pending > 0 ? `제출 검토 ${pending}` : '제출 검토' },
          { key: 'quests', label: `미션 ${(quests.data?.quests ?? []).length}` },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === 'review' ? <QuestReview rows={submissions.data ?? []} loading={submissions.isLoading} /> : <QuestList quests={quests.data?.quests ?? []} />}
    </Screen>
  );
}

function QuestReview({ rows, loading }: { rows: NonNullable<ReturnType<typeof useQuestSubmissions>['data']>; loading: boolean }) {
  const job = useJob();
  const [comments, setComments] = useState<Record<string, string>>({});
  const sorted = [...rows].sort((a, b) => Number(b.status === 'pending') - Number(a.status === 'pending') || (b.submittedAt ?? '').localeCompare(a.submittedAt ?? ''));
  const review = (id: string, decision: 'approve' | 'reject' | 'revoke') => {
    const comment = comments[id]?.trim() ?? '';
    if (decision === 'reject' && !comment) return job.fail('반려 사유를 메모에 적어 주세요.');
    void job.run(() => reviewQuest(id, decision, comment), decision === 'approve' ? '승인했습니다.' : decision === 'reject' ? '반려했습니다.' : '승인을 취소했습니다.');
  };
  if (loading) return <Muted>불러오는 중…</Muted>;
  return (
    <>
      <JobNotice notice={job.notice} />
      {sorted.length === 0 ? <Card><EmptyState icon="inbox" text="제출된 미션이 없습니다." /></Card> : null}
      {sorted.map((row) => (
        <Card key={row.id} style={{ gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <T variant="subtitle" style={{ flex: 1 }}>{row.studentName} · {row.questTitle}</T>
            <Badge label={QUEST_STATUS_LABEL[row.status]} tone={QUEST_STATUS_TONE[row.status]} />
          </View>
          {row.submittedAt ? <T variant="caption" tone="secondary">{fmt(row.submittedAt)}</T> : null}
          {row.text ? <T>{row.text}</T> : null}
          {row.link ? <T tone="primary" style={{ textDecorationLine: 'underline' }} onPress={() => void Linking.openURL(row.link)}>{row.link}</T> : null}
          {row.files.map((file, index) =>
            file.url ? (
              <T key={file.key} tone="primary" onPress={() => void Linking.openURL(absoluteFileUrl(file.url!))}>첨부 {index + 1} 열기</T>
            ) : null,
          )}
          {row.grantedAmount > 0 ? <Muted>{row.grantedAmount.toLocaleString('ko-KR')}M 지급</Muted> : null}
          {row.status === 'pending' ? (
            <>
              <Field label="메모 (반려 시 필수)" value={comments[row.id] ?? ''} onChangeText={(value) => setComments((prev) => ({ ...prev, [row.id]: value }))} />
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <View style={{ flex: 1 }}><Btn label="반려" tone="ghost" disabled={job.busy} onPress={() => review(row.id, 'reject')} /></View>
                <View style={{ flex: 1 }}><Btn label="승인" disabled={job.busy} onPress={() => review(row.id, 'approve')} /></View>
              </View>
            </>
          ) : row.status === 'approved' ? (
            <Btn
              label="승인 취소"
              tone="ghost"
              icon="undo"
              disabled={job.busy}
              onPress={() =>
                confirmAction(
                  '승인 취소',
                  row.grantedAmount > 0 ? `지급한 ${row.grantedAmount.toLocaleString('ko-KR')}M 이 회수됩니다. 계속할까요?` : '승인을 취소할까요?',
                  () => review(row.id, 'revoke'),
                  '승인 취소',
                )
              }
            />
          ) : row.reviewComment ? <Muted>사유: {row.reviewComment}</Muted> : null}
        </Card>
      ))}
    </>
  );
}

function QuestList({ quests }: { quests: Quest[] }) {
  const { user } = useSession();
  const job = useJob();
  const [editing, setEditing] = useState<Quest | 'new' | null>(null);
  const cohortId = user?.cohortId ?? '';
  return (
    <>
      {editing === null ? <Btn label="미션 만들기" icon="add" disabled={!cohortId} onPress={() => setEditing('new')} /> : null}
      {editing !== null ? <QuestForm key={editing === 'new' ? 'new' : editing.id} quest={editing === 'new' ? undefined : editing} onDone={() => setEditing(null)} /> : null}
      <JobNotice notice={job.notice} />
      {quests.length === 0 ? <Card><EmptyState icon="emoji-events" text="등록된 미션이 없습니다." /></Card> : null}
      {quests.map((quest) => (
        <Card key={quest.id} style={{ gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <T variant="subtitle" style={{ flexShrink: 1 }}>{quest.title}</T>
            <Badge label={`${quest.reward.toLocaleString('ko-KR')}M`} tone="primary" />
            {quest.closed ? <Badge label="마감" tone="neutral" /> : quest.open ? <Badge label="진행 중" tone="success" /> : null}
          </View>
          {quest.description && quest.description !== quest.title ? <T tone="secondary" numberOfLines={3}>{quest.description}</T> : null}
          <T variant="caption" tone="secondary">
            {EVIDENCE_LABEL[quest.evidenceType]} · {APPROVAL_LABEL[quest.approval]} · {periodLabel(quest)} · 1인 {quest.maxCompletions}회
          </T>
          {quest.counts ? (
            <T variant="caption" tone="secondary">
              검토 중 {quest.counts.pending ?? 0} · 완료 {quest.counts.approved ?? 0} · 반려 {quest.counts.rejected ?? 0}
            </T>
          ) : null}
          <ToggleRow
            label="학생에게 공개"
            value={quest.published}
            disabled={job.busy}
            onChange={(value) => void job.run(() => saveQuest(cohortId, { title: quest.title, published: value }, quest.id))}
          />
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ flex: 1 }}><Btn label="수정" tone="ghost" onPress={() => setEditing(quest)} /></View>
            <View style={{ flex: 1 }}>
              <Btn
                label={quest.closed ? '다시 열기' : '마감'}
                tone="soft"
                disabled={job.busy}
                onPress={() => void job.run(() => saveQuest(cohortId, { title: quest.title, closed: !quest.closed }, quest.id), quest.closed ? '다시 열었습니다.' : '마감했습니다.')}
              />
            </View>
          </View>
        </Card>
      ))}
    </>
  );
}

function QuestForm({ quest, onDone }: { quest?: Quest; onDone: () => void }) {
  const { user } = useSession();
  const job = useJob();
  const [title, setTitle] = useState(quest?.title ?? '');
  const [description, setDescription] = useState(quest?.description ?? '');
  const [reward, setReward] = useState(String(quest?.reward ?? 1000));
  const [evidenceType, setEvidenceType] = useState<QuestEvidenceType>(quest?.evidenceType ?? 'text');
  const [approval, setApproval] = useState<QuestApproval>(quest?.approval ?? 'manual');
  const [maxCompletions, setMaxCompletions] = useState(String(quest?.maxCompletions ?? 1));
  const [startOn, setStartOn] = useState(quest?.startOn ?? '');
  const [endOn, setEndOn] = useState(quest?.endOn ?? '');
  const [published, setPublished] = useState(quest?.published ?? true);

  const save = () => {
    if (!user) return;
    const rewardNo = Number(reward);
    const maxNo = Number(maxCompletions);
    if (!title.trim()) return job.fail('미션 제목을 입력해 주세요.');
    if (!Number.isInteger(rewardNo) || rewardNo <= 0) return job.fail('보상은 1 이상의 숫자로 입력해 주세요.');
    if (!Number.isInteger(maxNo) || maxNo < 1) return job.fail('1인 최대 횟수는 1 이상의 숫자로 입력해 주세요.');
    if (startOn.trim() && !isDateKey(startOn.trim())) return job.fail('시작일을 YYYY-MM-DD 형식으로 입력해 주세요.');
    if (endOn.trim() && !isDateKey(endOn.trim())) return job.fail('종료일을 YYYY-MM-DD 형식으로 입력해 주세요.');
    if (startOn.trim() && endOn.trim() && endOn.trim() < startOn.trim()) return job.fail('종료일이 시작일보다 빠릅니다.');
    void job.run(async () => {
      await saveQuest(
        user.cohortId,
        {
          title: title.trim(),
          description: description.trim(),
          reward: rewardNo,
          evidenceType,
          approval,
          maxCompletions: maxNo,
          startOn: startOn.trim() || null,
          endOn: endOn.trim() || null,
          published,
        },
        quest?.id,
      );
      onDone();
    });
  };

  return (
    <Card style={{ gap: 12 }}>
      <T variant="subtitle">{quest ? '미션 수정' : '미션 만들기'}</T>
      <Field label="제목 *" value={title} onChangeText={setTitle} />
      <Field label="설명" value={description} onChangeText={setDescription} multiline placeholder="학생에게 보일 안내" />
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <View style={{ flex: 1 }}><Field label="보상 (M)" value={reward} onChangeText={setReward} keyboard="numeric" /></View>
        <View style={{ flex: 1 }}><Field label="1인 최대 횟수" value={maxCompletions} onChangeText={setMaxCompletions} keyboard="numeric" /></View>
      </View>
      <ChipRow label="인증 방식" options={(Object.keys(EVIDENCE_LABEL) as QuestEvidenceType[]).map((key) => ({ key, label: EVIDENCE_LABEL[key] }))} value={evidenceType} onChange={setEvidenceType} />
      <ChipRow label="지급" options={(Object.keys(APPROVAL_LABEL) as QuestApproval[]).map((key) => ({ key, label: APPROVAL_LABEL[key] }))} value={approval} onChange={setApproval} />
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <View style={{ flex: 1 }}><Field label="시작일" value={startOn} onChangeText={setStartOn} placeholder="YYYY-MM-DD" /></View>
        <View style={{ flex: 1 }}><Field label="종료일" value={endOn} onChangeText={setEndOn} placeholder="YYYY-MM-DD" /></View>
      </View>
      <ToggleRow label="학생에게 공개" value={published} onChange={setPublished} />
      <JobNotice notice={job.notice} />
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <View style={{ flex: 1 }}><Btn label="취소" tone="ghost" onPress={onDone} /></View>
        <View style={{ flex: 1 }}><Btn label={job.busy ? '저장 중…' : '저장'} disabled={job.busy} onPress={save} /></View>
      </View>
    </Card>
  );
}

// ── 출석 관리 ──────────────────────────────────────────

export function AttendanceAdminPage() {
  const issues = [...useIssues()].sort(
    (a, b) => Number(b.status === 'submitted') - Number(a.status === 'submitted') || b.dateKey.localeCompare(a.dateKey),
  );
  const users = useDb()?.users ?? [];
  const job = useJob();
  const [comments, setComments] = useState<Record<string, string>>({});
  const decide = (id: string, decision: 'approved' | 'rejected') => {
    const comment = comments[id]?.trim() ?? '';
    if (decision === 'rejected' && !comment) return job.fail('반려 사유를 매니저 메모에 적어 주세요.');
    void job.run(() => reviewAttendanceRequest([id], decision, comment), decision === 'approved' ? '승인했습니다.' : '반려했습니다.');
  };
  return (
    <Screen title={navLabel(RoutePaths.adminAttendance, '출석 관리')} empty={issues.length === 0} emptyText="출결 신청이 없습니다." onRefresh={refreshBootstrap}>
      <JobNotice notice={job.notice} />
      {issues.map((issue) => {
        const comment = comments[issue.id] ?? '';
        return (
          <Card key={issue.id} style={{ gap: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <T variant="subtitle">{users.find((row) => row.uid === issue.userId)?.displayName ?? '학생'}</T>
              <T tone="secondary">{issue.dateKey}</T>
              <Badge label={RequestStatusLabels[issue.status] ?? '확인 대기'} tone={RequestStatusTones[issue.status] ?? 'warning'} />
            </View>
            <T>{labelOf(issue)}</T>
            {issue.reason ? <T tone="secondary">{issue.reason}</T> : null}
            {issue.status === 'submitted' ? (
              <>
                <Field label="매니저 메모 (반려 시 필수)" value={comment} onChangeText={(value) => setComments((prev) => ({ ...prev, [issue.id]: value }))} />
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <View style={{ flex: 1 }}><Btn label="승인" disabled={job.busy} onPress={() => decide(issue.id, 'approved')} /></View>
                  <View style={{ flex: 1 }}><Btn label="반려" tone="ghost" disabled={job.busy} onPress={() => decide(issue.id, 'rejected')} /></View>
                </View>
              </>
            ) : issue.reviewComment ? (
              <T variant="caption" tone="secondary">매니저 메모: {issue.reviewComment}</T>
            ) : null}
          </Card>
        );
      })}
    </Screen>
  );
}

// ── 자리 확인 ──────────────────────────────────────────

function shiftDay(dateKey: string, days: number): string {
  const [y, m, d] = dateKey.split('-').map(Number);
  return todayKey(new Date(y, m - 1, d + days));
}

/** 웹 `InstructorAttendanceScreen` — 강사 첫 화면이자 관리자의 자리 확인. 출석 상태는 건드리지 않는다. */
export function PresencePage({ home = false }: { home?: boolean }) {
  const { user } = useSession();
  const db = useDb();
  const { palette } = useTheme();
  const { width } = useWindowDimensions();
  const students = useUsers().filter((row) => row.role === 'student' && row.isActive !== false && row.cohortId === user?.cohortId);
  const [dateKey, setDateKey] = useState(() => todayKey());
  const [periodId, setPeriodId] = useState(() => nearestPeriod().id);
  const [index, setIndex] = useState(0);
  const [markError, setMarkError] = useState(false);
  const period = Number(periodId);
  const presence = usePresence().filter((row) => row.dateKey === dateKey && row.period === period);
  const checks = useSpotChecks().filter((row) => row.cohortId === user?.cohortId);
  const running = currentPeriod();

  const roomId = user?.cohortId ? db?.seatingMeta?.[user.cohortId]?.publishedRoomId : undefined;
  const room = (db?.seatingRooms ?? []).find((row) => row.id === roomId);
  const assignment = (db?.seatingAssignments ?? []).find((row) => row.roomId === roomId);
  const published = room !== undefined && assignment?.status === 'published';

  const stateOf = (uid: string): SeatPresenceState => presence.find((row) => row.userId === uid)?.state ?? 'unknown';
  // 호명은 이름 차례대로. 좌석 순서로 부르면 옆자리가 비었을 때 헷갈린다.
  const roll = [...students].sort((a, b) => a.displayName.localeCompare(b.displayName, 'ko'));
  const current = roll[Math.min(index, roll.length - 1)];
  const confirmed = roll.filter((row) => stateOf(row.uid) === 'confirmed');
  const held = roll.filter((row) => stateOf(row.uid) === 'held');

  const seatLabelOf = (uid: string | undefined) => {
    const seatId = Object.entries(assignment?.assignments ?? {}).find(([, owner]) => owner === uid)?.[0];
    if (seatId === undefined) return '좌석 없음';
    return `${room?.cells.find((cell) => cell.seatId === seatId)?.label ?? seatId}번`;
  };

  const mark = (student: User, state: SeatPresenceState, advance = true) => {
    setMarkError(false);
    if (advance) setIndex((value) => Math.min(value + 1, roll.length - 1));
    setSeatPresence(dateKey, period, student.uid, state).catch(() => setMarkError(true));
  };

  const title = home ? navLabel(RoutePaths.instructor, '자리 확인') : navLabel(RoutePaths.adminSeatPresence, '자리 확인');

  return (
    <Screen title={title} back={!home} left={home ? <MenuButton /> : undefined} onRefresh={refreshBootstrap}>
      <T tone="secondary">
        {user?.cohortName || '기수 없음'} · 진행 중: {running === null ? '쉬는 시간' : `${running.label} 교시`}
      </T>

      <Card style={{ gap: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Pressable accessibilityLabel="이전 날" hitSlop={8} onPress={() => setDateKey((value) => shiftDay(value, -1))}>
            <MaterialIcons name="chevron-left" size={26} color={palette.text} />
          </Pressable>
          <T variant="subtitle" style={{ flex: 1, textAlign: 'center' }}>{dateKey}</T>
          <Pressable accessibilityLabel="다음 날" hitSlop={8} onPress={() => setDateKey((value) => shiftDay(value, 1))}>
            <MaterialIcons name="chevron-right" size={26} color={palette.text} />
          </Pressable>
          <Chip label="오늘" selected={dateKey === todayKey()} onPress={() => setDateKey(todayKey())} />
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
          {ClassPeriods.map((row) => (
            <Chip key={row.id} label={row.label} selected={row.id === periodId} onPress={() => setPeriodId(row.id)} />
          ))}
        </ScrollView>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          <Badge label={`확인 ${confirmed.length} / ${roll.length}`} tone="success" />
          <Badge label={`보류 ${held.length}`} tone="warning" />
        </View>
      </Card>

      {markError ? (
        <Callout tone="error">
          <T tone="error">자리 확인을 저장하지 못했습니다. 다시 시도해 주세요.</T>
        </Callout>
      ) : null}

      {roll.length === 0 ? (
        <Card><EmptyState icon="groups" text={user?.cohortId ? '이 기수에 학생이 없습니다.' : '대시보드에서 기수를 먼저 선택해 주세요.'} /></Card>
      ) : (
        <Card style={{ gap: 14, borderColor: palette.primary, borderWidth: 1.5 }}>
          <View style={{ alignItems: 'center', gap: 2 }}>
            <T variant="caption" tone="secondary">{Math.min(index, roll.length - 1) + 1} / {roll.length}</T>
            <T variant="hero">{current?.displayName ?? '—'}</T>
            <T tone="primary" style={{ fontWeight: '600' }}>{seatLabelOf(current?.uid)}</T>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Pressable accessibilityLabel="이전 학생" hitSlop={8} onPress={() => setIndex((value) => Math.max(0, value - 1))}>
              <MaterialIcons name="chevron-left" size={30} color={palette.textSecondary} />
            </Pressable>
            <View style={{ flex: 1 }}>
              <Btn label="확인" icon="check" disabled={current === undefined} onPress={() => current && mark(current, 'confirmed')} />
            </View>
            <View style={{ flex: 1 }}>
              <Btn label="보류" icon="pause" tone="ghost" disabled={current === undefined} onPress={() => current && mark(current, 'held')} />
            </View>
            <Pressable accessibilityLabel="다음 학생" hitSlop={8} onPress={() => setIndex((value) => Math.min(roll.length - 1, value + 1))}>
              <MaterialIcons name="chevron-right" size={30} color={palette.textSecondary} />
            </Pressable>
          </View>
        </Card>
      )}

      <SectionLabel title="좌석 배치" />
      {!published || assignment === undefined ? (
        <Card><EmptyState icon="event-seat" text="확정된 좌석 배치가 없습니다." /></Card>
      ) : (
        <Card style={{ paddingHorizontal: 8, paddingVertical: 16 }}>
          <SeatGrid
            grid={room}
            seatUserIds={assignment.assignments}
            seatNames={assignment.seatNames}
            highlightUserId={current?.uid}
            highlightCaption="지금"
            markOf={stateOf}
            width={width - 32 - 16 - 2}
          />
        </Card>
      )}

      {held.length > 0 ? (
        <>
          <SectionLabel title={`보류 ${held.length}명`} />
          <ListGroup>
            {held.map((student) => (
              <ListItem
                key={student.uid}
                title={student.displayName}
                subtitle={seatLabelOf(student.uid)}
                left={<MaterialIcons name="pause-circle" size={20} color={palette.warning} />}
                right={<Chip label="확인으로" onPress={() => mark(student, 'confirmed', false)} />}
              />
            ))}
          </ListGroup>
        </>
      ) : null}

      {roll.length > 0 ? (
        <>
          <SectionLabel title="호명 순서" />
          <ListGroup>
            {roll.map((student, i) => {
              const state = stateOf(student.uid);
              return (
                <ListItem
                  key={student.uid}
                  title={`${i + 1}. ${student.displayName}`}
                  subtitle={seatLabelOf(student.uid)}
                  onPress={() => setIndex(i)}
                  left={
                    <MaterialIcons
                      name={state === 'confirmed' ? 'check-circle' : state === 'held' ? 'pause-circle' : 'radio-button-unchecked'}
                      size={20}
                      color={state === 'confirmed' ? palette.success : state === 'held' ? palette.warning : palette.textHint}
                    />
                  }
                  right={i === Math.min(index, roll.length - 1) ? <Badge label="지금" /> : undefined}
                />
              );
            })}
          </ListGroup>
        </>
      ) : null}

      {checks.length > 0 ? (
        <>
          <SectionLabel title="최근 불시 점검" />
          <ListGroup>
            {checks.slice(0, 5).map((check) => (
              <ListItem
                key={check.id}
                title={`${fmt(check.checkedAt)} · ${check.period === 'am' ? '오전' : '오후'}`}
                subtitle={`유 ${check.items.filter((item) => item.state === 'present').length} · 무 ${check.items.filter((item) => item.state === 'absent').length}${check.checkedByName ? ` · ${check.checkedByName}` : ''}`}
              />
            ))}
          </ListGroup>
        </>
      ) : null}
    </Screen>
  );
}

export { SettingsPage, ResumeListPage };
