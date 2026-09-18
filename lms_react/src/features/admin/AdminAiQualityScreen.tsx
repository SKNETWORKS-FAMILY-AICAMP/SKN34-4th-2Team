import { useMemo, useState } from 'react';

import { useDb } from '../../data/repository';
import type { AiGenerationLog } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { Badge } from '../../ui/components';
import { formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';

/**
 * LLMOps — features/admin/presentation/admin_ai_quality_screen.dart
 *
 * 관측 지표(성공률·지연·비용), 평가 결과, 프롬프트 버전별 채택률을 본다.
 * 프로토타입의 로그는 seed에서 만들어진 값이다.
 */
const TYPE_FILTERS: [string, string][] = [
  ['all', '전체'],
  ['assessment', '문제생성'],
  ['job_chat', '공고챗봇'],
  ['job_recommend', '추천'],
  ['resume_review', '첨삭'],
  ['student_chatbot', '학생챗봇'],
];

export function AdminAiQualityScreen() {
  const user = useCurrentUser();
  const logs = useDb((db) => db.aiLogs);
  const evals = useDb((db) => db.aiEvals);
  const [type, setType] = useState('all');

  const filtered = type === 'all' ? logs : logs.filter((l) => l.type === type);
  const stats = useMemo(() => summarize(filtered), [filtered]);
  const latestEval = [...evals].sort(
    (a, b) => (b.ranAt?.getTime() ?? 0) - (a.ranAt?.getTime() ?? 0),
  )[0];

  // 프롬프트 버전별 묶음 — 원본의 byPromptVersion
  const versions = Array.from(new Set(logs.map((l) => l.promptVersion)));

  const showAssessment = type === 'all' || type === 'assessment';

  return (
    <div className="admin-page admin-page--wide llmops">
      <h1 className="admin-page__title">LLMOps · {user.cohortName}</h1>
      <p className="admin-page__desc">관측 · 평가 · 피드백 · 프롬프트 버전</p>

      <div className="mchips">
        {TYPE_FILTERS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`mchip${type === id ? ' mchip--on' : ''}`}
            onClick={() => setType(id)}
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
      {latestEval === undefined ? (
        <p className="hint">아직 평가 실행 기록이 없습니다.</p>
      ) : (
        <div className="panel llmops__card">
          <strong className="llmops__card-title">
            {latestEval.promptVersion} · {latestEval.model ?? 'gpt-5.6-sol'}
          </strong>
          <span className="hint">
            source={latestEval.suite} · 사례 {latestEval.caseCount} · 통과{' '}
            {Math.round(latestEval.caseCount * latestEval.passRate)} · 정답률{' '}
            {(latestEval.passRate * 100).toFixed(1)}% · 평균 {latestEval.avgLatencyMs ?? 0}ms ·{' '}
            {formatDateTime(latestEval.ranAt)}
          </span>
        </div>
      )}

      <h2 className="llmops__title">프롬프트 버전별</h2>
      {versions.length === 0 ? (
        <p className="hint">아직 버전별 데이터가 없습니다.</p>
      ) : (
        versions.map((version) => {
          const rows = logs.filter((l) => l.promptVersion === version);
          const stat = summarize(rows);
          return (
            <div key={version} className="panel llmops__card">
              <strong className="llmops__card-title">{version}</strong>
              <span className="hint">
                생성 {stat.generated} · 채택+수정 {stat.adopted} ·{' '}
                {stat.generated > 0 ? `채택률 ${stat.adoptionRate.toFixed(1)}% · ` : ''}유용 피드백{' '}
                {stat.useful}
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
        filtered.map((log) => (
          <div key={log.id} className="panel llmops__log">
            <header className="llmops__log-head">
              <span className="llmops__tag">
                {TYPE_FILTERS.find(([id]) => id === log.type)?.[1] ?? log.type}
              </span>
              <Badge tone={log.status === 'success' ? 'success' : 'error'}>{log.status}</Badge>
              <strong>{formatDateTime(log.createdAt)}</strong>
              <span className="spacer" />
              <span className="hint">{log.latencyMs}ms</span>
            </header>
            <p className="llmops__log-body">
              {log.promptVersion} · {log.model}
              {log.generatedCount > 0 && ` · 생성 ${log.generatedCount}`}
              {log.tokenIn !== undefined &&
                ` · 토큰 ${(log.tokenIn ?? 0).toLocaleString()}/${(log.tokenOut ?? 0).toLocaleString()}`}
            </p>
            {log.errorMessage !== undefined && (
              <p className="llmops__log-error">{log.errorMessage}</p>
            )}
          </div>
        ))
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
