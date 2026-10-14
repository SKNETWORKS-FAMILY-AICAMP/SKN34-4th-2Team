import { useMemo, useState } from 'react';

import { useDb } from '../../data/repository';
import type { AiGenerationLog } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { Badge, PageHeader } from '../../ui/components';
import { formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';

/**
 * LLMOps — features/admin/presentation/admin_ai_quality_screen.dart
 *
 * 관측 지표(성공률·지연·비용), 평가 결과, 프롬프트 버전별 채택률을 본다.
 * 서버는 기수의 최근 로그 500건과 최근 평가 50건만 내려 준다.
 */
const TYPE_LABELS: Record<string, string> = {
  assessment: '문제생성',
  job_chat: '공고챗봇',
  job_recommend: '추천',
  resume_review: '첨삭',
  student_chatbot: '학생챗봇',
  admin_assistant: '관리자 도우미',
};

const LOG_PAGE = 50;
const EVAL_SHOWN = 5;

function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? (type || '기타');
}

function timeOf(date: Date | undefined): number {
  return date?.getTime() ?? 0;
}

export function AdminAiQualityScreen() {
  const user = useCurrentUser();
  const rawLogs = useDb((db) => db.aiLogs);
  const rawEvals = useDb((db) => db.aiEvals);
  const [type, setType] = useState('all');
  const [shown, setShown] = useState(LOG_PAGE);

  const logs = useMemo(() => [...rawLogs].sort((a, b) => timeOf(b.createdAt) - timeOf(a.createdAt)), [rawLogs]);
  const evals = useMemo(() => [...rawEvals].sort((a, b) => timeOf(b.ranAt) - timeOf(a.ranAt)), [rawEvals]);
  const typeFilters = useMemo<[string, string][]>(() => {
    const present = new Set(logs.map((l) => l.type));
    const known = Object.keys(TYPE_LABELS);
    const extra = [...present].filter((t) => !known.includes(t)).sort();
    return [['all', '전체'], ...[...known, ...extra].map((t): [string, string] => [t, typeLabel(t)])];
  }, [logs]);

  const filtered = useMemo(() => (type === 'all' ? logs : logs.filter((l) => l.type === type)), [logs, type]);
  const stats = useMemo(() => summarize(filtered), [filtered]);

  // 프롬프트 버전별 묶음 — 원본의 byPromptVersion. 고른 유형 안에서만 묶는다
  const versions = useMemo(() => {
    const groups = new Map<string, AiGenerationLog[]>();
    for (const log of filtered) {
      const key = log.promptVersion.trim();
      groups.set(key, [...(groups.get(key) ?? []), log]);
    }
    return [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [filtered]);

  const showAssessment = type === 'all' || type === 'assessment';
  const chooseType = (id: string) => {
    setType(id);
    setShown(LOG_PAGE);
  };

  return (
    <div className="admin-page admin-page--wide llmops">
      <PageHeader title="AI 품질 (LLMOps)" description={`${user.cohortName} · 관측 · 평가 · 피드백 · 프롬프트 버전`} />

      <div className="mchips">
        {typeFilters.map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`mchip${type === id ? ' mchip--on' : ''}`}
            onClick={() => chooseType(id)}
          >
            {type === id && <Icon name="check" size={14} />}
            {label}
          </button>
        ))}
      </div>

      <div className="stat-chips">
        <StatChip label="요청수" value={String(stats.total)} />
        <StatChip label="성공률" value={`${stats.successRate.toFixed(1)}%`} />
        <StatChip label="평균 지연" value={`${stats.avgLatency}ms`} />
        <StatChip label="p95 지연" value={`${stats.p95Latency}ms`} />
        {showAssessment && (
          <>
            <StatChip label="생성 문항" value={String(stats.generated)} />
            <StatChip label="채택률" value={`${stats.adoptionRate.toFixed(1)}%`} />
            <StatChip label="수정률" value={`${stats.editRate.toFixed(1)}%`} />
          </>
        )}
        <StatChip label="유용률" value={`${stats.usefulnessRate.toFixed(1)}%`} />
        <StatChip label="총 토큰" value={stats.tokens === 0 ? '-' : stats.tokens.toLocaleString()} />
        <StatChip
          label="대략 비용 (추정치)"
          value={stats.tokens === 0 ? '-' : `$${stats.cost.toFixed(4)}`}
        />
      </div>

      <h2 className="llmops__title">최근 평가 실행</h2>
      {evals.length === 0 ? (
        <p className="hint">아직 평가 실행 기록이 없습니다.</p>
      ) : (
        evals.slice(0, EVAL_SHOWN).map((run) => (
          <div key={run.id} className="panel llmops__card">
            <strong className="llmops__card-title">
              {run.promptVersion || '버전 없음'}
              {run.model ? ` · ${run.model}` : ''}
            </strong>
            <span className="hint">
              source={run.suite || '-'} · 사례 {run.caseCount} · 통과 {Math.round(run.caseCount * run.passRate)} · 정답률{' '}
              {(run.passRate * 100).toFixed(1)}%
              {run.avgLatencyMs !== undefined ? ` · 평균 ${run.avgLatencyMs}ms` : ''} · {formatDateTime(run.ranAt)}
            </span>
          </div>
        ))
      )}

      <h2 className="llmops__title">프롬프트 버전별</h2>
      {versions.length === 0 ? (
        <p className="hint">아직 버전별 데이터가 없습니다.</p>
      ) : (
        versions.map(([version, rows]) => {
          const stat = summarize(rows);
          return (
            <div key={version || '-'} className="panel llmops__card">
              <strong className="llmops__card-title">{version || '버전 없음'}</strong>
              <span className="hint">
                요청 {stat.total} · 성공률 {stat.successRate.toFixed(1)}% · 평균 {stat.avgLatency}ms
                {stat.generated > 0
                  ? ` · 생성 ${stat.generated} · 채택+수정 ${stat.adopted} · 채택률 ${stat.adoptionRate.toFixed(1)}%`
                  : ''}
                {stat.useful > 0 ? ` · 유용 피드백 ${stat.useful}` : ''}
              </span>
            </div>
          );
        })
      )}

      <h2 className="llmops__title">최근 생성 로그</h2>
      {filtered.length === 0 ? (
        <p className="hint">
          아직 AI 생성 로그가 없습니다.
          <br />
          문제 생성 · 취업 코치 · 학생 챗봇을 실행해 보세요.
        </p>
      ) : (
        <>
          {filtered.slice(0, shown).map((log) => (
            <div key={log.id} className="panel llmops__log">
              <header className="llmops__log-head">
                <span className="llmops__tag">{typeLabel(log.type)}</span>
                <Badge tone={log.status === 'success' ? 'success' : 'error'}>
                  {log.status === 'success' ? '성공' : '실패'}
                </Badge>
                <strong>{log.createdAt ? formatDateTime(log.createdAt) : '-'}</strong>
                {log.createdByName && <span className="hint">{log.createdByName}</span>}
                <span className="spacer" />
                <span className="hint">{log.latencyMs.toLocaleString()}ms</span>
              </header>
              <p className="llmops__log-body">
                {[
                  log.promptVersion || '버전 없음',
                  log.model || '모델 미기록',
                  log.generatedCount > 0 ? `생성 ${log.generatedCount}` : '',
                  log.tokenIn !== undefined || log.tokenOut !== undefined
                    ? `토큰 ${(log.tokenIn ?? 0).toLocaleString()}/${(log.tokenOut ?? 0).toLocaleString()}`
                    : '',
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
              {log.errorMessage && <p className="llmops__log-error">{log.errorMessage}</p>}
            </div>
          ))}
          {filtered.length > shown && (
            <button type="button" className="btn btn--outline btn--md" onClick={() => setShown((n) => n + LOG_PAGE)}>
              더 보기 ({filtered.length - shown}건 남음)
            </button>
          )}
        </>
      )}
    </div>
  );
}

function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="stat-chip">
      <span className="stat-chip__label">{label}</span>
      <strong className="stat-chip__value">{value}</strong>
    </span>
  );
}

interface Summary {
  total: number;
  /** 백분율(%) */
  successRate: number;
  avgLatency: number;
  p95Latency: number;
  generated: number;
  /** 채택 + 수정 */
  adopted: number;
  adoptionRate: number;
  editRate: number;
  useful: number;
  usefulnessRate: number;
  tokens: number;
  cost: number;
  failures: number;
}

/** 지표 계산 — Dart의 AiOpsStats와 같은 식이다. */
function summarize(logs: AiGenerationLog[]): Summary {
  if (logs.length === 0) {
    return {
      total: 0,
      successRate: 0,
      avgLatency: 0,
      p95Latency: 0,
      generated: 0,
      adopted: 0,
      adoptionRate: 0,
      editRate: 0,
      useful: 0,
      usefulnessRate: 0,
      tokens: 0,
      cost: 0,
      failures: 0,
    };
  }
  const ok = logs.filter((l) => l.status === 'success');
  const latencies = logs.map((l) => l.latencyMs).sort((a, b) => a - b);
  const p95 = latencies[Math.min(latencies.length - 1, Math.floor(latencies.length * 0.95))];
  const tokenIn = logs.reduce((s, l) => s + (l.tokenIn ?? 0), 0);
  const tokenOut = logs.reduce((s, l) => s + (l.tokenOut ?? 0), 0);
  const generated = logs.reduce((s, l) => s + l.generatedCount, 0);
  const adopted = logs.reduce((s, l) => s + (l.adoptedCount ?? 0), 0);
  const edited = logs.reduce((s, l) => s + (l.editedCount ?? 0), 0);
  const useful = logs.reduce((s, l) => s + (l.usefulCount ?? 0), 0);
  const pct = (part: number, whole: number) => (whole <= 0 ? 0 : (part / whole) * 100);

  return {
    total: logs.length,
    successRate: pct(ok.length, logs.length),
    avgLatency: Math.round(logs.reduce((s, l) => s + l.latencyMs, 0) / logs.length),
    p95Latency: p95,
    generated,
    adopted: adopted + edited,
    adoptionRate: pct(adopted + edited, generated),
    editRate: pct(edited, generated),
    useful,
    usefulnessRate: pct(useful, generated),
    tokens: tokenIn + tokenOut,
    // 입력 $3 / 출력 $15 per 1M 토큰 기준의 어림값
    cost: (tokenIn / 1_000_000) * 3 + (tokenOut / 1_000_000) * 15,
    failures: logs.length - ok.length,
  };
}
