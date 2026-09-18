/**
 * 마일리지 미션 — core/constants/mission_rules.dart + shared/models/mission_models.dart
 *
 * 기록실에 낸 것이 승인되면 규칙에 따라 자동으로 적립된다. 그 규칙과, 다음 목표를
 * 사람 말로 풀어 쓰는 안내문이 여기 있다. 기록실과 대시보드가 같은 것을 읽는다.
 */
import type { Submission } from './types';

export interface MissionTier {
  count: number;
  amount: number;
}

export const MissionRules = {
  studyCertTiers: [
    { count: 3, amount: 10000 },
    { count: 5, amount: 30000 },
    { count: 10, amount: 50000 },
  ] as MissionTier[],
  quizTiers: [
    { count: 1, amount: 10000 },
    { count: 3, amount: 30000 },
    { count: 5, amount: 50000 },
  ] as MissionTier[],
  quizPassScore: 60,
  blogUnitReward: 20000,
  blogMaxUnits: 5,
  studyTeamReward: 50000,
  codingPcce: 25000,
  codingAdvanced: 50000,
};

/** 지금까지 넘어선 단계의 금액 */
export function tierTarget(count: number, tiers: MissionTier[]): number {
  let target = 0;
  for (const t of tiers) if (count >= t.count) target = t.amount;
  return target;
}

/** 아직 넘지 못한 첫 단계. 다 넘었으면 null. */
export function nextTier(count: number, tiers: MissionTier[]): MissionTier | null {
  for (const t of tiers) if (count < t.count) return t;
  return null;
}

export interface MissionProgress {
  studyCertCount: number;
  studyCertGranted: number;
  quizPassCount: number;
  quizGranted: number;
  codingPcce: boolean;
  codingPccp: boolean;
  codingPcsql: boolean;
  codingGranted: number;
  blogWeeks: number;
  blogUnitsGranted: number;
  studyWeeks: number;
  studyGranted: boolean;
}

/** 승인된 제출을 모아 지금 상태를 센다 — mission_providers.dart의 집계 자리 */
export function missionProgressOf(submissions: Submission[]): MissionProgress {
  const approved = submissions.filter((s) => s.status === 'approved');
  const of = (type: string) => approved.filter((s) => s.type === type);
  const granted = (type: string) => of(type).reduce((sum, s) => sum + s.mileageAmount, 0);

  const certs = of('certification');
  const has = (kind: string) => certs.some((s) => (s.certType ?? '').includes(kind));
  const studyWeeks = of('study').length;

  return {
    studyCertCount: of('studyCert').length,
    studyCertGranted: granted('studyCert'),
    quizPassCount: of('precourseQuiz').length,
    quizGranted: granted('precourseQuiz'),
    codingPcce: has('PCCE'),
    codingPccp: has('PCCP'),
    codingPcsql: has('PCSQL'),
    codingGranted: granted('certification'),
    blogWeeks: of('blog').length,
    blogUnitsGranted: Math.floor(granted('blog') / MissionRules.blogUnitReward),
    studyWeeks,
    studyGranted: granted('study') >= MissionRules.studyTeamReward,
  };
}

export interface MissionGuidanceItem {
  id: string;
  title: string;
  earned: number;
  maxEarn: number;
  /** 지금까지 얼마나 했는지 */
  progressLabel: string;
  /** 다음 목표 한 줄 — 파랗게 나온다 */
  statusText: string;
  /** 무엇을 하면 되는지 */
  hint: string;
}

/** buildMissionGuidance(p) 그대로 */
export function buildMissionGuidance(p: MissionProgress): MissionGuidanceItem[] {
  const items: MissionGuidanceItem[] = [];

  const nextStudy = nextTier(p.studyCertCount, MissionRules.studyCertTiers);
  items.push({
    id: 'studyCert',
    title: '학습인증 (예수학제)',
    earned: p.studyCertGranted,
    maxEarn: 50000,
    progressLabel: `승인 ${p.studyCertCount}회 · 적립 ${p.studyCertGranted}M`,
    statusText:
      nextStudy === null ? '최대 금액 달성' : `다음: ${nextStudy.count}회 → ${nextStudy.amount}M`,
    hint:
      nextStudy === null
        ? '학습인증 미션을 모두 달성했어요.'
        : `${nextStudy.count - p.studyCertCount}회 더 승인되면 ${
            nextStudy.amount - p.studyCertGranted
          }M을 더 받을 수 있어요.`,
  });

  const nextQuiz = nextTier(p.quizPassCount, MissionRules.quizTiers);
  items.push({
    id: 'precourseQuiz',
    title: '프리코스 퀴즈 (60점↑)',
    earned: p.quizGranted,
    maxEarn: 50000,
    progressLabel: `통과 ${p.quizPassCount}회 · 적립 ${p.quizGranted}M`,
    statusText:
      nextQuiz === null ? '최대 금액 달성' : `다음: ${nextQuiz.count}회 → ${nextQuiz.amount}M`,
    hint:
      nextQuiz === null
        ? '프리코스 퀴즈 미션을 모두 달성했어요.'
        : `${nextQuiz.count - p.quizPassCount}회 더 통과·승인되면 ${
            nextQuiz.amount - p.quizGranted
          }M을 더 받을 수 있어요.`,
  });

  const kinds = [
    p.codingPcce ? 'PCCE' : null,
    p.codingPccp ? 'PCCP' : null,
    p.codingPcsql ? 'PCSQL' : null,
  ].filter((v): v is string => v !== null);
  items.push({
    id: 'coding',
    title: '코딩테스트 (PCCE/PCCP/PCSQL)',
    earned: p.codingGranted,
    maxEarn: 50000,
    progressLabel: kinds.length === 0 ? '미취득' : kinds.join(' · '),
    statusText:
      p.codingGranted >= 50000
        ? '최대 금액 달성'
        : p.codingPcce
          ? 'PCCP/PCSQL 취득 시 총 50,000M'
          : 'PCCE 25,000M / PCCP·PCSQL 50,000M',
    hint:
      p.codingGranted >= 50000
        ? '코딩테스트 미션 적립이 완료됐어요.'
        : '자격증 유형으로 제출·승인되면 규칙에 따라 적립됩니다.',
  });

  items.push({
    id: 'blog',
    title: '블로그 (단위기간 연속)',
    earned: p.blogUnitsGranted * MissionRules.blogUnitReward,
    maxEarn: MissionRules.blogMaxUnits * MissionRules.blogUnitReward,
    progressLabel: `완료 단위 ${p.blogUnitsGranted}/${MissionRules.blogMaxUnits} · 승인 주차 ${p.blogWeeks}개`,
    statusText:
      p.blogUnitsGranted >= MissionRules.blogMaxUnits
        ? '최대 금액 달성'
        : `단위기간 전 주차 작성 시 +${MissionRules.blogUnitReward}M`,
    hint: '단위기간마다 모든 주차를 빠짐없이 작성·승인받으면 적립됩니다.',
  });

  items.push({
    id: 'study',
    title: '팀 스터디 (1~2단위)',
    earned: p.studyGranted ? MissionRules.studyTeamReward : 0,
    maxEarn: MissionRules.studyTeamReward,
    progressLabel: p.studyGranted
      ? `달성 · ${MissionRules.studyTeamReward}M`
      : `인증 주 ${p.studyWeeks}개`,
    statusText: p.studyGranted ? '미션 달성' : '1~2단위기간 매주 1회 이상 팀 스터디 인증',
    hint: p.studyGranted
      ? '팀 스터디 미션을 달성했어요.'
      : '오프라인 팀 스터디 사진을 주 1회 이상 올려 주세요.',
  });

  return items;
}
