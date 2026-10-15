import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo } from 'react-native';
import Svg, { Circle, G, Line, Path, Rect } from 'react-native-svg';

import { useTheme } from '../theme/Theme';

/**
 * 로봇 머리 — 웹 `ui/RobotHead.tsx` 를 그대로 옮겼다.
 *
 * `bounce` 가 바뀔 때마다 머리가 옆으로 잠깐 늘어났다 돌아온다(0 → 1.33 → 1 → -0.33 → 0.17 → 0).
 * 귀는 넓어질수록 껍데기 속으로 들어간다. 좌표는 원본 104×96 캔버스 그대로 두고 viewBox 로 맞춘다.
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

export function RobotHead({ size = 40, bounce = 0 }: { size?: number; bounce?: number }) {
  const { palette } = useTheme();
  const [stretch, setStretch] = useState(0);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    let frame = 0;
    let cancelled = false;
    void AccessibilityInfo.isReduceMotionEnabled().then((reduce) => {
      if (reduce || cancelled) return;
      const start = Date.now();
      const tick = () => {
        if (cancelled) return;
        const progress = Math.min(1, (Date.now() - start) / DURATION);
        setStretch(stretchAt(progress));
        if (progress < 1) frame = requestAnimationFrame(tick);
      };
      frame = requestAnimationFrame(tick);
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
  }, [bounce]);

  const morph = (from: number, to: number) => from + (to - from) * stretch;
  const primary = palette.primary;

  const head = { x: morph(14, 8), y: morph(28, 32), w: morph(76, 88), h: morph(55, 48) };
  const headRight = head.x + head.w;
  const antennaTop = head.y - morph(14, 10);
  const earVisibility = Math.max(0, Math.min(1, 1 - stretch));

  const mask = { x: head.x + 9, y: head.y + morph(10, 9), w: head.w - 18, h: head.h - morph(20, 18) };
  const eyeY = mask.y + morph(10, 8);
  const eyeH = morph(8, 7);
  const mouthWidth = morph(14, 10);
  const mouthY = mask.y + morph(17, 14);
  const mouthH = morph(12, 9);

  return (
    <Svg width={size} height={size} viewBox="0 0 104 104">
      <G transform="translate(0, 4)">
        {earVisibility > 0
          ? [false, true].map((right) => (
              <Rect
                key={String(right)}
                x={right ? headRight - 1 : head.x - 6 * earVisibility}
                y={head.y + 17}
                width={7 * earVisibility}
                height={18}
                rx={4}
                fill={palette.primaryLight}
                stroke={primary}
                strokeWidth={2.2}
              />
            ))
          : null}

        <Line x1={52} y1={head.y} x2={52} y2={antennaTop} stroke={primary} strokeWidth={2.2} strokeLinecap="round" />
        <Circle cx={52} cy={antennaTop - 2} r={4} fill={primary} />

        <Rect x={head.x} y={head.y} width={head.w} height={head.h} rx={morph(20, 17)} fill="#ffffff" stroke={primary} strokeWidth={2.2} />
        <Rect x={mask.x} y={mask.y} width={mask.w} height={mask.h} rx={morph(13, 11)} fill={NAVY} />

        {[false, true].map((right) => (
          <Rect
            key={String(right)}
            x={right ? mask.x + mask.w - morph(12, 17) - 6 : mask.x + morph(12, 17)}
            y={eyeY}
            width={6}
            height={eyeH}
            rx={3}
            fill="#ffffff"
          />
        ))}

        {/* 입은 아래로 휜 반원 */}
        <Path
          d={`M ${52 - mouthWidth / 2} ${mouthY + mouthH / 2} A ${mouthWidth / 2} ${mouthH / 2} 0 0 0 ${52 + mouthWidth / 2} ${mouthY + mouthH / 2}`}
          fill="none"
          stroke="#ffffff"
          strokeWidth={2}
          strokeLinecap="round"
        />
      </G>
    </Svg>
  );
}
