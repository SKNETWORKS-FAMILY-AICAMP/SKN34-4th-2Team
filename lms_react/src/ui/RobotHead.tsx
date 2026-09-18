import { useEffect, useRef, useState } from 'react';

/**
 * 로봇 머리 — features/chatbot/presentation/robot_head_icon.dart
 *
 * `bounce`가 바뀔 때마다 머리가 옆으로 잠깐 늘어났다 돌아온다. 늘어나는 정도는
 * Dart 쪽 곡선(0 → 1.33 → 1 → -0.33 → 0.17 → 0)을 그대로 쓴다. 귀는 넓어질수록
 * 껍데기 속으로 들어간다.
 *
 * `inverted`는 이력서 화면의 AI 코치용이다. 같은 화면 오른쪽 아래에 학생 챗봇이
 * 떠 있어서, 색을 뒤집어 어느 쪽과 이야기하는지 구분한다.
 */
const STOPS = [0, 0.28, 0.45, 0.7, 0.86, 1];
const VALUES = [0, 1.33, 1, -0.33, 0.17, 0];
const DURATION = 700;
const NAVY = '#0b2a6f';

const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t));

function stretchAt(progress: number): number {
  for (let i = 1; i < STOPS.length; i++) {
    if (progress <= STOPS[i]) {
      const t = (progress - STOPS[i - 1]) / (STOPS[i] - STOPS[i - 1]);
      return VALUES[i - 1] + (VALUES[i] - VALUES[i - 1]) * easeInOut(t);
    }
  }
  return 0;
}

export function RobotHead({
  size = 40,
  bounce = 0,
  inverted = false,
}: {
  size?: number;
  /** 값이 바뀔 때마다 한 번 튄다. */
  bounce?: number;
  inverted?: boolean;
}) {
  const [stretch, setStretch] = useState(0);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / DURATION);
      setStretch(stretchAt(progress));
      if (progress < 1) frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [bounce]);

  const morph = (from: number, to: number) => from + (to - from) * stretch;

  // 원본은 104×96 캔버스에 그린다. 좌표를 그대로 두고 viewBox로 맞춘다.
  const head = {
    x: morph(14, 8),
    y: morph(28, 32),
    w: morph(76, 88),
    h: morph(55, 48),
  };
  const headRight = head.x + head.w;
  const antennaTop = head.y - morph(14, 10);
  const earVisibility = Math.max(0, Math.min(1, 1 - stretch));

  const shell = inverted ? 'var(--primary)' : '#ffffff';
  const screen = inverted ? '#ffffff' : NAVY;
  const face = inverted ? 'var(--primary)' : '#ffffff';

  const mask = {
    x: head.x + 9,
    y: head.y + morph(10, 9),
    w: head.w - 18,
    h: head.h - morph(20, 18),
  };
  const eyeY = mask.y + morph(10, 8);
  const eyeH = morph(8, 7);
  const mouthWidth = morph(14, 10);
  const mouthY = mask.y + morph(17, 14);
  const mouthH = morph(12, 9);

  return (
    <svg width={size} height={size} viewBox="0 0 104 104" aria-hidden className="robot">
      <g transform="translate(0, 4)">
      {earVisibility > 0 &&
        [false, true].map((right) => (
          <rect
            key={String(right)}
            x={right ? headRight - 1 : head.x - 6 * earVisibility}
            y={head.y + 17}
            width={7 * earVisibility}
            height={18}
            rx={4}
            fill="var(--primary-light)"
            stroke="var(--primary)"
            strokeWidth={2.2}
          />
        ))}

      <line
        x1={52}
        y1={head.y}
        x2={52}
        y2={antennaTop}
        stroke="var(--primary)"
        strokeWidth={2.2}
        strokeLinecap="round"
      />
      <circle cx={52} cy={antennaTop - 2} r={4} fill="var(--primary)" />

      <rect
        x={head.x}
        y={head.y}
        width={head.w}
        height={head.h}
        rx={morph(20, 17)}
        fill={shell}
        stroke="var(--primary)"
        strokeWidth={2.2}
      />

      <rect x={mask.x} y={mask.y} width={mask.w} height={mask.h} rx={morph(13, 11)} fill={screen} />

      {[false, true].map((right) => (
        <rect
          key={String(right)}
          x={right ? mask.x + mask.w - morph(12, 17) - 6 : mask.x + morph(12, 17)}
          y={eyeY}
          width={6}
          height={eyeH}
          rx={3}
          fill={face}
        />
      ))}

      {/* 입은 아래로 휜 반원 */}
      <path
        d={`M ${52 - mouthWidth / 2} ${mouthY + mouthH / 2} A ${mouthWidth / 2} ${mouthH / 2} 0 0 0 ${
          52 + mouthWidth / 2
        } ${mouthY + mouthH / 2}`}
        fill="none"
        stroke={face}
        strokeWidth={inverted ? 2.2 : 2}
        strokeLinecap="round"
      />

      </g>
    </svg>
  );
}
