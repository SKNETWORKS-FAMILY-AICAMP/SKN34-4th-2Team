import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { RoutePaths, adminAlertPopupEditPath } from '../../app/routePaths';
import {
  deleteAlertPopup,
  setAlertPopupActive,
  upsertAlertPopup,
  useAlertPopups,
  useStudents,
} from '../../data/repository';
import { dateKeyOf } from '../../data/seed';
import { nextId } from '../../data/store';
import type { AlertPopup, User } from '../../domain/types';
import {
  Badge,
  Button,
  Card,
  Chip,
  DataTable,
  Dialog,
  Field,
  PageHeader,
  Row,
  Spacer,
  TabPage,
  TextArea,
  TextInput,
  Toggle,
} from '../../ui/components';
import { formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { TargetPicker } from '../manager/TargetPicker';

function addDays(dateKey: string, days: number): string {
  const [y, m, d] = dateKey.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

function isExpired(popup: AlertPopup, today: string): boolean {
  return popup.endDate !== undefined && popup.endDate < today;
}

/** 받는 학생 — 지정이 없으면 기수의 활동 중인 학생 전체 */
function recipientsOf(popup: AlertPopup, students: User[]): User[] {
  const targets = popup.targetUserIds ?? [];
  return targets.length === 0 ? students : students.filter((s) => targets.includes(s.uid));
}

/** 알림 팝업(관리자) — 학생 화면 위에 뜨는 알림. 기수 전체 또는 고른 학생에게 보낸다 */
export function AdminAlertPopupsScreen() {
  const user = useCurrentUser();
  const [toggleError, setToggleError] = useState<string | null>(null);
  const [readsOf, setReadsOf] = useState<AlertPopup | null>(null);
  const popups = useAlertPopups();
  const students = useStudents(user.cohortId).filter((s) => s.isActive);
  const navigate = useNavigate();
  const today = dateKeyOf(new Date());
  const showing = popups.filter((p) => p.isActive && !isExpired(p, today)).length;
  const rows = [...popups].sort(
    (a, b) =>
      Number(isExpired(a, today) || !a.isActive) - Number(isExpired(b, today) || !b.isActive) ||
      (b.createdAt?.getTime() ?? 0) - (a.createdAt?.getTime() ?? 0),
  );

  return (
    <TabPage
      title="알림 팝업"
      description={`학생이 LMS 를 열면 화면 위에 뜨는 알림입니다. 기수 전체 또는 고른 학생에게만 보낼 수 있습니다. 지금 노출 중 ${showing}건.`}
      actions={
        <Link className="btn btn--filled btn--md" to={RoutePaths.adminAlertPopupCreate}>
          팝업 등록
        </Link>
      }
    >
      {toggleError !== null && (
        <div className="callout callout--error" role="alert">
          {toggleError}
          <button type="button" className="btn btn--text btn--sm" onClick={() => setToggleError(null)}>
            닫기
          </button>
        </div>
      )}

      <Card padded={false}>
        <DataTable
          rows={rows}
          rowKey={(p) => p.id}
          empty="등록된 팝업이 없습니다."
          columns={[
            {
              key: 'title',
              header: '제목',
              render: (p) => (
                <div>
                  <Row gap={6}>
                    {isExpired(p, today) && <Badge tone="neutral">기간 끝남</Badge>}
                    <span>{p.title}</span>
                  </Row>
                  <span className="hint">
                    {p.authorName} · {formatDateTime(p.createdAt)}
                  </span>
                </div>
              ),
            },
            {
              key: 'targets',
              header: '대상',
              width: '110px',
              render: (p) =>
                (p.targetUserIds?.length ?? 0) === 0 ? (
                  <span className="hint">기수 전체</span>
                ) : (
                  <Badge tone="info">{p.targetUserIds?.length}명 지정</Badge>
                ),
            },
            {
              key: 'window',
              header: '노출',
              width: '170px',
              render: (p) => (
                <div>
                  <div>
                    {p.startTime === undefined && p.endTime === undefined
                      ? '종일'
                      : `${p.startTime ?? '00:00'} ~ ${p.endTime ?? '23:59'}`}
                  </div>
                  <span className="hint">
                    {p.endDate === undefined ? '끌 때까지' : p.endDate === today ? '오늘까지' : `${p.endDate}까지`}
                  </span>
                </div>
              ),
            },
            {
              key: 'reads',
              header: '읽음',
              width: '90px',
              render: (p) => {
                const recipients = recipientsOf(p, students);
                const read = (p.readBy ?? []).filter((r) => recipients.some((s) => s.uid === r.uid)).length;
                return (
                  <button type="button" className="btn btn--text btn--sm" onClick={() => setReadsOf(p)}>
                    {read}/{recipients.length}
                  </button>
                );
              },
            },
            {
              key: 'active',
              header: '켜기',
              width: '80px',
              render: (p) => (
                <Toggle
                  checked={p.isActive && !isExpired(p, today)}
                  onChange={(v) => {
                    let next = p;
                    if (v && isExpired(p, today)) {
                      if (!window.confirm(`「${p.title}」은 ${p.endDate}에 기간이 끝났습니다. 오늘까지로 늘려서 켤까요?`)) return;
                      next = { ...p, endDate: today };
                    }
                    setAlertPopupActive(next, v).catch((err: unknown) =>
                      setToggleError(`「${p.title}」 노출을 바꾸지 못했습니다. ${err instanceof Error ? err.message : ''}`),
                    );
                  }}
                />
              ),
            },
            {
              key: 'actions',
              header: '',
              width: '140px',
              align: 'right',
              render: (p) => (
                <Row gap={4} wrap={false}>
                  <Spacer />
                  <Button size="sm" variant="outline" onClick={() => navigate(adminAlertPopupEditPath(p.id))}>
                    수정
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => {
                      if (window.confirm(`「${p.title}」 알림을 지울까요? 읽음 기록도 함께 지워집니다.`)) {
                        void deleteAlertPopup(p.id);
                      }
                    }}
                  >
                    삭제
                  </Button>
                </Row>
              ),
            },
          ]}
        />
      </Card>

      {readsOf !== null && <ReadsDialog popup={readsOf} students={students} onClose={() => setReadsOf(null)} />}
    </TabPage>
  );
}

function ReadsDialog({ popup, students, onClose }: { popup: AlertPopup; students: User[]; onClose: () => void }) {
  const recipients = recipientsOf(popup, students);
  const readAt = new Map((popup.readBy ?? []).map((r) => [r.uid, r.readAt]));
  const read = recipients.filter((s) => readAt.has(s.uid));
  const unread = recipients.filter((s) => !readAt.has(s.uid));
  return (
    <Dialog
      title={`「${popup.title}」 읽음 ${read.length}/${recipients.length}`}
      onClose={onClose}
      actions={<Button onClick={onClose}>닫기</Button>}
    >
      <p className="muted">학생이 팝업에서 확인 · 바로 가기 · 오늘 하루 보지 않기를 누르면 읽음으로 셉니다.</p>
      <div className="field">
        <span className="field__label">아직 안 읽음 {unread.length}명</span>
        <p>{unread.length === 0 ? '모두 읽었습니다.' : unread.map((s) => s.displayName).join(', ')}</p>
      </div>
      <div className="field">
        <span className="field__label">읽음 {read.length}명</span>
        {read.length === 0 ? (
          <p className="hint">아직 없습니다.</p>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {read.map((s) => (
              <li key={s.uid}>
                {s.displayName} <span className="hint">{formatDateTime(readAt.get(s.uid))}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Dialog>
  );
}

/** 알림 팝업 등록·수정 — admin_alert_popup_form_screen.dart */
export function AdminAlertPopupFormScreen() {
  const { popupId } = useParams<{ popupId: string }>();
  const popups = useAlertPopups();
  const existing = popups.find((p) => p.id === popupId);
  const user = useCurrentUser();
  const navigate = useNavigate();
  const today = dateKeyOf(new Date());

  const [title, setTitle] = useState(existing?.title ?? '');
  const [content, setContent] = useState(existing?.content ?? '');
  const [linkUrl, setLinkUrl] = useState(existing?.linkUrl ?? '');
  const [startTime, setStartTime] = useState(existing?.startTime ?? '');
  const [endTime, setEndTime] = useState(existing?.endTime ?? '');
  const [endDate, setEndDate] = useState(existing === undefined ? today : (existing.endDate ?? ''));
  const [isActive, setActive] = useState(existing?.isActive ?? true);
  const [sortOrder, setSortOrder] = useState(String(existing?.sortOrder ?? 0));
  const [targets, setTargets] = useState<string[]>(existing?.targetUserIds ?? []);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const students = useStudents(user.cohortId).filter((s) => s.isActive);

  const presets: { label: string; value: string }[] = [
    { label: '오늘만', value: today },
    { label: '3일', value: addDays(today, 2) },
    { label: '1주', value: addDays(today, 6) },
    { label: '끌 때까지', value: '' },
  ];

  const save = () => {
    if (title.trim() === '') {
      setError('제목을 입력해 주세요.');
      return;
    }
    if (endDate !== '' && endDate < today && isActive) {
      setError('노출 마지막 날이 지났습니다. 날짜를 고치거나 「끌 때까지」를 골라 주세요.');
      return;
    }
    if (startTime !== '' && endTime !== '' && endTime <= startTime) {
      setError('노출 종료 시각은 시작 시각보다 늦어야 합니다.');
      return;
    }
    const popup: AlertPopup = {
      targetUserIds: targets,
      id: existing?.id ?? nextId('ap'),
      title: title.trim(),
      content: content.trim(),
      authorName: user.displayName,
      isActive,
      sortOrder: Number(sortOrder) || 0,
      linkUrl: linkUrl.trim() === '' ? undefined : linkUrl.trim(),
      startTime: startTime === '' ? undefined : startTime,
      endTime: endTime === '' ? undefined : endTime,
      endDate: endDate === '' ? undefined : endDate,
      createdAt: existing?.createdAt ?? new Date(),
      readBy: existing?.readBy,
    };
    setSaving(true);
    void upsertAlertPopup(popup)
      .then(() => navigate(RoutePaths.adminAlertPopups))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '저장에 실패했습니다.');
        setSaving(false);
      });
  };

  return (
    <div className="screen__inner">
      <PageHeader title={existing === undefined ? '알림 팝업 등록' : '알림 팝업 수정'} />
      <Card>
        <Field label="제목" error={error ?? undefined}>
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="내용">
          <TextArea rows={4} value={content} onChange={(e) => setContent(e.target.value)} />
        </Field>
        <Field label="링크" hint="비워 두면 안내만 보여 줍니다. /attendance-request 처럼 LMS 주소를 넣으면 「바로 가기」로 그 화면을 엽니다.">
          <TextInput value={linkUrl} onChange={(e) => setLinkUrl(e.target.value)} placeholder="https:// 또는 /attendance-request" />
        </Field>
        <div className="field">
          <span className="field__label">받는 학생</span>
          <TargetPicker cohortId={user.cohortId} students={students} selected={targets} onChange={setTargets} />
        </div>
        <div className="field">
          <span className="field__label">노출 기간</span>
          <Row gap={6}>
            {presets.map((preset) => (
              <Chip key={preset.label} selected={endDate === preset.value} onClick={() => setEndDate(preset.value)}>
                {preset.label}
              </Chip>
            ))}
            <TextInput
              type="date"
              aria-label="노출 마지막 날"
              style={{ width: 170 }}
              min={today}
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </Row>
          <span className="field__hint">
            {endDate === '' ? '끌 때까지 계속 보입니다.' : `${endDate}까지 보이고, 그다음 날부터 자동으로 사라집니다.`}
          </span>
        </div>
        <div className="grid grid--2">
          <Field label="하루 중 노출 시작" hint="비우면 종일 노출합니다.">
            <TextInput type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
          </Field>
          <Field label="하루 중 노출 종료">
            <TextInput type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
          </Field>
        </div>
        <Field label="표시 순서" hint="작을수록 먼저 보여 줍니다.">
          <TextInput type="number" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} />
        </Field>
        <Toggle checked={isActive} onChange={setActive} label="지금 노출" />
        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(RoutePaths.adminAlertPopups)}>
            취소
          </Button>
          <Button onClick={save} disabled={saving}>
            {saving ? '저장 중' : '저장'}
          </Button>
        </Row>
      </Card>
    </div>
  );
}
