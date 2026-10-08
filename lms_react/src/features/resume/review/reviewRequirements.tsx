import { useState } from 'react';

import { Icon } from '../../../ui/Icon';

/**
 * 공고 요건 대조 · STAR 판정 · 단계 표시 — ai_coach/presentation/review_requirements.dart
 */

/** 공고 맞춤 첨삭의 대화 단계. 서버(review_workflow._review_stage)와 번호를 맞춘다. */
export const REVIEW_STAGE_LABELS = ['문장 다듬기', '공고 요건 확인', '경험 보완', '지원동기', '자기소개서'];

/** 공고 요건 확인 단계 번호. 공고 없는 첨삭이면 단계 줄에서 뺀다. */
const REQUIREMENT_STAGE = 2;

export function reviewStageLabel(stage: number | null | undefined): string {
  return stage != null && stage >= 1 && stage <= REVIEW_STAGE_LABELS.length ? REVIEW_STAGE_LABELS[stage - 1] : '';
}

/** 서버 응답 `requirement_map`의 한 줄. 점수가 아니라 근거가 있는지만 담는다. */
export interface RequirementRow {
  id: string;
  /** must(필수) · preferred(우대) · task(주요 업무) */
  group: string;
  label: string;
  /** met(근거 있음) · partial(일부) · unconfirmed(확인 필요) · absent(해당 없음) */
  status: string;
  postingQuote: string;
  evidencePaths: string[];
  evidenceQuotes: string[];
  source: string;
  /** skill · eligibility(경력 연수 · 학력 같은 지원 자격 — 질문하지 않고 「확인만」 줄에 둔다) */
  kind: string;
  kindBasis: string;
  assessmentState?: 'complete' | 'pending';
  snapshotHash?: string;
  sourceHash?: string;
  evidenceRefs?: Record<string, unknown>[];
}

const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];

export function requirementRowFromMap(map: Record<string, unknown>): RequirementRow {
  return {
    id: String(map.id ?? ''),
    group: String(map.group ?? 'must'),
    label: String(map.label ?? ''),
    status: String(map.status ?? 'unconfirmed'),
    postingQuote: String(map.posting_quote ?? ''),
    evidencePaths: strings(map.evidence_paths),
    evidenceQuotes: strings(map.evidence_quotes),
    source: String(map.source ?? 'none'),
    kind: String(map.kind ?? 'skill'),
    kindBasis: String(map.kind_basis ?? ''),
    assessmentState: map.assessment_state === 'complete' || map.assessment_state === 'pending' ? map.assessment_state : undefined,
    snapshotHash: typeof map.snapshot_hash === 'string' ? map.snapshot_hash : undefined,
    sourceHash: typeof map.source_hash === 'string' ? map.source_hash : undefined,
    evidenceRefs: Array.isArray(map.evidence_refs) ? map.evidence_refs as Record<string, unknown>[] : [],
  };
}

export function requirementRowToMap(row: RequirementRow): Record<string, unknown> {
  return {
    id: row.id,
    group: row.group,
    label: row.label,
    status: row.status,
    posting_quote: row.postingQuote,
    evidence_paths: row.evidencePaths,
    evidence_quotes: row.evidenceQuotes,
    source: row.source,
    kind: row.kind,
    kind_basis: row.kindBasis,
    assessment_state: row.assessmentState,
    snapshot_hash: row.snapshotHash,
    source_hash: row.sourceHash,
    evidence_refs: row.evidenceRefs,
  };
}

export const isEligibility = (row: RequirementRow) => row.kind === 'eligibility';

export function requirementRowsFrom(raw: unknown): RequirementRow[] {
  return (Array.isArray(raw) ? raw : [])
    .filter((item): item is Record<string, unknown> => item !== null && typeof item === 'object')
    .map(requirementRowFromMap);
}

/** 서버(app.models.STAR_ELEMENTS)와 같은 순서 */
export const STAR_ELEMENTS: Record<string, string> = {
  situation: '상황',
  task: '과제',
  action: '행동',
  result: '결과',
};

/** 서버 응답 `star_checks`의 한 줄. 경험 항목에 상황 · 과제 · 행동 · 결과가 원문에 있는지 */
export interface StarCheck {
  fieldPath: string;
  present: string[];
  /** Legacy missing reason; v2 diagnosis is auxiliary, not a completeness checklist. */
  reason: string;
  diagnosticStatus?: 'complete' | 'pending' | 'not_applicable';
  sourceHash?: string;
  quotes?: Record<string, string>;
  experienceId?: string;
}

export function starCheckToMap(check: StarCheck): Record<string, unknown> {
  return {
    field_path: check.fieldPath,
    present: check.present,
    missing: check.diagnosticStatus && check.diagnosticStatus !== 'complete' ? []
      : Object.keys(STAR_ELEMENTS).filter((e) => !check.present.includes(e)),
    reason: check.reason,
    diagnostic_status: check.diagnosticStatus,
    source_hash: check.sourceHash,
    quotes: check.quotes,
    experience_id: check.experienceId,
  };
}

export function starChecksByPath(raw: unknown): Record<string, StarCheck> {
  const out: Record<string, StarCheck> = {};
  for (const item of Array.isArray(raw) ? raw : []) {
    if (item === null || typeof item !== 'object') continue;
    const map = item as Record<string, unknown>;
    const check: StarCheck = { fieldPath: String(map.field_path ?? ''), present: strings(map.present), reason: String(map.reason ?? '') };
    if (['complete', 'pending', 'not_applicable'].includes(String(map.diagnostic_status))) {
      check.diagnosticStatus = map.diagnostic_status as StarCheck['diagnosticStatus'];
    }
    if (typeof map.source_hash === 'string' && map.source_hash !== '') check.sourceHash = map.source_hash;
    if (typeof map.experience_id === 'string') check.experienceId = map.experience_id;
    if (map.quotes && typeof map.quotes === 'object') {
      check.quotes = Object.fromEntries(Object.entries(map.quotes).filter((pair): pair is [string, string] => typeof pair[1] === 'string'));
    }
    if (check.fieldPath !== '') out[check.fieldPath] = check;
  }
  return out;
}

/** Original-text auxiliary diagnosis; legacy cards retain their display contract. */
export function ReviewStarCells({ check }: { check: StarCheck }) {
  if (check.diagnosticStatus === 'not_applicable') return null;
  if (check.diagnosticStatus === 'pending') {
    return <div className="rv-star">현재 원문 STAR · 판정 대기 / 갱신 필요</div>;
  }
  const diagnostic = check.diagnosticStatus === 'complete';
  return (
    <div className="rv-star" title={check.reason || undefined}>
      {diagnostic && <span>현재 원문 STAR · 보조 진단</span>}
      {Object.entries(STAR_ELEMENTS).map(([key, label]) => {
        const has = check.present.includes(key);
        return (
          <span key={key} title={check.quotes?.[key]} className={`rv-star__cell ${has ? 'is-ok' : diagnostic ? '' : 'is-missing'}`} aria-label={`${label} ${has ? '근거 확인' : diagnostic ? '근거 미확인' : '빠짐'}`}>
            {has ? `${label} ✓` : `${label} ${diagnostic ? '근거 미확인' : '빠짐'}`}
          </span>
        );
      })}
    </div>
  );
}

export function requirementGroupLabel(group: string): string {
  return group === 'must' ? '필수' : group === 'preferred' ? '우대' : '주요 업무';
}

function requirementStatusLabel(status: string): string {
  return status === 'met' ? '근거 있음' : status === 'partial' ? '일부만 있음' : status === 'absent' ? '해당 없음' : '확인 필요';
}

const STATUS_ICON: Record<string, string> = { met: 'check', partial: 'change_history', absent: 'remove' };

/** 대화 위에 붙는 공고 요건 대조 줄. 칩을 누르면 근거가 있는 이력서 항목으로 옮겨 간다 */
export function requirementGroupSummary(rows: RequirementRow[], group: string): string {
  const inGroup=rows.filter(row=>row.group===group && !isEligibility(row));
  if (!inGroup.length)return '';
  const complete=inGroup.filter(row=>row.assessmentState!=='pending');
  const waiting=inGroup.length-complete.length;
  if (!complete.length)return `${requirementGroupLabel(group)} 대조 대기`;
  return `${requirementGroupLabel(group)} ${complete.filter(row=>row.status==='met').length}/${complete.length}${waiting ? ` · ${waiting}개 대기` : ''}`;
}

export function ReviewRequirementStrip({
  rows,
  onTapRow,
}: {
  rows: RequirementRow[];
  onTapRow(row: RequirementRow): void;
}) {
  const [expanded, setExpanded] = useState(true);
  const groups = ['must', 'preferred'];
  const judged = rows.filter((row) => !isEligibility(row));
  const eligibility = rows.filter(isEligibility);
  const count = (group: string) => requirementGroupSummary(judged,group);
  const summary = groups.map(count).filter((t) => t !== '').join(' · ');

  return (
    <div className={`rv-reqs${expanded ? '' : ' is-collapsed'}`}>
      <div className="rv-reqs__head">
        <strong>공고 요건 대조</strong>
        <span className="rv-reqs__summary">{summary} 근거 확인</span>
        <span className="spacer" />
        <button type="button" className="btn btn--text btn--sm" onClick={() => setExpanded((v) => !v)}>
          <Icon name={expanded ? 'expand_less' : 'expand_more'} size={18} />
          {expanded ? '접기' : '펼치기'}
        </button>
      </div>
      {expanded &&
        groups
          .filter((group) => judged.some((row) => row.group === group))
          .map((group) => (
            <div key={group} className="rv-reqs__group">
              <span className="rv-reqs__label">{requirementGroupLabel(group)}</span>
              <div className="rv-reqs__chips">
                {judged
                  .filter((row) => row.group === group)
                  .map((row) => (
                    <button
                      key={row.id}
                      type="button"
                      className={`rv-req-chip is-${row.status}`}
                      title={`${row.assessmentState === 'pending' ? '미판정 / 갱신 필요' : row.status === 'unconfirmed' && row.assessmentState === 'complete' ? '현재 분석에서 직접 근거 미확인 (경험 없음 판정 아님)' : requirementStatusLabel(row.status)} · 공고: ${row.postingQuote}${row.evidenceRefs?.map(ref => `\n${String(ref.experience_title ?? ref.experience_id ?? ref.field_path)}: ${String(ref.quote ?? '')}`).join('') ?? ''}`}
                      onClick={() => onTapRow(row)}
                    >
                      <Icon name={STATUS_ICON[row.status] ?? 'help'} size={14} />
                      {row.label}
                      {row.assessmentState === 'pending' && ' · 대기'}
                    </button>
                  ))}
              </div>
            </div>
          ))}
      {expanded && eligibility.length > 0 && (
        <p
          className="rv-reqs__eligibility"
          title={eligibility.map((row) => `${row.label}: ${row.kindBasis || '지원 자격'}`).join('\n')}
        >
          <strong>지원 자격 · 확인만 </strong>
          {eligibility.map((row) => row.label).join(' · ')}
        </p>
      )}
    </div>
  );
}

/** ① 문장 다듬기 → ② 공고 요건 확인 → ③ 경험 보완 → ④ 지원동기 → ⑤ 자기소개서. 6 이상이면 모두 끝 */
export function ReviewStageBar({
  currentStage,
  includeRequirementStage,
}: {
  currentStage: number;
  includeRequirementStage: boolean;
}) {
  const stages = REVIEW_STAGE_LABELS.map((_, i) => i + 1).filter(
    (stage) => includeRequirementStage || stage !== REQUIREMENT_STAGE,
  );
  return (
    <div className="rv-stages">
      {stages.map((stage, i) => {
        const state = stage < currentStage ? 'done' : stage === currentStage ? 'now' : 'waiting';
        return (
          <span key={stage} className="rv-stages__item">
            {i > 0 && <span className="rv-stages__line" />}
            <span className={`rv-stage is-${state}`} aria-label={`${reviewStageLabel(stage)} ${state === 'now' ? '진행 중' : state === 'done' ? '완료' : '대기'}`}>
              <span className="rv-stage__no">{state === 'done' ? <Icon name="check" size={12} /> : i + 1}</span>
              {reviewStageLabel(stage)}
            </span>
          </span>
        );
      })}
    </div>
  );
}

/** 질문 말풍선 · 수정안 카드 위의 작은 표시. 요건에 연결되면 「필수 · Git 협업」, 아니면 단계 이름 */
export function ReviewItemTag({ text, requirementGroup }: { text: string; requirementGroup: string | null }) {
  const tone = requirementGroup === null ? 'plain' : requirementGroup === 'must' ? 'must' : 'preferred';
  return <span className={`rv-tag is-${tone}`}>{text}</span>;
}
