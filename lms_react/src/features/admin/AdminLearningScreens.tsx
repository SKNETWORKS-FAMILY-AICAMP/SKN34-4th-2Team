import { useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { RoutePaths, adminStudyRoomPackagePath } from '../../app/routePaths';
import {
  deleteInflearnPackage,
  upsertInflearnPackage,
  useCohorts,
  useInflearnPackages,
  useStudySources,
  useYoutubeRecommendations,
} from '../../data/repository';
import { nextId } from '../../data/store';
import type {
  InflearnCourse,
  InflearnPackage,
  InflearnPackageType,
  InflearnUnit,
} from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { StudySourcesPanel } from '../study/StudySourcesPanel';
import {
  Button,
  Card,
  Chip,
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

const packageTypeLabels: Record<InflearnPackageType, string> = {
  review: '예복습',
  preview: '예습',
  bonus: '보너스',
};

/** 설문 · 제출(관리자) — 화면은 features/forms 에 둔다(LMS 설문 편집 · 결과) */
export { AdminFormTaskFormScreen, AdminFormTasksScreen } from '../forms/AdminFormScreens';

/** 학습실(관리자) — admin_study_room_screen.dart */
export function AdminStudyRoomScreen() {
  const packages = useInflearnPackages();
  const videos = useYoutubeRecommendations();
  const cohorts = useCohorts();
  const sources = useStudySources();
  const navigate = useNavigate();
  // 저장소가 있는 첫 기수부터 — 없으면 첫 기수
  const [sourceCohort, setSourceCohort] = useState(
    () => sources.find((s) => s.cohortId)?.cohortId ?? cohorts[0]?.cohortId ?? '',
  );

  return (
    <div className="admin-page admin-page--wide study-admin">
      <PageHeader title="학습실 관리" description="인프런 강의 패키지 · 관심사 YouTube 추천 · 수업 저장소를 관리합니다." />
      <SectionHead
        title="인프런 강의 패키지"
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
        title="수업 저장소"
        desc="기수에 GitHub 조직이나 강사 계정을 연결하면 저장소가 학생 공부방에 자동으로 올라갑니다. 올리지 않을 저장소는 숨기세요."
        action={
          <Select
            id="admin-source-cohort"
            aria-label="기수"
            value={sourceCohort}
            onChange={(e) => setSourceCohort(e.target.value)}
          >
            {cohorts.map((c) => (
              <option key={c.cohortId} value={c.cohortId}>
                {c.name}
              </option>
            ))}
          </Select>
        }
      />
      {sourceCohort !== '' && <StudySourcesPanel cohortId={sourceCohort} />}
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
  const [units, setUnits] = useState<InflearnUnit[]>(existing?.units ?? []);
  // 원본은 「단원별(표) / 단순 목록」 둘 중 하나로 넣는다. 단원이 있으면 표 모양으로 시작한다
  const [layout, setLayout] = useState<'units' | 'flat'>((existing?.units ?? []).length > 0 ? 'units' : 'flat');
  const [sortOrder, setSortOrder] = useState(String(existing?.sortOrder ?? packages.length + 1));
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
      units: layout === 'units' ? units.filter((u) => u.name.trim() !== '') : [],
      courses: layout === 'flat' ? courses : units.flatMap((u) => u.courses),
      isPublished,
      sortOrder: Number(sortOrder) || 0,
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
        <Field label="정렬 순서" hint="작을수록 먼저 보여 줍니다.">
          <TextInput type="number" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} />
        </Field>
        <Toggle checked={isPublished} onChange={setPublished} label="기수에 공개" />
      </Card>

      <Card title="강의 넣는 방식">
        <Row>
          {([
            ['units', '단원별 (표 형태)'],
            ['flat', '단순 목록'],
          ] as const).map(([id, label]) => (
            <Chip key={id} selected={layout === id} onClick={() => setLayout(id)}>
              {label}
            </Chip>
          ))}
        </Row>
        <span className="muted">
          단원별은 단원 밑에 강의를 묶어 넣습니다. 학생 화면에서 단원 제목과 함께 보입니다.
        </span>
      </Card>

      {layout === 'units' && (
        <Card title={`단원 (${units.length})`}>
          {units.map((unit, unitIndex) => (
            <Card key={unitIndex} title={`단원 ${unitIndex + 1}`}>
              <Row gap={8} wrap={false}>
                <Field label="단원 이름">
                  <TextInput
                    value={unit.name}
                    placeholder="예) Python"
                    onChange={(e) =>
                      setUnits((list) =>
                        list.map((u, i) => (i === unitIndex ? { ...u, name: e.target.value } : u)),
                      )
                    }
                  />
                </Field>
                <Button
                  variant="text"
                  onClick={() => setUnits((list) => list.filter((_, i) => i !== unitIndex))}
                >
                  단원 삭제
                </Button>
              </Row>
              <ul className="list">
                {unit.courses.map((course, courseIndex) => (
                  <li key={courseIndex} className="list__item">
                    <span>{course.title}</span>
                    <Spacer />
                    <span className="hint">{course.url}</span>
                    <Button
                      variant="text"
                      onClick={() =>
                        setUnits((list) =>
                          list.map((u, i) =>
                            i === unitIndex
                              ? { ...u, courses: u.courses.filter((_, c) => c !== courseIndex) }
                              : u,
                          ),
                        )
                      }
                    >
                      삭제
                    </Button>
                  </li>
                ))}
              </ul>
              <UnitCourseAdder
                onAdd={(course) =>
                  setUnits((list) =>
                    list.map((u, i) => (i === unitIndex ? { ...u, courses: [...u.courses, course] } : u)),
                  )
                }
              />
            </Card>
          ))}
          <Button variant="outline" onClick={() => setUnits((list) => [...list, { name: '', courses: [] }])}>
            단원 추가
          </Button>
        </Card>
      )}

      {layout === 'flat' && (
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
      )}

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

/** 단원 밑에 강의 한 줄 넣기 — 단원마다 입력칸이 따로 있어야 해서 따로 뺀다 */
function UnitCourseAdder({ onAdd }: { onAdd(course: InflearnCourse): void }) {
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  return (
    <Row gap={8} wrap={false}>
      <TextInput value={title} placeholder="강의명" onChange={(e) => setTitle(e.target.value)} />
      <TextInput value={url} placeholder="URL" onChange={(e) => setUrl(e.target.value)} />
      <Button
        variant="outline"
        onClick={() => {
          if (title.trim() === '') return;
          onAdd({ title: title.trim(), url: url.trim() });
          setTitle('');
          setUrl('');
        }}
      >
        강의 추가
      </Button>
    </Row>
  );
}

export { StatTile };
