import { useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { RoutePaths, adminFormTaskEditPath, adminStudyRoomPackagePath } from '../../app/routePaths';
import {
  deleteFormTask,
  deleteInflearnPackage,
  upsertFormTask,
  upsertInflearnPackage,
  useFormResponses,
  useFormTasks,
  useInflearnPackages,
  useStudents,
  useStudySources,
  useYoutubeRecommendations,
} from '../../data/repository';
import { nextId } from '../../data/store';
import type { FormTask, InflearnPackage, InflearnPackageType } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import {
  Badge,
  Button,
  Card,
  Dialog,
  Field,
  PageHeader,
  Row,
  Select,
  Spacer,
  StatTile,
  TextArea,
  TextInput,
  Toggle,
} from '../../ui/components';
import { formatDate, formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';

const packageTypeLabels: Record<InflearnPackageType, string> = {
  review: '예복습',
  preview: '예습',
  bonus: '보너스',
};

const toInputDateTime = (d: Date) => {
  const pad = (v: number) => String(v).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

/** 설문 · 제출(관리자) — admin_form_tasks_screen.dart */
export function AdminFormTasksScreen() {
  const user = useCurrentUser();
  const tasks = useFormTasks();
  const responses = useFormResponses();
  const students = useStudents(user.cohortId).filter((s) => s.isActive);
  const navigate = useNavigate();
  const [detail, setDetail] = useState<FormTask | null>(null);

  return (
    <div className="list-page">
      <div className="pill-head">
        <h1 className="pill-head__title">설문 · 제출 관리</h1>
        <div className="pill-head__trailing">
          <Link className="btn btn--filled btn--md" to={RoutePaths.adminFormTasksCreate}>
            <Icon name="add" size={18} />
            설문 등록
          </Link>
        </div>
      </div>

      {tasks.length === 0 ? (
        <div className="list-page__empty">
          <Icon name="assignment" size={44} />
          <p>등록된 설문이 없습니다</p>
        </div>
      ) : (
        <div className="list-page__body">
          {tasks.map((t) => {
            const count = responses.filter((r) => r.taskId === t.id).length;
            return (
              <div key={t.id} className="task-row">
                <button type="button" className="task-row__main" onClick={() => setDetail(t)}>
                  <span className="task-row__icon">
                    <Icon name="description" size={22} />
                  </span>
                  <span className="task-row__body">
                    <strong>{t.title}</strong>
                    <span className="hint">
                      마감 {formatDate(t.dueAt)} · 제출 {count}명
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="삭제"
                  onClick={() => deleteFormTask(t.id)}
                >
                  <Icon name="delete" size={20} />
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="수정"
                  onClick={() => navigate(adminFormTaskEditPath(t.id))}
                >
                  <Icon name="chevron_right" size={20} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {detail !== null && (
        <Dialog
          title={`${detail.title} 제출 현황`}
          width={560}
          onClose={() => setDetail(null)}
          actions={<Button onClick={() => setDetail(null)}>닫기</Button>}
        >
          <ul className="list">
            {students.map((s) => {
              const response = responses.find((r) => r.taskId === detail.id && r.userId === s.uid);
              return (
                <li key={s.uid} className="list__item">
                  <span>{s.displayName}</span>
                  <Spacer />
                  {response === undefined ? (
                    <Badge tone="warning">미제출</Badge>
                  ) : (
                    <>
                      <span className="hint">{formatDateTime(response.submittedAt)}</span>
                      <Badge tone="success">제출</Badge>
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        </Dialog>
      )}
    </div>
  );
}

/** 설문 등록·수정 — admin_form_task_form */
export function AdminFormTaskFormScreen() {
  const { taskId } = useParams<{ taskId: string }>();
  const tasks = useFormTasks();
  const existing = tasks.find((t) => t.id === taskId);
  const navigate = useNavigate();

  const [title, setTitle] = useState(existing?.title ?? '');
  const [description, setDescription] = useState(existing?.description ?? '');
  const [formUrl, setFormUrl] = useState(existing?.formUrl ?? '');
  const [guideUrl, setGuideUrl] = useState(existing?.notionGuideUrl ?? '');
  const [dueAt, setDueAt] = useState(
    toInputDateTime(existing?.dueAt ?? new Date(Date.now() + 7 * 86400000)),
  );
  const [published, setPublished] = useState(existing?.published ?? true);
  const [error, setError] = useState<string | null>(null);

  const save = () => {
    if (title.trim() === '' || formUrl.trim() === '') {
      setError('제목과 폼 주소는 반드시 입력해야 합니다.');
      return;
    }
    upsertFormTask({
      id: existing?.id ?? nextId('form'),
      title: title.trim(),
      description: description.trim(),
      formUrl: formUrl.trim(),
      notionGuideUrl: guideUrl.trim() === '' ? undefined : guideUrl.trim(),
      dueAt: new Date(dueAt),
      published,
      responseCount: existing?.responseCount ?? 0,
      createdAt: existing?.createdAt ?? new Date(),
    });
    navigate(RoutePaths.adminFormTasks);
  };

  return (
    <div className="screen__inner">
      <PageHeader title={existing === undefined ? '설문 등록' : '설문 수정'} />
      <Card>
        <Field label="제목" error={error ?? undefined}>
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="설명">
          <TextArea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label="구글폼 주소">
          <TextInput value={formUrl} onChange={(e) => setFormUrl(e.target.value)} placeholder="https://docs.google.com/forms/..." />
        </Field>
        <Field label="작성 가이드(노션)">
          <TextInput value={guideUrl} onChange={(e) => setGuideUrl(e.target.value)} placeholder="https://notion.so/..." />
        </Field>
        <Field label="마감 일시">
          <TextInput type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} />
        </Field>
        <Toggle checked={published} onChange={setPublished} label="학생에게 공개" />
        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(RoutePaths.adminFormTasks)}>
            취소
          </Button>
          <Button onClick={save}>저장</Button>
        </Row>
      </Card>
    </div>
  );
}

/** 학습실(관리자) — admin_study_room_screen.dart */
export function AdminStudyRoomScreen() {
  const packages = useInflearnPackages();
  const videos = useYoutubeRecommendations();
  const sources = useStudySources();
  const navigate = useNavigate();

  return (
    <div className="admin-page admin-page--wide study-admin">
      <SectionHead
        title="학습실"
        desc="인프런 강의 패키지를 등록하고 기수에 공개하세요."
        action={
          <Link className="btn btn--filled btn--md" to={RoutePaths.adminStudyRoomCreate}>
            <Icon name="add" size={18} />
            패키지 등록
          </Link>
        }
      />

      {packages.map((p) => (
        <div key={p.id} className="media-row">
          <button
            type="button"
            className="media-row__main"
            onClick={() => navigate(adminStudyRoomPackagePath(p.id))}
          >
            <span className="media-row__thumb media-row__thumb--pkg">
              <Icon name="menu_book" size={22} />
            </span>
            <span className="media-row__body">
              <strong>{p.title}</strong>
              <span className="hint">
                {p.isPublished ? '공개' : '비공개'} · {packageTypeLabels[p.type]} · {p.subject}
              </span>
            </span>
          </button>
          <Toggle
            checked={p.isPublished}
            onChange={(v) => upsertInflearnPackage({ ...p, isPublished: v })}
          />
          <button
            type="button"
            className="icon-btn media-row__danger"
            aria-label="삭제"
            onClick={() => deleteInflearnPackage(p.id)}
          >
            <Icon name="delete" size={20} />
          </button>
        </div>
      ))}

      <SectionHead
        title="관심사 YouTube 추천"
        desc="선택적 수동 큐레이션입니다. 학생 학습실 추천은 커리큘럼 주차 + YouTube API로 자동 표시됩니다."
        action={
          <button type="button" className="btn btn--filled btn--md">
            <Icon name="add" size={18} />
            영상 등록
          </button>
        }
      />

      {videos.map((v) => (
        <div key={v.id} className="media-row">
          <a className="media-row__main" href={v.youtubeUrl} target="_blank" rel="noreferrer">
            <span className="media-row__thumb">
              <Icon name="play_arrow" size={22} />
            </span>
            <span className="media-row__body">
              <strong>{v.title}</strong>
              <span className="hint">
                {v.isPublished ? '공개' : '비공개'} · {v.tags.join(', ')}
              </span>
            </span>
          </a>
          <button type="button" className="icon-btn" aria-label="미리보기">
            <Icon name="visibility" size={20} />
          </button>
          <button type="button" className="icon-btn" aria-label="수정">
            <Icon name="edit" size={20} />
          </button>
          <button type="button" className="icon-btn media-row__danger" aria-label="삭제">
            <Icon name="delete" size={20} />
          </button>
        </div>
      ))}

      <SectionHead
        title="공부 소스"
        desc="기수별 수업 저장소를 등록합니다. 공개 GitHub 저장소면 토큰 없이 됩니다. 학생은 활성 소스만 보고, 고른 범위만 정리합니다."
        action={
          <button type="button" className="btn btn--filled btn--md">
            <Icon name="add" size={18} />
            소스 추가
          </button>
        }
      />

      {sources.map((src) => (
        <div key={src.id} className="media-row">
          <span className="media-row__main media-row__main--plain">
            <span className="media-row__body">
              <strong>{src.title}</strong>
              <span className="media-row__repo">{src.repoUrl.replace(/^https?:\/\/github\.com\//, '')}</span>
              <span className="hint">
                {src.branch} · {src.allowedPrefixes.join(', ')}
              </span>
            </span>
          </span>
          <span className={src.isActive ? 'media-row__on' : 'hint'}>
            {src.isActive ? '공개' : '비공개'}
          </span>
          <button type="button" className="icon-btn" aria-label="수정">
            <Icon name="edit" size={20} />
          </button>
          <button type="button" className="icon-btn" aria-label="숨기기">
            <Icon name="visibility_off" size={20} />
          </button>
        </div>
      ))}
    </div>
  );
}

/** 구역 머리 — 제목·설명과 오른쪽 단추 */
function SectionHead({
  title,
  desc,
  action,
}: {
  title: string;
  desc: string;
  action: ReactNode;
}) {
  return (
    <header className="sec-head">
      <div>
        <h2 className="sec-head__title">{title}</h2>
        <p className="sec-head__desc">{desc}</p>
      </div>
      <span className="spacer" />
      {action}
    </header>
  );
}

/** 인프런 패키지 등록·수정 — admin_inflearn_package_form_screen.dart */
export function AdminInflearnPackageFormScreen() {
  const { packageId } = useParams<{ packageId: string }>();
  const packages = useInflearnPackages();
  const existing = packages.find((p) => p.id === packageId);
  const navigate = useNavigate();

  const [title, setTitle] = useState(existing?.title ?? '');
  const [subject, setSubject] = useState(existing?.subject ?? '');
  const [type, setType] = useState<InflearnPackageType>(existing?.type ?? 'review');
  const [summary, setSummary] = useState(existing?.summary ?? '');
  const [isPublished, setPublished] = useState(existing?.isPublished ?? false);
  const [courses, setCourses] = useState(existing?.courses ?? []);
  const [courseTitle, setCourseTitle] = useState('');
  const [courseUrl, setCourseUrl] = useState('');
  const [error, setError] = useState<string | null>(null);

  const save = () => {
    if (title.trim() === '') {
      setError('제목을 입력해 주세요.');
      return;
    }
    const pkg: InflearnPackage = {
      id: existing?.id ?? nextId('pkg'),
      title: title.trim(),
      subject: subject.trim(),
      type,
      summary: summary.trim() === '' ? undefined : summary.trim(),
      units: existing?.units ?? [],
      courses,
      isPublished,
      sortOrder: existing?.sortOrder ?? packages.length + 1,
      publishedAt: isPublished ? new Date() : existing?.publishedAt,
    };
    upsertInflearnPackage(pkg);
    navigate(RoutePaths.adminStudyRoom);
  };

  return (
    <div className="screen__inner">
      <PageHeader title={existing === undefined ? '패키지 등록' : '패키지 수정'} />
      <Card>
        <Field label="제목" error={error ?? undefined}>
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <div className="grid grid--2">
          <Field label="교과목">
            <TextInput value={subject} onChange={(e) => setSubject(e.target.value)} />
          </Field>
          <Field label="유형">
            <Select value={type} onChange={(e) => setType(e.target.value as InflearnPackageType)}>
              {Object.entries(packageTypeLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="설명">
          <TextArea rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} />
        </Field>
        <Toggle checked={isPublished} onChange={setPublished} label="기수에 공개" />
      </Card>

      <Card title={`강의 목록 (${courses.length})`}>
        <Row gap={8} wrap={false}>
          <TextInput value={courseTitle} placeholder="강의 제목" onChange={(e) => setCourseTitle(e.target.value)} />
          <TextInput value={courseUrl} placeholder="https://www.inflearn.com/..." onChange={(e) => setCourseUrl(e.target.value)} />
          <Button
            onClick={() => {
              if (courseTitle.trim() === '') return;
              setCourses((c) => [...c, { title: courseTitle.trim(), url: courseUrl.trim() }]);
              setCourseTitle('');
              setCourseUrl('');
            }}
          >
            추가
          </Button>
        </Row>
        <ul className="list">
          {courses.map((course, i) => (
            <li key={`${course.title}-${i}`} className="list__item">
              <span>{course.title}</span>
              <Spacer />
              <Button size="sm" variant="text" onClick={() => setCourses((c) => c.filter((_, x) => x !== i))}>
                삭제
              </Button>
            </li>
          ))}
        </ul>
      </Card>

      <Row>
        <Spacer />
        <Button variant="outline" onClick={() => navigate(RoutePaths.adminStudyRoom)}>
          취소
        </Button>
        <Button onClick={save}>저장</Button>
      </Row>
    </div>
  );
}

export { StatTile };
