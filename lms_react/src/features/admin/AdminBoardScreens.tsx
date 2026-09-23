import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import {
  RoutePaths,
  adminBoardAlertPopupEditPath,
  adminBoardNoticeEditPath,
  adminBoardScheduledEditPath,
} from '../../app/routePaths';
import {
  deleteAlertPopup,
  deleteNotice,
  deleteScheduledNotice,
  publishScheduledNotice,
  upsertAlertPopup,
  upsertScheduledNotice,
  useAlertPopups,
  useNotices,
  useScheduledNotices,
} from '../../data/repository';
import { nextId } from '../../data/store';
import type { AlertPopup, ScheduleRepeatType, ScheduledNotice } from '../../domain/types';
import { AdminTargets } from '../../tour/targets';
import { useTourTarget } from '../../tour/useTourTarget';
import {
  Badge,
  Button,
  Card,
  Checkbox,
  DataTable,
  Field,
  PageHeader,
  Row,
  Select,
  Spacer,
  TextArea,
  TextInput,
  Toggle,
} from '../../ui/components';
import { formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';

const repeatLabels: Record<ScheduleRepeatType, string> = {
  once: '한 번',
  daily: '매일',
  weekly: '매주',
};

const weekdayLabels = ['월', '화', '수', '목', '금', '토', '일'];

/** 게시판(관리자) — features/admin/presentation/admin_board_screen.dart */
export function AdminBoardScreen() {
  const [tab, setTab] = useState('notices');
  const notices = useNotices();
  const scheduled = useScheduledNotices();
  const popups = useAlertPopups();
  const navigate = useNavigate();
  const createRef = useTourTarget(AdminTargets.boardCreate);

  return (
    <div className="screen__inner">
      <PageHeader
        title="게시판 관리"
        description="공지 · 예약 게시 · 로그인 알림 팝업을 관리합니다."
        actions={
          tab === 'notices' ? (
            <Link className="btn btn--filled btn--md" ref={createRef} to={RoutePaths.adminBoardNoticeCreate}>
              공지 작성
            </Link>
          ) : tab === 'scheduled' ? (
            <Link className="btn btn--filled btn--md" to={RoutePaths.adminBoardScheduledCreate}>
              예약 공지 등록
            </Link>
          ) : (
            <Link className="btn btn--filled btn--md" to={RoutePaths.adminBoardAlertPopupCreate}>
              팝업 등록
            </Link>
          )
        }
      />

      <div className="board-tabs board-tabs--inline">
        {(
          [
            ['notices', '공지 관리'],
            ['scheduled', '예약 공지'],
            ['popups', '알림 팝업'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`board-tab${tab === id ? ' board-tab--on' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'notices' && (
        <Card padded={false}>
          <DataTable
            rows={notices}
            rowKey={(n) => n.id}
            empty="등록된 공지가 없습니다."
            columns={[
              {
                key: 'title',
                header: '제목',
                render: (n) => (
                  <Row gap={6}>
                    {n.isFavorite && <Badge tone="error">중요</Badge>}
                    {n.channelLabel !== undefined && <Badge tone="info">{n.channelLabel}</Badge>}
                    <span>{n.title}</span>
                  </Row>
                ),
              },
              { key: 'author', header: '작성자', width: '130px', render: (n) => n.authorName },
              { key: 'at', header: '작성일', width: '160px', render: (n) => formatDateTime(n.createdAt) },
              {
                key: 'actions',
                header: '',
                width: '140px',
                align: 'right',
                render: (n) => (
                  <Row gap={4} wrap={false}>
                    <Spacer />
                    <Button size="sm" variant="outline" onClick={() => navigate(adminBoardNoticeEditPath(n.id))}>
                      수정
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => deleteNotice(n.id)}>
                      삭제
                    </Button>
                  </Row>
                ),
              },
            ]}
          />
        </Card>
      )}

      {tab === 'scheduled' && (
        <Card padded={false}>
          <DataTable
            rows={scheduled}
            rowKey={(s) => s.id}
            empty="예약 공지가 없습니다."
            columns={[
              { key: 'title', header: '제목', render: (s) => s.title },
              {
                key: 'repeat',
                header: '반복',
                width: '150px',
                render: (s) =>
                  s.repeatType === 'weekly'
                    ? `매주 ${weekdayLabels[(s.weekday - 1) % 7]}요일 ${s.publishTime}`
                    : `${repeatLabels[s.repeatType]} ${s.publishTime}`,
              },
              { key: 'last', header: '최근 발행', width: '160px', render: (s) => formatDateTime(s.lastPublishedAt) },
              {
                key: 'active',
                header: '동작',
                width: '90px',
                render: (s) => (
                  <Toggle checked={s.isActive} onChange={(v) => void upsertScheduledNotice({ ...s, isActive: v })} />
                ),
              },
              {
                key: 'actions',
                header: '',
                width: '240px',
                align: 'right',
                render: (s) => (
                  <Row gap={4} wrap={false}>
                    <Spacer />
                    <Button size="sm" variant="outline" onClick={() => void publishScheduledNotice(s.id)}>
                      지금 게시
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => navigate(adminBoardScheduledEditPath(s.id))}>
                      수정
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => void deleteScheduledNotice(s.id)}>
                      삭제
                    </Button>
                  </Row>
                ),
              },
            ]}
          />
        </Card>
      )}

      {tab === 'popups' && (
        <Card padded={false}>
          <DataTable
            rows={popups}
            rowKey={(p) => p.id}
            empty="등록된 팝업이 없습니다."
            columns={[
              { key: 'title', header: '제목', render: (p) => p.title },
              {
                key: 'window',
                header: '노출 시간',
                width: '160px',
                render: (p) =>
                  p.startTime === undefined && p.endTime === undefined
                    ? '종일'
                    : `${p.startTime ?? '00:00'} ~ ${p.endTime ?? '23:59'}`,
              },
              {
                key: 'active',
                header: '노출',
                width: '90px',
                render: (p) => (
                  <Toggle checked={p.isActive} onChange={(v) => void upsertAlertPopup({ ...p, isActive: v })} />
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
                    <Button size="sm" variant="outline" onClick={() => navigate(adminBoardAlertPopupEditPath(p.id))}>
                      수정
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => void deleteAlertPopup(p.id)}>
                      삭제
                    </Button>
                  </Row>
                ),
              },
            ]}
          />
        </Card>
      )}
    </div>
  );
}

/** 예약 공지 등록·수정 — admin_scheduled_notice_form_screen.dart */
export function AdminScheduledNoticeFormScreen() {
  const { scheduledId } = useParams<{ scheduledId: string }>();
  const scheduled = useScheduledNotices();
  const existing = scheduled.find((s) => s.id === scheduledId);
  const user = useCurrentUser();
  const navigate = useNavigate();

  const [title, setTitle] = useState(existing?.title ?? '');
  const [content, setContent] = useState(existing?.content ?? '');
  const [repeatType, setRepeatType] = useState<ScheduleRepeatType>(existing?.repeatType ?? 'daily');
  const [publishTime, setPublishTime] = useState(existing?.publishTime ?? '08:30');
  const [weekday, setWeekday] = useState(existing?.weekday ?? 1);
  const [isFavorite, setFavorite] = useState(existing?.isFavorite ?? false);
  const [isActive, setActive] = useState(existing?.isActive ?? true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const save = () => {
    if (title.trim() === '') {
      setError('제목을 입력해 주세요.');
      return;
    }
    const notice: ScheduledNotice = {
      id: existing?.id ?? nextId('sn'),
      title: title.trim(),
      content: content.trim(),
      authorName: user.displayName,
      isFavorite,
      repeatType,
      publishTime,
      weekday,
      isActive,
      lastPublishedAt: existing?.lastPublishedAt,
      createdAt: existing?.createdAt ?? new Date(),
    };
    setSaving(true);
    void upsertScheduledNotice(notice)
      .then(() => navigate(RoutePaths.adminBoard))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '저장에 실패했습니다.');
        setSaving(false);
      });
  };

  return (
    <div className="screen__inner">
      <PageHeader title={existing === undefined ? '예약 공지 등록' : '예약 공지 수정'} />
      <Card>
        <Field label="제목" error={error ?? undefined}>
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="내용">
          <TextArea rows={6} value={content} onChange={(e) => setContent(e.target.value)} />
        </Field>
        <div className="grid grid--3">
          <Field label="반복">
            <Select value={repeatType} onChange={(e) => setRepeatType(e.target.value as ScheduleRepeatType)}>
              {Object.entries(repeatLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="발행 시각">
            <TextInput type="time" value={publishTime} onChange={(e) => setPublishTime(e.target.value)} />
          </Field>
          {repeatType === 'weekly' && (
            <Field label="요일">
              <Select value={weekday} onChange={(e) => setWeekday(Number(e.target.value))}>
                {weekdayLabels.map((label, i) => (
                  <option key={label} value={i + 1}>
                    {label}요일
                  </option>
                ))}
              </Select>
            </Field>
          )}
        </div>
        <Checkbox checked={isFavorite} onChange={setFavorite} label="중요 공지로 올립니다" />
        <Toggle checked={isActive} onChange={setActive} label="예약 동작" />
        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(RoutePaths.adminBoard)}>
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

/** 알림 팝업 등록·수정 — admin_alert_popup_form_screen.dart */
export function AdminAlertPopupFormScreen() {
  const { popupId } = useParams<{ popupId: string }>();
  const popups = useAlertPopups();
  const existing = popups.find((p) => p.id === popupId);
  const user = useCurrentUser();
  const navigate = useNavigate();

  const [title, setTitle] = useState(existing?.title ?? '');
  const [content, setContent] = useState(existing?.content ?? '');
  const [linkUrl, setLinkUrl] = useState(existing?.linkUrl ?? '');
  const [startTime, setStartTime] = useState(existing?.startTime ?? '');
  const [endTime, setEndTime] = useState(existing?.endTime ?? '');
  const [isActive, setActive] = useState(existing?.isActive ?? true);
  const [sortOrder, setSortOrder] = useState(String(existing?.sortOrder ?? 0));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const save = () => {
    if (title.trim() === '') {
      setError('제목을 입력해 주세요.');
      return;
    }
    const popup: AlertPopup = {
      id: existing?.id ?? nextId('ap'),
      title: title.trim(),
      content: content.trim(),
      authorName: user.displayName,
      isActive,
      sortOrder: Number(sortOrder) || 0,
      linkUrl: linkUrl.trim() === '' ? undefined : linkUrl.trim(),
      startTime: startTime === '' ? undefined : startTime,
      endTime: endTime === '' ? undefined : endTime,
      createdAt: existing?.createdAt ?? new Date(),
    };
    setSaving(true);
    void upsertAlertPopup(popup)
      .then(() => navigate(RoutePaths.adminBoard))
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
        <Field label="링크" hint="비워 두면 링크 없이 안내만 보여 줍니다.">
          <TextInput value={linkUrl} onChange={(e) => setLinkUrl(e.target.value)} placeholder="https://" />
        </Field>
        <div className="grid grid--2">
          <Field label="노출 시작" hint="비우면 종일 노출합니다.">
            <TextInput type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
          </Field>
          <Field label="노출 종료">
            <TextInput type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
          </Field>
        </div>
        <Field label="표시 순서" hint="작을수록 먼저 보여 줍니다.">
          <TextInput type="number" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} />
        </Field>
        <Toggle checked={isActive} onChange={setActive} label="지금 노출" />
        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(RoutePaths.adminBoard)}>
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
