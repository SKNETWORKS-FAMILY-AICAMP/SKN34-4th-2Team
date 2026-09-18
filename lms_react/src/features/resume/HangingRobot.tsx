/**
 * 매달린 로봇 — job_recommendation_loading.dart의 _HangingRobotPainter
 *
 * 한 팔로 클립보드를 붙잡고 매달려 흔들린다. 다 끝나면 손을 펴 놓아 버리고
 * 떨어진다. 좌표·회전값은 Dart 쪽 그대로다(캔버스 58×92, translate(8,4),
 * scale 0.68). 끝나면 눈웃음 대신 입이 동그래지고, 진행 중에는 가끔 깜빡인다.
 */
export function HangingRobot({
  phase,
  release,
  completed,
}: {
  /** 0~1 흔들림 위상 */
  phase: number;
  /** 0~1 손을 놓은 정도 */
  release: number;
  completed: boolean;
}) {
  const swing = Math.sin(phase * 2 * Math.PI);
  const deg = (rad: number) => (rad * 180) / Math.PI;

  const bodyTilt = deg(completed ? release * 0.3 : swing * 0.095);
  const gripArm = deg(0.3 - release * 0.5);
  const legTilt = (i: number) =>
    deg(completed ? (i === 0 ? -0.25 : 0.33) : swing * (i === 0 ? 0.2 : -0.2));
  const freeArm = deg(completed ? release * 2.1 : 0.4 + swing * 0.12);
  const blink = !completed && phase > 0.74 && phase < 0.79;

  const body = '#ffffff';
  const tint = 'var(--robot-tint)';
  const outline = 'var(--primary)';
  const screen = 'var(--rail-dark-bg)';
  const stroke = { stroke: outline, strokeWidth: 1.7, strokeLinecap: 'round' as const };

  // 원본 CustomPaint는 캔버스 밖으로도 그릴 수 있었다. SVG는 viewBox 밖을 잘라
  // 내므로, 든 팔이 위로 나가는 만큼 캔버스를 넓혀 둔다. 좌표계는 그대로다.
  return (
    <svg width={90} height={124} viewBox="-16 -28 90 124" aria-hidden className="hanging-robot">
      <g transform="translate(8, 4) scale(0.68)">
        <g transform={`rotate(${bodyTilt}, 57, 0)`}>
          {/* 붙잡은 팔 — 손은 잡은 자리에 남고 몸만 흔들린다 */}
          <g transform={`translate(57, 0) rotate(${gripArm})`}>
            <rect x={-5} y={0} width={10} height={63} rx={5} fill={body} {...stroke} />
            <rect x={-6} y={-4} width={13} height={12} rx={5} fill={tint} {...stroke} />
            <line x1={0} y1={1} x2={5} y2={1} {...stroke} />
          </g>

          {/* 두 다리 */}
          {[0, 1].map((i) => (
            <g key={i} transform={`translate(${i === 0 ? 18 : 35}, 88) rotate(${legTilt(i)})`}>
              <rect x={-5} y={0} width={10} height={27} rx={5} fill={tint} {...stroke} />
              <rect x={-9} y={23} width={17} height={8} rx={4} fill={body} {...stroke} />
            </g>
          ))}

          {/* 반대쪽 팔 */}
          <g transform={`translate(9, 64) rotate(${freeArm})`}>
            <rect x={-5} y={0} width={10} height={28} rx={5} fill={body} {...stroke} />
            <rect x={-5} y={24} width={10} height={10} rx={5} fill={tint} {...stroke} />
          </g>

          {/* 목 · 몸통 · 가슴 계기 */}
          <rect x={19} y={49} width={13} height={9} rx={3} fill={tint} {...stroke} />
          <rect x={10} y={56} width={33} height={35} rx={10} fill={body} {...stroke} />
          <circle cx={26} cy={71} r={7} fill={tint} />
          <line x1={26} y1={67} x2={26} y2={75} {...stroke} />
          <line x1={22} y1={71} x2={30} y2={71} {...stroke} />

          {/* 머리 */}
          <g transform="rotate(7.45, 25, 36)">
            <line x1={24} y1={18} x2={24} y2={9} {...stroke} />
            <circle cx={24} cy={7} r={3} fill={outline} />
            <rect x={-2} y={28} width={6} height={12} rx={3} fill={tint} {...stroke} />
            <rect x={46} y={28} width={6} height={12} rx={3} fill={tint} {...stroke} />
            <rect x={3} y={18} width={44} height={34} rx={14} fill={body} {...stroke} />
            <rect x={8} y={23} width={34} height={24} rx={9} fill={screen} />
            {[16, 30].map((x) => (
              <rect key={x} x={x} y={30} width={4} height={blink ? 1 : 5} rx={2} fill={body} />
            ))}
            {completed ? (
              <ellipse cx={25.5} cy={40} rx={2.5} ry={3} fill="none" stroke={body} strokeWidth={1.3} />
            ) : (
              <path
                d="M 21 38 A 4.5 3 0 0 0 30 38"
                fill="none"
                stroke={body}
                strokeWidth={1.3}
              />
            )}
          </g>
        </g>
      </g>
    </svg>
  );
}
