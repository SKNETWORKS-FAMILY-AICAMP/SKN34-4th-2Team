import { MaterialIcons } from '@expo/vector-icons';
import { useEffect, useState, type ReactNode } from 'react';
import { Linking, View } from 'react-native';
import { RoutePaths } from '@web/app/routePaths';
import type { AlertPopup, FormTask, InflearnPackage, InflearnPackageType, Notice, ScheduleRepeatType, ScheduledNotice } from '@web/domain/types';

import { useSession } from '../auth/session';
import { deleteFormTask, saveFormTask, useFormResponses, useFormTasks } from '../data/forms';
import { publishScheduled, removeAlert, removeNotice, removeScheduled, saveAlert, saveNotice, saveScheduled, useAlerts, useNotices, useScheduled } from '../data/notices';
import { deletePackage, savePackage, useCurriculum, usePackages, useUsers } from '../data/people';
import { refreshBootstrap } from '../data/query';
import { addGithub, listGithub, removeGithub, setSourceActive, syncSources, useNotes, useSources, type GithubOwner } from '../data/study';
import { navLabel } from '../nav/webNav';
import { useTheme } from '../theme/Theme';
import { ChipRow, JobNotice, SectionLabel, ToggleRow, confirmAction, dateFromKey, isDateKey, isTime, keyOf, useJob } from '../ui/form';
import { Badge, Btn, Callout, Card, EmptyState, Field, ListGroup, ListItem, Muted, Screen, Segmented, T, fmt } from '../ui/kit';

function isUrl(value: string): boolean {
  return /^https?:\/\/\S+$/i.test(value.trim());
}

function Actions({ children }: { children: ReactNode }) {
  return <View style={{ flexDirection: 'row', gap: 8 }}>{children}</View>;
}

function Half({ children }: { children: ReactNode }) {
  return <View style={{ flex: 1 }}>{children}</View>;
}

// ── 게시판 ─────────────────────────────────────────────

const REPEAT_LABEL: Record<ScheduleRepeatType, string> = { once: '한 번', daily: '매일', weekly: '매주' };
const WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일'];

function repeatText(row: ScheduledNotice): string {
  if (row.repeatType === 'weekly') return `매주 ${WEEKDAYS[(row.weekday - 1 + 7) % 7]}요일 ${row.publishTime}`;
  return `${REPEAT_LABEL[row.repeatType] ?? row.repeatType} ${row.publishTime}`;
}

export function NoticeAdminPage({ scheduled = false, allowScheduled = true }: { scheduled?: boolean; allowScheduled?: boolean }) {
  const notices = useNotices();
  const planned = useScheduled();
  const [tab, setTab] = useState<'notices' | 'scheduled'>(scheduled && allowScheduled ? 'scheduled' : 'notices');
  const title = allowScheduled ? navLabel(RoutePaths.adminBoard, '게시판') : navLabel(RoutePaths.instructorBoard, '게시물관리');
  return (
    <Screen title={title} onRefresh={refreshBootstrap}>
      {allowScheduled ? (
        <Segmented
          options={[
            { key: 'notices', label: `공지 ${notices.length}` },
            { key: 'scheduled', label: `예약 공지 ${planned.length}` },
          ]}
          value={tab}
          onChange={setTab}
        />
      ) : null}
      {tab === 'notices' ? <NoticeTab notices={notices} /> : <ScheduledTab rows={planned} />}
    </Screen>
  );
}

function NoticeTab({ notices }: { notices: Notice[] }) {
  const job = useJob();
  const [editing, setEditing] = useState<Notice | 'new' | null>(null);
  const sorted = [...notices].sort(
    (a, b) => Number(b.isFavorite) - Number(a.isFavorite) || (b.createdAt?.getTime() ?? 0) - (a.createdAt?.getTime() ?? 0),
  );
  return (
    <>
      {editing === null ? <Btn label="공지 작성" icon="edit" onPress={() => setEditing('new')} /> : null}
      {editing !== null ? (
        <NoticeForm key={editing === 'new' ? 'new' : editing.id} notice={editing === 'new' ? undefined : editing} onDone={() => setEditing(null)} />
      ) : null}
      <JobNotice notice={job.notice} />
      {sorted.length === 0 ? <Card><EmptyState icon="campaign" text="등록된 공지가 없습니다." /></Card> : null}
      {sorted.map((notice) => (
        <Card key={notice.id} style={{ gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            {notice.isFavorite ? <Badge label="중요" tone="error" /> : null}
            {notice.channelLabel ? <Badge label={notice.channelLabel} tone="info" /> : null}
            <T variant="subtitle" style={{ flexShrink: 1 }}>{notice.title}</T>
          </View>
          <T variant="caption" tone="secondary">{[notice.authorName, fmt(notice.createdAt)].filter(Boolean).join(' · ')}</T>
          {notice.content ? <T tone="secondary" numberOfLines={3}>{notice.content}</T> : null}
          <Actions>
            <Half><Btn label="수정" tone="ghost" onPress={() => setEditing(notice)} /></Half>
            <Half>
              <Btn
                label="삭제"
                tone="danger"
                disabled={job.busy}
                onPress={() => confirmAction('공지 삭제', `「${notice.title}」을(를) 삭제할까요?`, () => void job.run(() => removeNotice(notice.id), '삭제했습니다.'))}
              />
            </Half>
          </Actions>
        </Card>
      ))}
    </>
  );
}

function NoticeForm({ notice, onDone }: { notice?: Notice; onDone: () => void }) {
  const { user } = useSession();
  const job = useJob();
  const [title, setTitle] = useState(notice?.title ?? '');
  const [content, setContent] = useState(notice?.content ?? '');
  const [favorite, setFavorite] = useState(notice?.isFavorite ?? false);
  const save = () => {
    if (!user) return;
    if (!title.trim()) return job.fail('제목을 입력해 주세요.');
    if (!content.trim()) return job.fail('내용을 입력해 주세요.');
    void job.run(async () => {
      await saveNotice({ id: notice?.id, title: title.trim(), content: content.trim(), isFavorite: favorite, cohortId: user.cohortId });
      onDone();
    });
  };
  return (
    <Card style={{ gap: 12 }}>
      <T variant="subtitle">{notice ? '공지 수정' : '공지 작성'}</T>
      <Field label="제목 *" value={title} onChangeText={setTitle} />
      <Field label="내용 *" value={content} onChangeText={setContent} multiline />
      <ToggleRow label="중요 공지" hint="목록 맨 위에 고정됩니다." value={favorite} onChange={setFavorite} />
      <JobNotice notice={job.notice} />
      <Actions>
        <Half><Btn label="취소" tone="ghost" onPress={onDone} /></Half>
        <Half><Btn label={job.busy ? '저장 중…' : '저장'} disabled={job.busy} onPress={save} /></Half>
      </Actions>
    </Card>
  );
}

function ScheduledTab({ rows }: { rows: ScheduledNotice[] }) {
  const { user } = useSession();
  const job = useJob();
  const [editing, setEditing] = useState<ScheduledNotice | 'new' | null>(null);
  const sorted = [...rows].sort((a, b) => Number(b.isActive) - Number(a.isActive) || a.publishTime.localeCompare(b.publishTime));
  return (
    <>
      {editing === null ? <Btn label="예약 공지 등록" icon="schedule-send" onPress={() => setEditing('new')} /> : null}
      {editing !== null ? (
        <ScheduledForm key={editing === 'new' ? 'new' : editing.id} row={editing === 'new' ? undefined : editing} onDone={() => setEditing(null)} />
      ) : null}
      <JobNotice notice={job.notice} />
      {sorted.length === 0 ? <Card><EmptyState icon="schedule" text="예약 공지가 없습니다." /></Card> : null}
      {sorted.map((row) => (
        <Card key={row.id} style={{ gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            {row.isFavorite ? <Badge label="중요" tone="error" /> : null}
            <T variant="subtitle" style={{ flex: 1 }}>{row.title}</T>
          </View>
          <T variant="caption" tone="secondary">
            {repeatText(row)} · 최근 게시 {row.lastPublishedAt ? fmt(row.lastPublishedAt) : '없음'}
            {row.nextPublishAt ? ` · 다음 ${fmt(row.nextPublishAt)}` : ''}
          </T>
          <ToggleRow
            label="예약 동작"
            value={row.isActive}
            disabled={job.busy || !user}
            onChange={(value) => {
              if (user) void job.run(() => saveScheduled({ ...row, isActive: value, cohortId: user.cohortId }));
            }}
          />
          <Actions>
            <Half>
              <Btn
                label="지금 게시"
                tone="soft"
                disabled={job.busy}
                onPress={() => confirmAction('지금 게시', `「${row.title}」을(를) 바로 공지로 올릴까요?`, () => void job.run(() => publishScheduled(row.id), '공지로 게시했습니다.'), '게시')}
              />
            </Half>
            <Half><Btn label="수정" tone="ghost" onPress={() => setEditing(row)} /></Half>
            <Half>
              <Btn
                label="삭제"
                tone="danger"
                disabled={job.busy}
                onPress={() => confirmAction('예약 공지 삭제', `「${row.title}」을(를) 삭제할까요?`, () => void job.run(() => removeScheduled(row.id), '삭제했습니다.'))}
              />
            </Half>
          </Actions>
        </Card>
      ))}
    </>
  );
}

function ScheduledForm({ row, onDone }: { row?: ScheduledNotice; onDone: () => void }) {
  const { user } = useSession();
  const job = useJob();
  const [title, setTitle] = useState(row?.title ?? '');
  const [content, setContent] = useState(row?.content ?? '');
  const [repeatType, setRepeatType] = useState<ScheduleRepeatType>(row?.repeatType ?? 'daily');
  const [publishTime, setPublishTime] = useState(row?.publishTime ?? '08:30');
  const [weekday, setWeekday] = useState(row?.weekday ?? 1);
  const [favorite, setFavorite] = useState(row?.isFavorite ?? false);
  const [active, setActive] = useState(row?.isActive ?? true);
  const save = () => {
    if (!user) return;
    if (!title.trim()) return job.fail('제목을 입력해 주세요.');
    if (!isTime(publishTime)) return job.fail('게시 시각을 HH:mm 형식으로 입력해 주세요. 예) 08:30');
    void job.run(async () => {
      await saveScheduled({
        id: row?.id,
        title: title.trim(),
        content: content.trim(),
        cohortId: user.cohortId,
        repeatType,
        publishTime,
        weekday,
        isFavorite: favorite,
        isActive: active,
      });
      onDone();
    });
  };
  return (
    <Card style={{ gap: 12 }}>
      <T variant="subtitle">{row ? '예약 공지 수정' : '예약 공지 등록'}</T>
      <Field label="제목 *" value={title} onChangeText={setTitle} />
      <Field label="내용" value={content} onChangeText={setContent} multiline />
      <ChipRow
        label="반복"
        options={(Object.keys(REPEAT_LABEL) as ScheduleRepeatType[]).map((key) => ({ key, label: REPEAT_LABEL[key] }))}
        value={repeatType}
        onChange={setRepeatType}
      />
      <Field label="게시 시각" value={publishTime} onChangeText={setPublishTime} placeholder="HH:mm" />
      {repeatType === 'weekly' ? (
        <ChipRow label="요일" options={WEEKDAYS.map((label, index) => ({ key: index + 1, label }))} value={weekday} onChange={setWeekday} />
      ) : null}
      <ToggleRow label="중요 공지로 올리기" value={favorite} onChange={setFavorite} />
      <ToggleRow label="예약 동작" value={active} onChange={setActive} />
      <JobNotice notice={job.notice} />
      <Actions>
        <Half><Btn label="취소" tone="ghost" onPress={onDone} /></Half>
        <Half><Btn label={job.busy ? '저장 중…' : '저장'} disabled={job.busy} onPress={save} /></Half>
      </Actions>
    </Card>
  );
}

// ── 알림 팝업 ──────────────────────────────────────────

export function AlertsAdminPage() {
  const { user } = useSession();
  const alerts = [...useAlerts()].sort((a, b) => Number(b.isActive) - Number(a.isActive) || a.sortOrder - b.sortOrder);
  const job = useJob();
  const [editing, setEditing] = useState<AlertPopup | 'new' | null>(null);
  const toggle = (popup: AlertPopup, isActive: boolean) => {
    if (!user) return;
    void job.run(() => saveAlert({ ...popup, isActive, cohortId: user.cohortId }));
  };
  return (
    <Screen title={navLabel(RoutePaths.adminAlertPopups, '알림 팝업')} onRefresh={refreshBootstrap}>
      <Muted>켜 둔 알림은 학생이 앱 · 웹을 열 때 팝업으로 뜹니다.</Muted>
      {editing === null ? <Btn label="알림 만들기" icon="add-alert" onPress={() => setEditing('new')} /> : null}
      {editing !== null ? (
        <AlertForm key={editing === 'new' ? 'new' : editing.id} popup={editing === 'new' ? undefined : editing} onDone={() => setEditing(null)} />
      ) : null}
      <JobNotice notice={job.notice} />
      {alerts.length === 0 ? <Card><EmptyState icon="notifications-none" text="등록된 알림이 없습니다." /></Card> : null}
      {alerts.map((popup) => (
        <Card key={popup.id} style={{ gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <T variant="subtitle" style={{ flex: 1 }}>{popup.title}</T>
            <Badge label={popup.isActive ? '표시 중' : '꺼짐'} tone={popup.isActive ? 'success' : 'neutral'} />
          </View>
          {popup.content ? <T tone="secondary" numberOfLines={3}>{popup.content}</T> : null}
          <T variant="caption" tone="secondary">
            {[
              `확인 ${popup.readBy?.length ?? 0}명`,
              popup.targetUserIds?.length ? `지정 ${popup.targetUserIds.length}명` : '기수 전체',
              popup.endDate ? `${popup.endDate}까지` : '끌 때까지',
              popup.startTime && popup.endTime ? `${popup.startTime}~${popup.endTime}` : '',
            ].filter(Boolean).join(' · ')}
          </T>
          {popup.linkUrl ? (
            <T variant="caption" tone="primary" numberOfLines={1} onPress={() => void Linking.openURL(popup.linkUrl!)}>{popup.linkUrl}</T>
          ) : null}
          <ToggleRow label="학생에게 표시" value={popup.isActive} disabled={job.busy} onChange={(value) => toggle(popup, value)} />
          <Actions>
            <Half><Btn label="수정" tone="ghost" onPress={() => setEditing(popup)} /></Half>
            <Half>
              <Btn
                label="삭제"
                tone="danger"
                disabled={job.busy}
                onPress={() => confirmAction('알림 삭제', `「${popup.title}」을(를) 삭제할까요?`, () => void job.run(() => removeAlert(popup.id), '삭제했습니다.'))}
              />
            </Half>
          </Actions>
        </Card>
      ))}
    </Screen>
  );
}

function AlertForm({ popup, onDone }: { popup?: AlertPopup; onDone: () => void }) {
  const { user } = useSession();
  const job = useJob();
  const [title, setTitle] = useState(popup?.title ?? '');
  const [content, setContent] = useState(popup?.content ?? '');
  const [linkUrl, setLinkUrl] = useState(popup?.linkUrl ?? '');
  const [endDate, setEndDate] = useState(popup?.endDate ?? '');
  const [active, setActive] = useState(popup?.isActive ?? true);
  const save = () => {
    if (!user) return;
    if (!title.trim()) return job.fail('제목을 입력해 주세요.');
    if (!content.trim()) return job.fail('내용을 입력해 주세요.');
    if (linkUrl.trim() && !isUrl(linkUrl)) return job.fail('링크는 http:// 또는 https:// 로 시작해야 합니다.');
    if (endDate.trim() && !isDateKey(endDate.trim())) return job.fail('종료일을 YYYY-MM-DD 형식으로 입력해 주세요.');
    void job.run(async () => {
      await saveAlert({
        ...(popup ?? {}),
        id: popup?.id,
        title: title.trim(),
        content: content.trim(),
        linkUrl: linkUrl.trim() || undefined,
        endDate: endDate.trim() || undefined,
        isActive: active,
        cohortId: user.cohortId,
      });
      onDone();
    });
  };
  return (
    <Card style={{ gap: 12 }}>
      <T variant="subtitle">{popup ? '알림 수정' : '알림 만들기'}</T>
      <Field label="제목 *" value={title} onChangeText={setTitle} />
      <Field label="내용 *" value={content} onChangeText={setContent} multiline />
      <Field label="링크" value={linkUrl} onChangeText={setLinkUrl} keyboard="url" placeholder="https:// (선택)" />
      <Field label="종료일" value={endDate} onChangeText={setEndDate} placeholder="YYYY-MM-DD (비우면 끌 때까지)" />
      <ToggleRow label="바로 표시" value={active} onChange={setActive} />
      <Muted>특정 학생에게만 보내기 · 표시 시간대 설정은 PC 웹에서 할 수 있습니다.</Muted>
      <JobNotice notice={job.notice} />
      <Actions>
        <Half><Btn label="취소" tone="ghost" onPress={onDone} /></Half>
        <Half><Btn label={job.busy ? '저장 중…' : '저장'} disabled={job.busy} onPress={save} /></Half>
      </Actions>
    </Card>
  );
}

// ── 설문 · 제출 ────────────────────────────────────────

export function FormsAdminPage() {
  const { user } = useSession();
  const tasks = [...useFormTasks()].sort((a, b) => b.dueAt.getTime() - a.dueAt.getTime());
  const responses = useFormResponses();
  const students = useUsers().filter((row) => row.role === 'student' && row.cohortId === user?.cohortId && row.isActive !== false);
  const job = useJob();
  const [editing, setEditing] = useState<FormTask | 'new' | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const now = Date.now();

  return (
    <Screen title={navLabel(RoutePaths.adminFormTasks, '설문 · 제출')} onRefresh={refreshBootstrap}>
      {editing === null ? <Btn label="외부 설문 등록" icon="add-link" onPress={() => setEditing('new')} /> : null}
      {editing !== null ? (
        <ExternalForm key={editing === 'new' ? 'new' : editing.id} task={editing === 'new' ? undefined : editing} onDone={() => setEditing(null)} />
      ) : null}
      <JobNotice notice={job.notice} />
      {tasks.length === 0 ? <Card><EmptyState icon="ballot" text="등록된 설문이 없습니다." /></Card> : null}
      {tasks.map((task) => {
        const answered = responses.filter((row) => row.taskId === task.id);
        const answeredIds = new Set(answered.map((row) => row.userId));
        const missing = students.filter((row) => !answeredIds.has(row.uid));
        const closed = task.dueAt.getTime() < now;
        return (
          <Card key={task.id} style={{ gap: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <T variant="subtitle" style={{ flexShrink: 1 }}>{task.title}</T>
              <Badge label={task.mode === 'builtin' ? 'LMS 설문' : '외부 링크'} tone="info" />
              {!task.published ? <Badge label="비공개" tone="neutral" /> : null}
              {closed ? <Badge label="마감" tone="warning" /> : null}
            </View>
            <T variant="caption" tone="secondary">마감 {fmt(task.dueAt)} · 응답 {answered.length} / {students.length}명</T>
            {task.description ? <T tone="secondary" numberOfLines={2}>{task.description}</T> : null}
            <Btn
              label={expanded === task.id ? '응답 현황 닫기' : `응답 현황 보기 (미응답 ${missing.length}명)`}
              tone="soft"
              onPress={() => setExpanded(expanded === task.id ? null : task.id)}
            />
            {expanded === task.id ? (
              <View style={{ gap: 6 }}>
                <T variant="label" tone="secondary">미응답 {missing.length}명</T>
                <T>{missing.length === 0 ? '모두 응답했습니다.' : missing.map((row) => row.displayName).join(', ')}</T>
                <T variant="label" tone="secondary">응답 {answered.length}명</T>
                {answered.slice(0, 50).map((row) => (
                  <T key={row.id} variant="caption">{row.userDisplayName} · {fmt(row.submittedAt) || '-'}</T>
                ))}
              </View>
            ) : null}
            <ToggleRow
              label="학생에게 공개"
              value={task.published}
              disabled={job.busy || !user}
              onChange={(value) => {
                if (user) void job.run(() => saveFormTask({ ...task, published: value }, user.cohortId, true));
              }}
            />
            {task.mode === 'builtin' ? <Muted>LMS 설문 문항 편집은 PC 웹에서 할 수 있습니다.</Muted> : null}
            <Actions>
              {task.mode === 'external' ? <Half><Btn label="수정" tone="ghost" onPress={() => setEditing(task)} /></Half> : null}
              <Half>
                <Btn
                  label="삭제"
                  tone="danger"
                  disabled={job.busy}
                  onPress={() =>
                    confirmAction('설문 삭제', `「${task.title}」과 응답 기록을 삭제할까요?`, () => void job.run(() => deleteFormTask(task.id), '삭제했습니다.'))
                  }
                />
              </Half>
            </Actions>
          </Card>
        );
      })}
    </Screen>
  );
}

function ExternalForm({ task, onDone }: { task?: FormTask; onDone: () => void }) {
  const { user } = useSession();
  const job = useJob();
  const [title, setTitle] = useState(task?.title ?? '');
  const [description, setDescription] = useState(task?.description ?? '');
  const [formUrl, setFormUrl] = useState(task?.formUrl ?? '');
  const [guideUrl, setGuideUrl] = useState(task?.notionGuideUrl ?? '');
  const [due, setDue] = useState(keyOf(task?.dueAt) || keyOf(new Date(Date.now() + 7 * 86400000)));
  const [published, setPublished] = useState(task?.published ?? true);
  const save = () => {
    if (!user) return;
    if (!title.trim()) return job.fail('제목을 입력해 주세요.');
    if (!isUrl(formUrl)) return job.fail('설문 주소를 https:// 로 시작하는 링크로 입력해 주세요.');
    if (guideUrl.trim() && !isUrl(guideUrl)) return job.fail('안내 링크 형식이 올바르지 않습니다.');
    if (!isDateKey(due)) return job.fail('마감일을 YYYY-MM-DD 형식으로 입력해 주세요.');
    void job.run(async () => {
      await saveFormTask(
        {
          id: task?.id ?? '',
          title: title.trim(),
          description: description.trim(),
          mode: 'external',
          formUrl: formUrl.trim(),
          questions: [],
          notionGuideUrl: guideUrl.trim() || undefined,
          dueAt: dateFromKey(due, true),
          published,
          responseCount: task?.responseCount ?? 0,
        },
        user.cohortId,
        Boolean(task),
      );
      onDone();
    });
  };
  return (
    <Card style={{ gap: 12 }}>
      <T variant="subtitle">{task ? '외부 설문 수정' : '외부 설문 등록'}</T>
      <Field label="제목 *" value={title} onChangeText={setTitle} />
      <Field label="설명" value={description} onChangeText={setDescription} multiline />
      <Field label="설문 주소 *" value={formUrl} onChangeText={setFormUrl} keyboard="url" placeholder="https://forms.gle/..." />
      <Field label="안내 링크" value={guideUrl} onChangeText={setGuideUrl} keyboard="url" placeholder="노션 안내 등(선택)" />
      <Field label="마감일 *" value={due} onChangeText={setDue} placeholder="YYYY-MM-DD (그날 23:59 마감)" />
      <ToggleRow label="학생에게 공개" value={published} onChange={setPublished} />
      <JobNotice notice={job.notice} />
      <Actions>
        <Half><Btn label="취소" tone="ghost" onPress={onDone} /></Half>
        <Half><Btn label={job.busy ? '저장 중…' : '저장'} disabled={job.busy} onPress={save} /></Half>
      </Actions>
    </Card>
  );
}

// ── 학습실 ─────────────────────────────────────────────

const PACKAGE_LABEL: Record<InflearnPackageType, string> = { review: '복습', preview: '예습', bonus: '보너스' };

export function StudyAdminPage() {
  const { user } = useSession();
  const packs = [...usePackages()].sort((a, b) => a.sortOrder - b.sortOrder || a.title.localeCompare(b.title, 'ko'));
  const job = useJob();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [subject, setSubject] = useState('');
  const [summary, setSummary] = useState('');
  const [type, setType] = useState<InflearnPackageType>('review');

  const create = () => {
    if (!user) return;
    if (!title.trim()) return job.fail('패키지 제목을 입력해 주세요.');
    void job.run(async () => {
      await savePackage(
        { id: '', title: title.trim(), subject: subject.trim() || title.trim(), type, summary: summary.trim() || undefined, units: [], courses: [], isPublished: false, sortOrder: packs.length },
        user.cohortId,
      );
      setTitle('');
      setSubject('');
      setSummary('');
      setOpen(false);
    }, '추가했습니다. 강의 목록을 채운 뒤 공개해 주세요.');
  };

  const togglePublished = (pack: InflearnPackage, isPublished: boolean) => {
    if (user) void job.run(() => savePackage({ ...pack, isPublished }, user.cohortId));
  };

  return (
    <Screen title={navLabel(RoutePaths.adminStudyRoom, '학습실')} onRefresh={refreshBootstrap}>
      <Btn label={open ? '추가 닫기' : '패키지 추가'} icon={open ? 'close' : 'add'} tone={open ? 'ghost' : 'primary'} onPress={() => setOpen((value) => !value)} />
      {open ? (
        <Card style={{ gap: 12 }}>
          <Field label="제목 *" value={title} onChangeText={setTitle} />
          <Field label="과목" value={subject} onChangeText={setSubject} placeholder="비우면 제목과 같게" />
          <Field label="소개" value={summary} onChangeText={setSummary} multiline />
          <ChipRow label="구분" options={(Object.keys(PACKAGE_LABEL) as InflearnPackageType[]).map((key) => ({ key, label: PACKAGE_LABEL[key] }))} value={type} onChange={setType} />
          <Btn label={job.busy ? '추가 중…' : '추가'} disabled={job.busy} onPress={create} />
        </Card>
      ) : null}
      <JobNotice notice={job.notice} />
      <Muted>단원 · 강의 링크 편집은 PC 웹에서 할 수 있습니다.</Muted>
      {packs.length === 0 ? <Card><EmptyState icon="menu-book" text="등록된 패키지가 없습니다." /></Card> : null}
      {packs.map((pack) => {
        const courseCount = pack.courses.length + pack.units.reduce((sum, unit) => sum + unit.courses.length, 0);
        return (
          <Card key={pack.id} style={{ gap: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <T variant="subtitle" style={{ flex: 1 }}>{pack.title}</T>
              <Badge label={PACKAGE_LABEL[pack.type] ?? pack.type} tone="info" />
            </View>
            <T variant="caption" tone="secondary">{pack.subject} · 단원 {pack.units.length}개 · 강의 {courseCount}개</T>
            {pack.summary ? <T tone="secondary" numberOfLines={2}>{pack.summary}</T> : null}
            <ToggleRow label="학생에게 공개" value={pack.isPublished} disabled={job.busy} onChange={(value) => togglePublished(pack, value)} />
            <Btn
              label="삭제"
              tone="danger"
              disabled={job.busy}
              onPress={() => confirmAction('패키지 삭제', `「${pack.title}」을(를) 삭제할까요?`, () => void job.run(() => deletePackage(pack.id), '삭제했습니다.'))}
            />
          </Card>
        );
      })}
    </Screen>
  );
}

// ── 커리큘럼 ───────────────────────────────────────────

export function CurriculumPage() {
  const sheets = useCurriculum();
  const sheet = sheets[0];
  const [query, setQuery] = useState('');
  const q = query.trim().toLowerCase();
  const rows = [...(sheet?.rows ?? [])]
    .sort((a, b) => a.dayIndex - b.dayIndex || a.order - b.order)
    .filter((row) => !q || [row.subject, row.topic, row.detail, row.dateLabel].some((text) => text.toLowerCase().includes(q)));
  const days = new Map<number, typeof rows>();
  rows.forEach((row) => days.set(row.dayIndex, [...(days.get(row.dayIndex) ?? []), row]));

  return (
    <Screen title={navLabel(RoutePaths.instructorCurriculum, '커리큘럼')} onRefresh={refreshBootstrap}>
      <Callout tone="info">
        <T variant="caption">커리큘럼은 CSV 파일로 통째로 교체됩니다. 앱에서는 조회만 하고, 교체는 PC 웹에서 해 주세요.</T>
      </Callout>
      {!sheet ? (
        <Card><EmptyState icon="table-chart" text="등록된 커리큘럼이 없습니다." /></Card>
      ) : (
        <>
          <Card style={{ gap: 4 }}>
            <T variant="subtitle">{sheet.title || '커리큘럼'}</T>
            <T variant="caption" tone="secondary">
              {[sheet.fileName, `${days.size}일 · ${sheet.rows.length}개 항목`, sheet.uploadedByName, sheet.uploadedAt ? fmt(sheet.uploadedAt) : ''].filter(Boolean).join(' · ')}
            </T>
          </Card>
          <Field label="찾기" value={query} onChangeText={setQuery} placeholder="과목 · 주제 · 날짜" />
          {rows.length === 0 ? <Card><EmptyState icon="search-off" text="찾는 항목이 없습니다." /></Card> : null}
          {[...days.entries()].map(([day, items]) => (
            <Card key={day} style={{ gap: 6 }}>
              <T variant="label" tone="primary">{day}일차{items[0]?.dateLabel ? ` · ${items[0].dateLabel}` : ''}</T>
              {items.map((row) => (
                <View key={`${row.dayIndex}-${row.order}`} style={{ gap: 2 }}>
                  <T variant="subtitle" style={{ fontSize: 15 }}>{[row.subject, row.topic].filter(Boolean).join(' · ')}</T>
                  {row.detail ? <T variant="caption" tone="secondary">{row.detail}</T> : null}
                </View>
              ))}
            </Card>
          ))}
        </>
      )}
    </Screen>
  );
}

// ── 수업 저장소 ────────────────────────────────────────

export function SourcesPage() {
  const { user } = useSession();
  const { palette } = useTheme();
  const cohortId = user?.cohortId ?? '';
  const sources = useSources().filter((source) => !source.cohortId || source.cohortId === cohortId);
  const notes = useNotes();
  const job = useJob();
  const [owner, setOwner] = useState('');
  const [owners, setOwners] = useState<GithubOwner[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!cohortId) return;
    let alive = true;
    listGithub(cohortId)
      .then((rows) => alive && setOwners(rows))
      .catch(() => alive && setOwners([]))
      .finally(() => alive && setLoaded(true));
    return () => {
      alive = false;
    };
  }, [cohortId]);

  const connect = () => {
    const name = owner.trim().replace(/^https?:\/\/github\.com\//i, '').replace(/\/.*$/, '');
    if (!/^[A-Za-z0-9-_.]+$/.test(name)) return job.fail('GitHub 계정 또는 조직 이름을 입력해 주세요. 예) playdata-skn');
    void job.run(async () => {
      await addGithub(cohortId, name);
      setOwners(await listGithub(cohortId));
      setOwner('');
    }, '연결했습니다. 동기화를 누르면 저장소를 가져옵니다.');
  };

  return (
    <Screen title={navLabel(RoutePaths.instructorStudySources, '수업 저장소')} onRefresh={refreshBootstrap}>
      {!cohortId ? <Card><EmptyState icon="folder" text="기수를 먼저 선택해 주세요." /></Card> : null}
      <Card style={{ gap: 12 }}>
        <T variant="subtitle">GitHub 연결</T>
        <Field label="계정 · 조직" value={owner} onChangeText={setOwner} placeholder="예) playdata-skn" />
        <Actions>
          <Half><Btn label="연결" icon="link" disabled={job.busy || !cohortId} onPress={connect} /></Half>
          <Half>
            <Btn label={job.busy ? '처리 중…' : '동기화'} icon="sync" tone="ghost" disabled={job.busy || !cohortId} onPress={() => void job.run(() => syncSources(cohortId), '동기화했습니다.')} />
          </Half>
        </Actions>
        {loaded && owners.length === 0 ? <Muted>연결된 계정이 없습니다.</Muted> : null}
        {owners.map((row) => (
          <View key={row.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <MaterialIcons name={row.lastError ? 'error-outline' : 'check-circle'} size={18} color={row.lastError ? palette.error : palette.success} />
            <View style={{ flex: 1 }}>
              <T variant="subtitle" style={{ fontSize: 15 }}>{row.owner}</T>
              <T variant="caption" tone={row.lastError ? 'error' : 'secondary'} numberOfLines={2}>
                {row.lastError || (row.lastSyncedAt ? `최근 동기화 ${fmt(row.lastSyncedAt)}` : '아직 동기화 전')}
              </T>
            </View>
            <Btn
              label="해제"
              tone="ghost"
              disabled={job.busy}
              onPress={() =>
                confirmAction('연결 해제', `${row.owner} 연결을 해제할까요?`, () =>
                  void job.run(async () => {
                    await removeGithub(row.id);
                    setOwners((prev) => prev.filter((item) => item.id !== row.id));
                  }, '해제했습니다.'),
                '해제')
              }
            />
          </View>
        ))}
      </Card>
      <JobNotice notice={job.notice} />
      <SectionLabel title={`저장소 ${sources.length}개`} />
      {sources.length === 0 ? <Card><EmptyState icon="folder-open" text="가져온 저장소가 없습니다." /></Card> : null}
      {sources.map((source) => (
        <Card key={source.id} style={{ gap: 6 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <T variant="subtitle" style={{ flex: 1 }}>{source.title}</T>
            <Badge label={source.isActive ? '공개' : '숨김'} tone={source.isActive ? 'success' : 'neutral'} />
          </View>
          <T variant="caption" tone="secondary" numberOfLines={1}>{source.repoUrl}</T>
          <T variant="caption" tone="secondary">노트 {notes.filter((note) => note.sourceId === source.id).length}개 · {source.branch}</T>
          <ToggleRow
            label="학생에게 공개"
            value={source.isActive}
            disabled={job.busy}
            onChange={(value) => void job.run(() => setSourceActive(source.id, value))}
          />
        </Card>
      ))}
      <ListGroup>
        <ListItem title="저장소 노트 만들기 · 범위 설정" subtitle="PC 웹에서 이용해 주세요" left={<MaterialIcons name="computer" size={20} color={palette.textHint} />} />
      </ListGroup>
    </Screen>
  );
}
