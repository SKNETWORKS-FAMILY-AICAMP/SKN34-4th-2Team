import { useEffect, useState } from 'react';

import { nextId } from '../../data/store';
import { Icon } from '../../ui/Icon';
import { Button, Checkbox, Chip } from '../../ui/components';
import type { CompanyQuestion } from './companyQuestions';
import {
  REPORT_REASONS,
  roleKey,
  sharedQuestionsApi,
  similarRoles,
  toCompanyQuestions,
  type ReportReason,
  type SharedQuestions as Shared,
  type SharedRole,
  type SharedSet,
} from './sharedQuestionsApi';

/**
 * 「자소서 문항」 단계 맨 위 — 지원 직무를 고르고, 같은 회사 · 시즌 · 직무에 다른 수강생이 정리한 문항을 가져온다.
 *
 * 직무는 칩(이미 정리된 직무)에서 고르거나 직접 입력한다. 입력하면 비슷한 기존 직무를 먼저 보여 줘 이름이 갈라지지 않게 한다.
 * 공통 문항(회사가 직무와 상관없이 같은 문항을 낼 때)은 어느 직무를 골라도 함께 보인다.
 */
export function SharedQuestions({
  jobId,
  role,
  onRole,
  common,
  onCommon,
  guess,
  onPick,
}: {
  jobId: string;
  /** 지원 직무 — 확정할 때 이 이름으로 남긴다 */
  role: string;
  onRole(name: string): void;
  /** 「모든 직무 공통 문항」으로 남길지 */
  common: boolean;
  onCommon(next: boolean): void;
  /** 공고 제목에서 짐작한 직무 — 아직 아무도 정리하지 않았을 때 채워 둔다 */
  guess: string;
  onPick(questions: CompanyQuestion[], setId: string): void;
}) {
  const [data, setData] = useState<Shared | null>(null);
  const [failed, setFailed] = useState(false);
  const [typing, setTyping] = useState(false);

  useEffect(() => {
    let alive = true;
    setData(null);
    setFailed(false);
    sharedQuestionsApi
      .list(jobId)
      .then((d) => {
        if (!alive) return;
        setData(d);
        // 처음 열 때 — 정리된 직무가 있으면 가장 많이 쓴 것, 없으면 제목에서 짐작한 것
        if (role === '') onRole(d.roles[0]?.name ?? guess);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
    // 공고가 바뀔 때만 다시 읽는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  if (failed) return null; // 공유를 못 읽어도 직접 정하기는 그대로 쓴다
  if (data === null) return <p className="hint">다른 수강생이 정리한 문항을 찾는 중…</p>;

  const picked = data.roles.find((r) => r.key === roleKey(role)) ?? null;
  // 입력하는 동안 — 이름이 조금이라도 다르면 비슷한 기존 직무를 먼저 보여 준다(같은 열쇠로 접히는 이름도)
  const suggestions = typing ? similarRoles(role, data.roles).filter((r) => r.name !== role.trim()) : [];
  const hide = (setId: string) =>
    setData((d) =>
      d === null
        ? d
        : {
            ...d,
            roles: d.roles.map((r) => ({ ...r, sets: r.sets.filter((s) => s.id !== setId) })).filter((r) => r.sets.length > 0),
            common: d.common.filter((s) => s.id !== setId),
          },
    );

  return (
    <div className="apply-shared">
      <div className="apply-shared__roles">
        <span className="apply-label">
          지원 직무{data.roles.length > 0 && ' · 이 회사 · 시즌에 다른 수강생이 정리한 직무예요'}
        </span>
        {data.roles.length > 0 && (
          <div className="apply-shared__chips">
            {data.roles.map((r) => (
              <Chip
                key={r.key}
                selected={picked?.key === r.key && !typing}
                onClick={() => {
                  setTyping(false);
                  onRole(r.name);
                }}
              >
                {r.name} · {r.sets.length}
              </Chip>
            ))}
            <Chip selected={typing} onClick={() => setTyping(true)}>
              + 직접 입력
            </Chip>
          </div>
        )}
        {(typing || data.roles.length === 0) && (
          <input
            className="apply-q-input apply-shared__role-input"
            value={role}
            onChange={(e) => {
              setTyping(true);
              onRole(e.target.value);
            }}
            placeholder="예: SW 개발"
            aria-label="지원 직무"
          />
        )}
        {data.roles.length === 0 && guess !== '' && role === guess && (
          <span className="hint">공고 제목에서 가져왔어요 · 다르면 고쳐 주세요</span>
        )}
        {suggestions.length > 0 && (
          <div className="apply-shared__suggest">
            <span className="hint">혹시 이 직무인가요? 같은 직무면 골라 주세요 — 문항이 한곳에 모여요</span>
            {suggestions.map((r) => (
              <button
                key={r.key}
                type="button"
                className="apply-shared__suggest-item"
                onClick={() => {
                  setTyping(false);
                  onRole(r.name);
                }}
              >
                <b>{r.name}</b>
                <span>{r.people}명 정리 · 이걸로</span>
              </button>
            ))}
            <span className="hint">아니면 「{role}」로 새로 만들어요</span>
          </div>
        )}
        <Checkbox checked={common} onChange={onCommon} label="모든 직무 공통 문항이에요 (회사가 직무와 상관없이 같은 문항을 낼 때)" />
      </div>

      {data.roles.length === 0 && data.common.length === 0 && (
        <p className="apply-shared__empty">
          아직 {data.company} {data.season} 문항을 정리한 수강생이 없어요. 처음 정리하면 같은 회사 · 시즌 공고를 고른 다른 수강생에게도
          보여요.
        </p>
      )}

      {picked !== null && !typing && (
        <RoleSets role={picked} canReport={data.canReport} onPick={onPick} onHidden={hide} />
      )}

      {data.common.map((set) => (
        <SetCard key={set.id} set={set} title={`모든 직무 공통 문항`} tone="common" canReport={data.canReport} onPick={onPick} onHidden={hide} />
      ))}
    </div>
  );
}

function RoleSets({
  role,
  canReport,
  onPick,
  onHidden,
}: {
  role: SharedRole;
  canReport: boolean;
  onPick(questions: CompanyQuestion[], setId: string): void;
  onHidden(setId: string): void;
}) {
  const [open, setOpen] = useState(false);
  const [top, ...others] = role.sets;
  const base = new Set(top.questions.map((q) => questionKey(q.question)));
  return (
    <>
      <SetCard set={top} title={`다른 수강생이 정리한 문항 · ${role.name}`} canReport={canReport} onPick={onPick} onHidden={onHidden} />
      {others.length > 0 && (
        <div>
          <Button variant="text" size="sm" onClick={() => setOpen((o) => !o)}>
            <Icon name={open ? 'expand_less' : 'expand_more'} size={16} />
            {open ? '다른 정리 접기' : `다른 정리 ${others.length}개 보기`}
          </Button>
        </div>
      )}
      {open &&
        others.map((set) => (
          <SetCard key={set.id} set={set} title="다른 정리" diff={base} canReport={canReport} onPick={onPick} onHidden={onHidden} />
        ))}
    </>
  );
}

function SetCard({
  set,
  title,
  tone = 'role',
  diff,
  canReport,
  onPick,
  onHidden,
}: {
  set: SharedSet;
  title: string;
  tone?: 'role' | 'common';
  /** 맨 위 정리의 문항 — 이 정리에만 있는 문항을 칠한다 */
  diff?: Set<string>;
  canReport: boolean;
  onPick(questions: CompanyQuestion[], setId: string): void;
  onHidden(setId: string): void;
}) {
  const [reporting, setReporting] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const report = async (reason: ReportReason) => {
    setReporting(false);
    try {
      const { hidden } = await sharedQuestionsApi.report(set.id, reason);
      if (hidden) onHidden(set.id);
      else setNote('알려 줘서 고마워요. 2명이 알려 주면 이 정리는 숨겨져요.');
    } catch {
      setNote('지금은 알릴 수 없어요. 잠시 후 다시 시도해 주세요.');
    }
  };
  const date = new Date(set.updatedAt);
  return (
    <section className={`apply-shared__card apply-shared__card--${tone}`} aria-label={title}>
      <header className="apply-shared__head">
        <strong>{title}</strong>
        <span className="hint">
          {set.useCount}명 사용 · {date.getMonth() + 1}/{date.getDate()} 정리
          {set.mine && ' · 내가 정리'}
          {!set.shared && ' · 나만 보기'}
          {set.roleNames.length > 1 && ` · ${set.roleNames.join(' · ')}`}
        </span>
      </header>
      <ol className="apply-q-list">
        {set.questions.map((q, i) => (
          <li key={i} className={diff !== undefined && !diff.has(questionKey(q.question)) ? 'is-diff' : undefined}>
            <span>{q.question}</span>
            <span className="apply-q-limit">{q.limit === null ? '글자 수 없음' : `${q.limit.toLocaleString()}자`}</span>
          </li>
        ))}
      </ol>
      <div className="apply-shared__actions">
        <Button
          onClick={() => {
            void sharedQuestionsApi.use(set.id).catch(() => undefined);
            onPick(toCompanyQuestions(set, () => nextId('cq')), set.id);
          }}
        >
          <Icon name="check" size={18} />이 문항으로 쓰기
        </Button>
        {canReport && !set.mine && (
          <Button variant="text" size="sm" onClick={() => setReporting((r) => !r)}>
            이상해요
          </Button>
        )}
      </div>
      {reporting && (
        <div className="apply-shared__chips" role="group" aria-label="이상한 이유">
          {REPORT_REASONS.map((r) => (
            <Chip key={r.id} onClick={() => void report(r.id)}>
              {r.label}
            </Chip>
          ))}
        </div>
      )}
      {note !== null && <p className="hint">{note}</p>}
    </section>
  );
}

/** 번호 · 글자 수 표기 · 띄어쓰기만 다른 문항은 같은 문항 */
function questionKey(text: string): string {
  return text
    .normalize('NFKC')
    .replace(/^\s*(\d{1,2}\s*[.)-]|[①-⑳]|Q\s*\d{1,2}\s*[.)]?)\s*/, '')
    .replace(/[[(][^\])]*\d[\d,]*\s*자[^\])]*[\])]/g, '')
    .replace(/[^\p{L}\p{N}]+/gu, '')
    .toLowerCase();
}
