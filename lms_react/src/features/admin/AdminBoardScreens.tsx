import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { RoutePaths, adminBoardNoticeEditPath, adminBoardScheduledEditPath } from '../../app/routePaths';
import {
  deleteNotice,
  deleteScheduledNotice,
  publishScheduledNotice,
  setScheduledNoticeActive,
  upsertScheduledNotice,
  useNotices,
  useScheduledNotices,
} from '../../data/repository';
import { nextId } from '../../data/store';
import type { ScheduleRepeatType, ScheduledNotice } from '../../domain/types';
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
  TabPage,
  Tabs,
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
  const [toggleError, setToggleError] = useState<string | null>(null);
  const notices = useNotices();
  const scheduled = useScheduledNotices();
  const navigate = useNavigate();
  const createRef = useTourTarget(AdminTargets.boardCreate);

  return (
    <TabPage
      title="게시판 관리"
      description="공지와 예약 게시를 관리합니다. 학생 화면에 뜨는 알림은 「알림 팝업」 메뉴에서 보냅니다."
      tabs={
        <Tabs
          active={tab}
          onChange={(id) => setTab(id as typeof tab)}
          items={[
            { id: 'notices', label: '공지 관리', count: notices.length },
            { id: 'scheduled', label: '예약 공지', count: scheduled.length },
          ]}
        />
      }
      actions={
        tab === 'notices' ? (
          <Link className="btn btn--filled btn--md" ref={createRef} to={RoutePaths.adminBoardNoticeCreate}>
            공지 작성
          </Link>
        ) : (
          <Link className="btn btn--filled btn--md" to={RoutePaths.adminBoardScheduledCreate}>
            예약 공지 등록
          </Link>
        )
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
                  <Toggle
                    checked={s.isActive}
                    onChange={(v) =>
                      setScheduledNoticeActive(s, v).catch((err: unknown) =>
                        setToggleError(`「${s.title}」 동작을 바꾸지 못했습니다. ${err instanceof Error ? err.message : ''}`),
                      )
                    }
                  />
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

    </TabPage>
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
