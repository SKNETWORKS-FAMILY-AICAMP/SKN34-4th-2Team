import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { RoutePaths, studyRoomNoteSourcePath } from '../../app/routePaths';
import {
  createDemoStudyNote,
  useInflearnPackages,
  useMyPracticeAttempts,
  usePracticeSets,
  useStudyNotes,
  useStudySources,
  useYoutubeRecommendations,
} from '../../data/repository';
import type { InflearnPackage } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import {
  Badge,
  Button,
  Card,
  Checkbox,
  PageHeader,
  Row,
  Spacer,
  Tabs,
} from '../../ui/components';
import { formatDate } from '../../utils/format';
import { RETRY_SET_ID, retryDates, retryItems, retryTopics } from '../practice/review';
import { useIsHidden } from '../practice/useIsHidden';
import { useCurrentUser } from '../auth/session';

const packageTypeLabels: Record<string, string> = {
  review: '예복습',
  preview: '예습',
  bonus: '보너스',
};

/**
 * 학습실 — features/study_room/presentation/study_room_screen.dart
 *
 * 위에서 아래로 한 줄기다: 머리글 · 공부방 안내 · 이번 주 커리큘럼 추천 ·
 * 배정된 인프런 강의(검색 + 패키지 카드). 탭으로 가르지 않는다.
 */
export function StudyRoomScreen() {
  const user = useCurrentUser();
  const packages = useInflearnPackages().filter((p) => p.isPublished);
  const [query, setQuery] = useState('');

  const q = query.trim().toLowerCase();
  const filtered = packages.filter((p) => {
    if (q === '') return true;
    const hay = [
      p.title,
      p.subject,
      p.summary ?? '',
      ...p.units.flatMap((u) => [u.name, ...u.courses.map((c) => c.title)]),
      ...p.courses.map((c) => c.title),
    ];
    return hay.some((t) => t.toLowerCase().includes(q));
  });

  return (
    <div className="screen__inner study-room">
      <header className="study-head">
        <div>
          <h1 className="study-head__title">학습실</h1>
          <p className="study-head__desc">
            배정된 인프런 강의와 이번 주 커리큘럼 YouTube 추천을 확인하세요.
          </p>
        </div>
      </header>

      {/* 공부방 — 수업 저장소에서 복습 노트를 만드는 곳으로 들어가는 문 */}
      <section className="study-entry">
        <div>
          <strong className="study-entry__title">공부방</strong>
          <p className="study-entry__desc">수업 저장소에서 날짜·폴더·파일을 골라 복습 노트를 만듭니다.</p>
        </div>
        <Link className="btn btn--filled btn--md" to={RoutePaths.studyRoomNotes}>
          공부방 열기
        </Link>
      </section>

      {/* 파이썬 연습장 — 문제 없이 코드를 바로 돌려 보는 곳 */}
      <section className="study-entry study-entry--quiet">
        <div>
          <strong className="study-entry__title">파이썬 연습장</strong>
          <p className="study-entry__desc">수업 코드를 옮겨 적고 브라우저에서 바로 실행해 봅니다.</p>
        </div>
        <Link className="btn btn--outline btn--md" to={RoutePaths.studyRoomPlayground}>
          연습장 열기
        </Link>
      </section>

      <PracticeSetsSection cohortId={user.cohortId} uid={user.uid} />

      <YoutubeRecommendations cohortName={user.cohortName} />

      <section className="study-list">
        <h2 className="study-section__title">배정된 인프런 강의</h2>
        <label className="study-search">
          <Icon name="search" size={20} />
          <input
            className="study-search__input"
            value={query}
            placeholder="교과목·강의명 검색"
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>

        {filtered.length === 0 ? (
          <div className="study-empty">
            <Icon name="menu_book" size={48} />
            <p>배정된 인프런 강의가 없습니다</p>
            <span className="hint">강의 배정 후 이곳에 표시됩니다.</span>
          </div>
        ) : (
          filtered.map((pkg) => <PackageCard key={pkg.id} pkg={pkg} />)
        )}
      </section>
    </div>
  );
}

const PRACTICE_KIND_LABEL: Record<string, string> = {
  concept: '개념',
  code_output: '출력 예상',
  code_blank: '빈칸',
  code_fix: '디버깅',
  code_write: '함수 작성',
};

/** 복습 문제 — 수업일마다 만든 세트. 누르면 연습장에서 문제 셀로 열린다. */
function PracticeSetsSection({ cohortId, uid }: { cohortId: string; uid: string }) {
  const sets = usePracticeSets(cohortId);
  const attempts = useMyPracticeAttempts(uid);
  const isHidden = useIsHidden();
  const retries = retryItems(sets, attempts).filter((i) => !isHidden(i.set.id, i.index));
  if (sets.length === 0) return null;
  return (
    <section className="practice-sets">
      <header className="study-section__head">
        <h2 className="study-section__title">복습 문제</h2>
      </header>
      <p className="study-section__desc">그날 수업 코드로 만든 복습 문제입니다. 연습장에서 바로 실행하고 채점해요.</p>
      <div className="practice-sets__list">
        {retries.length > 0 && (
          <Link className="practice-set practice-set--retry" to={`${RoutePaths.studyRoomPlayground}?set=${RETRY_SET_ID}`}>
            <span className="practice-set__date">틀린 문제 모음 · {retryDates(retries)} 수업</span>
            <strong className="practice-set__title">다시 풀 문제 {retries.length}개</strong>
            <span className="practice-set__kinds">{retryTopics(retries, 3)}</span>
            <span className="practice-set__foot">
              다시 풀기
              <Icon name="arrow_forward" size={16} />
            </span>
          </Link>
        )}
        {sets.map((s) => {
          const mine = attempts.filter((a) => a.setId === s.id);
          const passed = mine.filter((a) => a.passed).length;
          const kinds = [...new Set(s.problems.map((p) => PRACTICE_KIND_LABEL[p.kind] ?? p.kind))];
          return (
            <Link key={s.id} className="practice-set" to={`${RoutePaths.studyRoomPlayground}?set=${encodeURIComponent(s.id)}`}>
              <span className="practice-set__date">
                {s.lessonDate.slice(5).replace('-', '/')} · {s.dayLabel}
              </span>
              <strong className="practice-set__title">{s.title}</strong>
              <span className="practice-set__kinds">{kinds.join(' · ')}</span>
              <span className="practice-set__bar" aria-hidden>
                {s.problems.map((_, i) => {
                  const a = mine.find((x) => x.index === i);
                  return <i key={i} className={a?.passed ? 'ok' : a ? 'no' : ''} />;
                })}
              </span>
              <span className="practice-set__foot">
                {passed === s.problems.length ? '모두 통과' : mine.length ? `통과 ${passed} / ${s.problems.length}` : `문제 ${s.problems.length}개`}
                <Icon name="arrow_forward" size={16} />
              </span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

/** 이번 주 커리큘럼 추천 — widgets/youtube_recommendation_section.dart */
function YoutubeRecommendations({ cohortName }: { cohortName: string }) {
  const user = useCurrentUser();
  const videos = useYoutubeRecommendations().filter((v) => v.isPublished);
  const [nonce, setNonce] = useState(0);

  // 내 기술과 겹치는 태그가 많은 것을 앞에 둔다.
  const ranked = videos
    .map((v) => ({
      video: v,
      matched: v.tags.filter((t) => user.skills.some((s) => s.toLowerCase() === t.toLowerCase())),
    }))
    .sort((a, b) => b.matched.length - a.matched.length);

  return (
    <section className="study-youtube" key={nonce}>
      <header className="study-section__head">
        <h2 className="study-section__title">이번 주 커리큘럼 추천</h2>
        <button
          type="button"
          className="icon-btn"
          aria-label="새로고침"
          title="새로고침"
          onClick={() => setNonce((n) => n + 1)}
        >
          <Icon name="refresh" size={20} />
        </button>
      </header>
      <p className="study-section__desc">
        「{cohortName} 커리큘럼」 기준으로 이번 주 주제 영상을 추천합니다.
      </p>

      {ranked.length === 0 ? (
        <div className="study-card study-card--empty">
          이번 주 추천 영상이 준비되면 여기에 표시됩니다.
        </div>
      ) : (
        <div className="study-videos">
          {ranked.map(({ video, matched }) => (
            <a
              key={video.id}
              className="study-video"
              href={video.youtubeUrl}
              target="_blank"
              rel="noreferrer"
            >
              <span className="study-video__thumb">
                <Icon name="play_circle" size={30} />
              </span>
              <strong className="study-video__title">{video.title}</strong>
              <span className="study-video__tags">
                {video.tags.map((tag) => (
                  <span key={tag} className={`chip${matched.includes(tag) ? ' chip--on' : ''}`}>
                    {tag}
                  </span>
                ))}
              </span>
              {matched.length > 0 && (
                <span className="hint">내 스택과 {matched.length}개 일치</span>
              )}
            </a>
          ))}
        </div>
      )}
    </section>
  );
}

/** 인프런 패키지 카드 — widgets/inflearn_package_card.dart */
function PackageCard({ pkg }: { pkg: InflearnPackage }) {
  const courseCount =
    pkg.courses.length + pkg.units.reduce((sum, u) => sum + u.courses.length, 0);

  return (
    <article className="pkg-card">
      <div className="pkg-card__badges">
        <span className={`pkg-badge pkg-badge--${pkg.type}`}>
          {packageTypeLabels[pkg.type] ?? pkg.type}
        </span>
        <span className="pkg-badge pkg-badge--subject">{pkg.subject}</span>
        {pkg.publishedAt !== undefined && (
          <span className="hint">배정일 {formatDate(pkg.publishedAt)}</span>
        )}
      </div>

      <h3 className="pkg-card__title">{pkg.title}</h3>
      <p className="pkg-card__count">총 {courseCount}개 강의</p>
      {pkg.summary !== undefined && <p className="pkg-card__summary">{pkg.summary}</p>}

      {pkg.units.length > 0
        ? pkg.units.map((unit) => (
            <UnitSection key={unit.name} name={unit.name} courses={unit.courses} />
          ))
        : pkg.courses.map((course) => (
            <CourseRow key={course.title} title={course.title} url={course.url} />
          ))}
    </article>
  );
}

/** 교과목 한 묶음 — 접힌 채로 시작한다(ExpansionTile). */
function UnitSection({
  name,
  courses,
}: {
  name: string;
  courses: { title: string; url: string }[];
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="unit">
      <button type="button" className="unit__head" onClick={() => setOpen((v) => !v)}>
        <span className="unit__text">
          <strong>{name}</strong>
          <span className="hint">{courses.length}개 강의</span>
        </span>
        <Icon name={open ? 'expand_less' : 'expand_more'} size={20} />
      </button>
      {open && (
        <div className="unit__body">
          {courses.map((course) => (
            <CourseRow key={course.title} title={course.title} url={course.url} />
          ))}
        </div>
      )}
    </div>
  );
}

function CourseRow({ title, url }: { title: string; url: string }) {
  return (
    <a className="course-row" href={url} target="_blank" rel="noreferrer">
      <Icon name="play_circle" size={18} />
      <span>{title}</span>
      <Icon name="open_in_new" size={15} className="course-row__go" />
    </a>
  );
}

/** 학습 노트 목록 — study_room_notes_screen.dart */
export function StudyNotesScreen() {
  const sources = useStudySources();
  const notes = useStudyNotes();

  return (
    <div className="screen__inner">
      <PageHeader title="학습 노트" description="강의 저장소에서 만들어진 요약·복습 노트입니다." />
      {sources.map((source) => (
        <Card key={source.id} title={source.title}>
          <Row gap={6}>
            <a className="link" href={source.repoUrl} target="_blank" rel="noreferrer">
              {source.repoUrl}
            </a>
            <Badge tone="neutral">{source.branch}</Badge>
            <Spacer />
            <Link className="btn btn--filled btn--sm" to={studyRoomNoteSourcePath(source.id)}>
              새 수업노트 만들기
            </Link>
          </Row>
          <div className="study-note-chips">
            {notes.filter((n) => n.sourceId === source.id).map((note) => (
              <Link
                key={note.id}
                className="chip"
                to={`${studyRoomNoteSourcePath(source.id)}?note=${encodeURIComponent(note.id)}`}
              >
                <Icon name="description" size={16} />
                {note.scopeKey ?? note.id}
              </Link>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

/** 노트 상세 — study_room_note_source_screen.dart */
export function StudyNoteSourceScreen() {
  const { sourceId } = useParams<{ sourceId: string }>();
  const sources = useStudySources();
  const notes = useStudyNotes().filter((n) => n.sourceId === sourceId);
  const source = sources.find((s) => s.id === sourceId);
  const initialNoteId = new URLSearchParams(window.location.search).get('note');
  const [selectedId, setSelectedId] = useState<string | null>(initialNoteId);
  const [tab, setTab] = useState('report');
  const [scopeMode, setScopeMode] = useState<'date' | 'folder' | 'file'>('date');
  const [scopeValue, setScopeValue] = useState('');
  const [checkedFiles, setCheckedFiles] = useState<string[]>([]);
  const [error, setError] = useState('');

  const note = notes.find((item) => item.id === selectedId);
  const files = Array.from(new Set(notes.flatMap((item) => item.files.map((file) => file.path))));
  const dateChoices = ['2026-09-17', '2026-09-18', '2026-09-19'];
  const folderChoices = source?.allowedPrefixes ?? [];

  const generate = () => {
    const selectedFiles = scopeMode === 'file' ? checkedFiles : files.filter((path) =>
      scopeMode === 'folder' ? path.startsWith(scopeValue) : true,
    );
    if ((scopeMode === 'file' && checkedFiles.length === 0) || (scopeMode !== 'file' && scopeValue === '')) {
      setError(scopeMode === 'file' ? '파일을 1개 이상 선택하세요.' : '정리할 범위를 선택하세요.');
      return;
    }
    const scopeKey = scopeMode === 'date'
      ? `date:${scopeValue}`
      : scopeMode === 'folder'
        ? `folder:${scopeValue}`
        : `files:${checkedFiles.length}개`;
    const id = createDemoStudyNote(
      sourceId ?? '',
      scopeKey,
      selectedFiles.slice(0, 8).map((path) => ({ path, commit: 'demo-local' })),
    );
    setSelectedId(id);
    setTab('report');
    setError('');
  };

  return (
    <div className="screen__inner">
      <PageHeader
        title={source?.title ?? '학습 노트'}
        description="날짜·폴더·파일 중 필요한 범위만 골라 복습 노트를 만듭니다."
        actions={<Link className="btn btn--outline btn--sm" to={RoutePaths.studyRoomNotes}>공부방 목록</Link>}
      />
      <div className="split">
          <Card padded={false} className="split__side">
            <ul className="list" style={{ padding: '0 12px' }}>
              <li className="list__item">
                <button
                  type="button"
                  className={`plain-btn${selectedId === null ? ' plain-btn--on' : ''}`}
                  onClick={() => setSelectedId(null)}
                >
                  + 새 수업노트
                </button>
              </li>
              {notes.map((n) => (
                <li key={n.id} className="list__item">
                  <button
                    type="button"
                    className={`plain-btn${n.id === selectedId ? ' plain-btn--on' : ''}`}
                    onClick={() => setSelectedId(n.id)}
                  >
                    {n.scopeKey ?? n.id}
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          {note === undefined ? (
            <Card className="split__main" title="새 수업노트 만들기">
              <p className="muted">정리할 범위를 하나만 고르면 됩니다.</p>
              <Tabs
                items={[
                  { id: 'date', label: '날짜' },
                  { id: 'folder', label: '폴더' },
                  { id: 'file', label: '파일' },
                ]}
                active={scopeMode}
                onChange={(id) => {
                  setScopeMode(id as 'date' | 'folder' | 'file');
                  setScopeValue('');
                  setError('');
                }}
              />
              <div className="study-scope-options">
                {scopeMode === 'date' && dateChoices.map((date) => (
                  <button key={date} type="button" className={`chip${scopeValue === date ? ' chip--on' : ''}`} onClick={() => setScopeValue(date)}>{date}</button>
                ))}
                {scopeMode === 'folder' && folderChoices.map((folder) => (
                  <button key={folder} type="button" className={`chip${scopeValue === folder ? ' chip--on' : ''}`} onClick={() => setScopeValue(folder)}>{folder}</button>
                ))}
                {scopeMode === 'file' && files.map((path) => (
                  <Checkbox
                    key={path}
                    checked={checkedFiles.includes(path)}
                    onChange={(checked) => setCheckedFiles((current) =>
                      checked ? [...current, path].slice(0, 8) : current.filter((item) => item !== path),
                    )}
                    label={path}
                  />
                ))}
              </div>
              {scopeMode === 'file' && <span className="hint">{checkedFiles.length}/8개 선택</span>}
              {error !== '' && <div className="callout callout--error">{error}</div>}
              <div className="callout">현재는 화면 확인용 로컬 생성입니다. 실제 저장소 분석은 Django·공부방 API 연결 후 동작합니다.</div>
              <Row><Spacer /><Button onClick={generate}>선택한 범위 정리하기</Button></Row>
            </Card>
          ) : (
          <Card className="split__main">
            <Tabs
              items={[
                { id: 'report', label: '요약' },
                { id: 'review', label: '복습' },
                { id: 'files', label: '파일', count: note.files.length },
              ]}
              active={tab}
              onChange={setTab}
            />
            {tab === 'report' && <Markdown text={note.reportMarkdown} />}
            {tab === 'review' && <Markdown text={note.reviewMarkdown} />}
            {tab === 'files' && (
              <ul className="list">
                {note.files.map((f) => (
                  <li key={f.path} className="list__item">
                    <code>{f.path}</code>
                    <Spacer />
                    <span className="hint">{f.commit.slice(0, 7)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          )}
        </div>
    </div>
  );
}

/** 아주 작은 마크다운 표시기 — 제목·목록·문단만 다룬다. */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown">
      {text.split('\n').map((line, i) => {
        if (line.startsWith('## ')) return <h3 key={i}>{line.slice(3)}</h3>;
        if (line.startsWith('# ')) return <h2 key={i}>{line.slice(2)}</h2>;
        if (line.startsWith('- ')) return <li key={i}>{line.slice(2)}</li>;
        if (/^\d+\.\s/.test(line)) return <li key={i}>{line.replace(/^\d+\.\s/, '')}</li>;
        if (line.trim() === '') return null;
        return <p key={i}>{line}</p>;
      })}
    </div>
  );
}
