import { useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import { homeFor } from '../../app/routePaths';
import { updateUser, useMyResumes } from '../../data/repository';
import { JobPreferencePresets } from '../../domain/constants';
import type { ProfileTechItem, Resume, ResumeTechStackItem, User } from '../../domain/types';
import { tourFor } from '../../tour/tours';
import { useTour } from '../../tour/useTour';
import { Icon } from '../../ui/Icon';
import { PageHeader } from '../../ui/components';
import { formatDateTime } from '../../utils/format';
import { useCurrentUser, useSession } from '../auth/session';
import { TechStackEditor } from '../resume/skills/TechStackEditor';
import { sameSkill } from '../resume/skills/skillCatalog';
import { PreferenceTagEditor } from './PreferenceTagEditor';

/**
 * 마이페이지 — features/my_page/presentation/my_page_screen.dart
 *
 * 가운데 좁은 줄기(560px)에 카드 다섯이 쌓인다: 프로필 요약, 개인 정보, 기술 스택, 취업 희망
 * 조건, 비밀번호. 항목은 표가 아니라 「라벨·값·연필」 한 줄이고, 연필을 누르면
 * 그 자리에서 고친다.
 */
export function MyPageScreen() {
  const user = useCurrentUser();
  const tour = useTour();
  const navigate = useNavigate();

  return (
    <div className="mypage">
      <div className="mypage__column">
        <PageHeader title="마이페이지" description="프로필 · 연락처 · 기술 스택 · 취업 희망 조건 · 비밀번호를 관리합니다." />

        <ProfileOverviewCard user={user} />
        <PersonalInfoCard user={user} />
        <TechStackCard user={user} />
        <JobPreferencesCard user={user} />
        <PasswordCard />

        <div className="mypage__links">
          <button
            type="button"
            className="btn btn--text btn--sm"
            onClick={() => {
              tour.restart(tourFor(user.role), user.uid);
              navigate(homeFor(user.role));
            }}
          >
            <Icon name="tour" size={18} />
            이용 안내 다시보기
          </button>
          <a className="btn btn--text btn--sm" href={manualUrl(user.role)} target="_blank" rel="noreferrer">
            <Icon name="picture_as_pdf" size={18} />
            PDF 매뉴얼 보기
          </a>
        </div>
      </div>
    </div>
  );
}

/**
 * 역할별 사용 설명서 — Flutter 판 my_page_screen.dart 와 같은 파일.
 * public/manuals/ 의 PDF 는 tools/guide/ 가 데모 빌드 화면을 찍어 만든다(tools/guide/README.md).
 */
function manualUrl(role: string): string {
  const file = role === 'admin' ? 'admin_manual.pdf' : role === 'instructor' ? 'instructor_manual.pdf' : 'student_manual.pdf';
  return `/manuals/${file}`;
}

/** 「SK네트웍스 Family AI 캠프 34기」를 과정 이름과 기수로 나눈다. */
function splitCohort(name: string): { course: string; term: string } {
  const match = /^(.*)\s+(\d+기)$/.exec(name.trim());
  return match === null
    ? { course: name, term: '-' }
    : { course: match[1].trim(), term: match[2] };
}

function ProfileOverviewCard({ user }: { user: User }) {
  const { course, term } = splitCohort(user.cohortName);
  const rows: [string, string][] = [
    ['교육과정', course],
    ['기수', term],
    ['계정 생성일', user.createdAt === undefined ? '-' : formatDateTime(user.createdAt)],
    ['마지막 로그인', user.lastLoginAt === undefined ? '-' : formatDateTime(user.lastLoginAt)],
  ];

  return (
    <section className="panel mycard">
      <div className="mycard__who">
        <span className="mycard__avatar">
          <Icon name="person" size={30} />
          <i className="mycard__camera">
            <Icon name="photo_camera" size={12} />
          </i>
        </span>
        <span className="mycard__name">
          <strong>{user.displayName}님</strong>
          <span className="hint">{user.cohortName}</span>
        </span>
      </div>

      <dl className="mycard__info">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function PersonalInfoCard({ user }: { user: User }) {
  const hasPersonalEmail = user.personalEmail !== undefined && user.personalEmail !== '';

  return (
    <section className="panel mycard">
      <h2 className="mycard__title">개인 정보</h2>

      {!hasPersonalEmail && (
        <p className="mycard__warn">
          개인 이메일이 등록되지 않았습니다. 구글폼 제출 연동을 위해 등록해 주세요.
        </p>
      )}

      <EditableRow
        icon="mail"
        label="개인 이메일 (구글폼)"
        value={user.personalEmail}
        empty="등록된 이메일 없음"
        onSave={(v) => updateUser(user.uid, { personalEmail: v })}
      />

      <hr className="mycard__rule" />

      <label className="mycard__field">
        <span className="mycard__field-label">생년월일</span>
        <span className="mycard__date">
          <Icon name="calendar_today" size={16} />
          <input
            type="date"
            value={user.birthDate ?? ''}
            onChange={(e) => updateUser(user.uid, { birthDate: e.target.value })}
          />
        </span>
      </label>

      <hr className="mycard__rule" />

      <EditableRow
        icon="code"
        label="GitHub"
        value={user.socialLinks.github}
        onSave={(v) => updateUser(user.uid, { socialLinks: { ...user.socialLinks, github: v } })}
      />

      <hr className="mycard__rule" />

      <EditableRow
        icon="article"
        label="블로그"
        value={user.socialLinks.blog}
        onSave={(v) => updateUser(user.uid, { socialLinks: { ...user.socialLinks, blog: v } })}
      />
    </section>
  );
}

/** 라벨·값·연필 한 줄. 연필을 누르면 그 자리가 입력칸이 된다. */
function EditableRow({
  icon,
  label,
  value,
  empty = '등록된 링크 없음',
  onSave,
}: {
  icon: string;
  label: string;
  value?: string;
  empty?: string;
  onSave(next: string): void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? '');
  const filled = value !== undefined && value !== '';

  return (
    <div className="mylink">
      <Icon name={icon} size={18} className="mylink__icon" />
      <span className="mylink__body">
        <strong>{label}</strong>
        {editing ? (
          <span className="mylink__edit">
            <input
              className="input"
              value={draft}
              autoFocus
              onChange={(e) => setDraft(e.target.value)}
            />
            <button
              type="button"
              className="btn btn--filled btn--sm"
              onClick={() => {
                onSave(draft.trim());
                setEditing(false);
              }}
            >
              저장
            </button>
            <button
              type="button"
              className="btn btn--text btn--sm"
              onClick={() => {
                setDraft(value ?? '');
                setEditing(false);
              }}
            >
              취소
            </button>
          </span>
        ) : filled ? (
          <span className="mylink__value">{value}</span>
        ) : (
          <span className="mylink__empty">{empty}</span>
        )}
      </span>
      {!editing && (
        <button
          type="button"
          className="icon-btn"
          aria-label="수정"
          title="수정"
          onClick={() => {
            setDraft(value ?? '');
            setEditing(true);
          }}
        >
          <Icon name="edit" size={18} />
        </button>
      )}
    </div>
  );
}

/**
 * 기술 스택 — 학생이 기술을 적는 원본. 이력서 기술스택은 「마이페이지에서 불러오기」로 여기서 가져간다
 * (이력서마다 하나씩 다시 적지 않게). 편집기는 이력서와 같은 것을 쓴다.
 * 이미 이력서에 적어 둔 학생은 「이력서에서 가져오기」로 한 번에 옮긴다.
 */
function TechStackCard({ user }: { user: User }) {
  const resumes = useMyResumes(user.uid).data ?? [];
  // 편집기는 id 로 고른 칸을 기억한다. 서버에서 다시 받아 id 가 바뀌지 않게 이 화면에서 들고 있는다
  const [items, setItems] = useState<ResumeTechStackItem[]>(() =>
    (user.techStack ?? user.skills.map((name) => ({ name, level: '' }))).map((t) => ({ id: techId(), ...t })),
  );
  const save = (next: ResumeTechStackItem[]) => {
    setItems(next);
    const techStack: ProfileTechItem[] = next.filter((t) => t.name.trim() !== '').map(({ name, level }) => ({ name, level }));
    updateUser(user.uid, { techStack, skills: techStack.map((t) => t.name) });
  };

  const source = resumeWithTech(resumes);
  const fresh = (source?.content.techStack ?? []).filter(
    (t) => t.name.trim() !== '' && !items.some((mine) => sameSkill(mine.name, t.name)),
  );

  return (
    <section className="panel mycard">
      <header className="mycard__head">
        <h2 className="mycard__title">기술 스택</h2>
        <span className="spacer" />
        {fresh.length > 0 && (
          <button
            type="button"
            className="btn btn--text btn--sm"
            title={`「${source?.title}」의 기술스택 중 여기 없는 ${fresh.length}개를 숙련도와 함께 가져옵니다`}
            onClick={() => save([...items, ...fresh.map((t) => ({ id: techId(), name: t.name, level: t.level }))])}
          >
            <Icon name="download" size={18} />
            이력서에서 가져오기 ({fresh.length})
          </button>
        )}
      </header>
      <p className="mycard__sub">
        여기 적어 두면 이력서 기술스택에서 「마이페이지에서 불러오기」로 한 번에 넣을 수 있어요.
      </p>
      <TechStackEditor items={items} readOnly={false} onChange={save} newId={techId} />
    </section>
  );
}

const techId = () => `pt${Date.now()}${Math.random().toString(36).slice(2, 6)}`;

/** 가져올 이력서 — 원본(기본) 이력서 중 가장 최근에 고친 것, 없으면 아무 이력서 중 가장 최근. 기술스택이 있는 것만 */
function resumeWithTech(resumes: Resume[]): Resume | undefined {
  const withTech = resumes.filter((r) => r.content.techStack.some((t) => t.name.trim() !== ''));
  const latest = (list: Resume[]) =>
    [...list].sort((a, b) => (b.updatedAt?.getTime() ?? 0) - (a.updatedAt?.getTime() ?? 0))[0];
  return latest(withTech.filter((r) => r.isBaseResume)) ?? latest(withTech);
}

function JobPreferencesCard({ user }: { user: User }) {
  const [editing, setEditing] = useState(false);
  const p = user.jobPreferences;

  const rows: [string, keyof typeof p, string[]][] = [
    ['희망 직무', 'targetRoles', p.targetRoles],
    ['희망 근무지역', 'regions', p.regions],
    ['희망 고용형태', 'employmentTypes', p.employmentTypes],
  ];

  return (
    <section className="panel mycard">
      <header className="mycard__head">
        <h2 className="mycard__title">취업 희망 조건</h2>
        <span className="spacer" />
        <button
          type="button"
          className="icon-btn"
          aria-label="수정"
          onClick={() => setEditing((v) => !v)}
        >
          <Icon name={editing ? 'close' : 'edit'} size={18} />
        </button>
      </header>
      <p className="mycard__sub">
        이력서에는 표시되지 않고 커리어 코치의 맞춤 공고 추천에만 쓰입니다.
      </p>

      {rows.map(([label, key, values]) => (
        <div key={label} className="mypref">
          <strong className="mypref__label">{label}</strong>
          {editing ? (
            <PreferenceTagEditor
              values={values}
              presets={JobPreferencePresets[key]}
              placeholder={`${label.replace('희망 ', '')} 직접 입력 후 Enter`}
              onChange={(next) => updateUser(user.uid, { jobPreferences: { ...p, [key]: next } })}
            />
          ) : values.length === 0 ? (
            <span className="mylink__empty">미입력</span>
          ) : (
            <span className="mypref__chips">
              {values.map((v) => (
                <span key={v} className="chip">
                  {v}
                </span>
              ))}
            </span>
          )}
        </div>
      ))}
    </section>
  );
}

function PasswordCard(): ReactNode {
  const { changePassword } = useSession();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [saving, setSaving] = useState(false);

  const submit = () => {
    setDone(false);
    if (next.length < 8) {
      setError('비밀번호는 8자 이상이어야 합니다.');
      return;
    }
    if (next !== confirm) {
      setError('두 번 입력한 비밀번호가 다릅니다.');
      return;
    }
    setSaving(true);
    void changePassword(next, current).then((result) => {
      setSaving(false);
      if (!result.ok) {
        setError(result.message);
        return;
      }
      setError(null);
      setCurrent('');
      setNext('');
      setConfirm('');
      setDone(true);
    });
  };

  return (
    <section className="panel mycard">
      <button type="button" className="mycard__toggle" onClick={() => setOpen((v) => !v)}>
        <h2 className="mycard__title">비밀번호 변경</h2>
        <span className="spacer" />
        <Icon name={open ? 'expand_less' : 'expand_more'} size={20} />
      </button>

      {open && (
        <>
          <p className="mycard__sub">현재 비밀번호를 확인한 뒤 새 비밀번호로 바꿉니다.</p>
          <label className="mycard__field">
            <span className="mycard__field-label">현재 비밀번호</span>
            <input
              className="input"
              type="password"
              value={current}
              onChange={(e) => {
                setCurrent(e.target.value);
                setError(null);
                setDone(false);
              }}
            />
          </label>
          <label className="mycard__field">
            <span className="mycard__field-label">새 비밀번호</span>
            <input
              className="input"
              type="password"
              value={next}
              onChange={(e) => {
                setNext(e.target.value);
                setError(null);
                setDone(false);
              }}
            />
          </label>
          <label className="mycard__field">
            <span className="mycard__field-label">새 비밀번호 확인</span>
            <input
              className="input"
              type="password"
              value={confirm}
              onChange={(e) => {
                setConfirm(e.target.value);
                setError(null);
                setDone(false);
              }}
            />
          </label>
          {error !== null && <p className="mycard__sub">{error}</p>}
          {done && <p className="mycard__sub">비밀번호를 바꿨습니다. 다음 로그인부터 새 비밀번호를 쓰세요.</p>}
          <div className="mycard__actions">
            <button type="button" className="btn btn--outline btn--md" onClick={submit} disabled={saving}>
              {saving ? '변경 중' : '변경'}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
