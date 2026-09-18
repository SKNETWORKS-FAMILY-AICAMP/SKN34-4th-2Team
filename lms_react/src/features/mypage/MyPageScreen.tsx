import { useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import { homeFor } from '../../app/routePaths';
import { updateUser } from '../../data/repository';
import type { User } from '../../domain/types';
import { tourFor } from '../../tour/tours';
import { useTour } from '../../tour/useTour';
import { Icon } from '../../ui/Icon';
import { formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';

/**
 * 마이페이지 — features/my_page/presentation/my_page_screen.dart
 *
 * 가운데 좁은 줄기(560px)에 카드 넷이 쌓인다: 프로필 요약, 개인 정보, 취업 희망
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
        <header className="mypage__head">
          <button
            type="button"
            className="icon-btn"
            aria-label="뒤로"
            onClick={() => navigate(homeFor(user.role))}
          >
            <Icon name="arrow_back" size={22} />
          </button>
          <h1>마이페이지</h1>
        </header>

        <ProfileOverviewCard user={user} />
        <PersonalInfoCard user={user} />
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
          <button type="button" className="btn btn--text btn--sm">
            <Icon name="picture_as_pdf" size={18} />
            PDF 매뉴얼 보기
          </button>
        </div>
      </div>
    </div>
  );
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
            <input
              className="input"
              defaultValue={values.join(', ')}
              placeholder="쉼표로 구분합니다"
              onBlur={(e) =>
                updateUser(user.uid, {
                  jobPreferences: {
                    ...p,
                    [key]: e.target.value
                      .split(',')
                      .map((v) => v.trim())
                      .filter((v) => v !== ''),
                  },
                })
              }
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
  const [open, setOpen] = useState(false);

  return (
    <section className="panel mycard">
      <button type="button" className="mycard__toggle" onClick={() => setOpen((v) => !v)}>
        <h2 className="mycard__title">비밀번호 변경</h2>
        <span className="spacer" />
        <Icon name={open ? 'expand_less' : 'expand_more'} size={20} />
      </button>

      {open && (
        <>
          <p className="mycard__sub">
            프로토타입에서는 비밀번호가 바뀌지 않습니다. 화면만 확인할 수 있습니다.
          </p>
          <label className="mycard__field">
            <span className="mycard__field-label">현재 비밀번호</span>
            <input className="input" type="password" />
          </label>
          <label className="mycard__field">
            <span className="mycard__field-label">새 비밀번호</span>
            <input className="input" type="password" />
          </label>
          <div className="mycard__actions">
            <button type="button" className="btn btn--outline btn--md">
              변경
            </button>
          </div>
        </>
      )}
    </section>
  );
}
