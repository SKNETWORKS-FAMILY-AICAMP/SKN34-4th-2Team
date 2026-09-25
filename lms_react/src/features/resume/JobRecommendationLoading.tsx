import { useEffect, useRef, useState } from 'react';

import { Icon } from '../../ui/Icon';
import { HangingRobot } from './HangingRobot';

/**
 * 공고 추천 로딩 — features/resume/ai_coach/presentation/job_recommendation_loading.dart
 *
 * 클립보드 카드에 네 단계가 차례로 켜지고, 왼쪽 로봇이 줄에 매달려 흔들린다
 * (3.1초 주기). 다 끝나면 줄을 놓고 떨어진다.
 */
const STEPS = [
  { id: 'resume', label: '이력서 읽기', detail: '기술과 프로젝트 경험을 살펴봐요' },
  { id: 'search', label: '공고 찾기', detail: '내 경험과 맞는 공고를 찾아요' },
  { id: 'filter', label: '지원 조건 비교', detail: '희망 조건과 지원 자격을 비교해요' },
  { id: 'judge', label: '직무 근거 비교', detail: '이력서와 공고의 연결점을 확인해요' },
] as const;

const SWAY_MS = 3100;
const FALL_MS = 1300;

export function JobRecommendationLoading({
  current,
  results,
  completed = false,
}: {
  /** 지금 도는 단계 id */
  current: string | null;
  /** 끝난 단계 id → 한 줄 결과 */
  results: Record<string, string>;
  completed?: boolean;
}) {
  const robotRef = useRef<HTMLDivElement>(null);
  const [fallStart, setFallStart] = useState<number | null>(null);
  const [motion, setMotion] = useState({ phase: 0, release: 0, done: false });

  useEffect(() => {
    if (completed && fallStart === null) setFallStart(performance.now());
  }, [completed, fallStart]);

  useEffect(() => {
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const start = performance.now();
    let frame = 0;

    const tick = (now: number) => {
      const robot = robotRef.current;
      if (still) {
        setMotion({ phase: 0, release: 0, done: false });
      } else if (fallStart !== null) {
        // 손을 놓고 왼쪽 아래로 떨어진다. release 0.15까지는 살짝 올라간다.
        const t = Math.min(1, (now - fallStart) / FALL_MS);
        const release = Math.max(0, Math.min(1, (t - 0.19) / 0.81));
        const descent = Math.max(0, Math.min(1, (release - 0.15) / 0.85));
        const dy =
          release < 0.15 ? -7 * Math.sin(((release / 0.15) * Math.PI) / 2) : -7 + 480 * descent * descent;
        if (robot !== null) robot.style.transform = `translate(${-14 * release}px, ${dy}px)`;
        setMotion({ phase: 0, release, done: t >= 1 });
      } else {
        setMotion({ phase: ((now - start) % SWAY_MS) / SWAY_MS, release: 0, done: false });
      }
      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [fallStart]);

  const index = STEPS.findIndex((s) => s.id === current);
  const status = completed
    ? '추천 준비 완료'
    : index < 0
      ? '추천을 준비하고 있어요'
      : results[STEPS[index].id] !== undefined
        ? `${STEPS[index].label} 완료`
        : `${STEPS[index].label} 진행 중`;

  return (
    <div className="joblo">
      <div className="joblo__stage">
        {/* 끝까지 떨어지면 사라진다. 원본도 그 뒤로는 그리지 않는다. */}
        {!motion.done && (
          <div className="joblo__robot" ref={robotRef} aria-hidden>
            <HangingRobot phase={motion.phase} release={motion.release} completed={completed} />
          </div>
        )}

        <div className="joblo__card">
          <span className="joblo__clip" aria-hidden />
          <strong className="joblo__title">{completed ? '추천 준비 완료!' : '공고를 고르고 있어요'}</strong>

          {index < 0 && !completed && <span className="joblo__bar" />}

          <ol className="joblo__steps">
            {STEPS.map((step, i) => {
              const done = completed || results[step.id] !== undefined || (index >= 0 && i < index);
              const running = !completed && i === index && results[step.id] === undefined;
              const detail = results[step.id] ?? (running ? step.detail : undefined);
              return (
                <li key={step.id} className="joblo__step">
                  <span className="joblo__mark">
                    {done ? (
                      <Icon name="check_circle" size={16} className="joblo__mark--done" />
                    ) : running ? (
                      <span className="spinner" />
                    ) : (
                      <Icon name="circle" size={16} className="joblo__mark--wait" />
                    )}
                    {i < STEPS.length - 1 && <i className={`joblo__line${done ? ' joblo__line--done' : ''}`} />}
                  </span>
                  <span className="joblo__text">
                    <strong className={running ? 'joblo__label--on' : undefined}>{step.label}</strong>
                    {detail !== undefined && <span className="hint">{detail}</span>}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
      </div>

      <p className={`joblo__status${completed ? ' joblo__status--done' : ''}`}>{status}</p>
    </div>
  );
}
