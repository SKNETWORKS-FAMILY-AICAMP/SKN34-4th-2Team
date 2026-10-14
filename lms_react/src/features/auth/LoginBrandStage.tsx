import { useEffect, useRef, type RefObject } from 'react';

import { clamp01, easeIn, easeInCubic, lerp } from '../../utils/curves';

/**
 * 로그인 브랜드 스테이지 — features/auth/presentation/widgets/login_brand_stage.dart
 *
 * 카드 두 장이 타원 궤도를 돌고, 가운데 PLAYDATA 패널은 제자리에서 천천히
 * 위아래로 흔들린다. 주기와 좌표는 Dart 쪽 값을 그대로 옮겼다 — 궤도 28초,
 * 맥박 8초, 중심 (0.72W, 0.48H), 반지름 (0.16W, 0.22H).
 *
 * 원본에는 마우스를 따라 무대 전체가 ±22/±14px 밀리는 시차가 있었지만, 창이
 * 좁아 카드가 모여 있을 때 덩어리째 따라 움직이는 것이 거슬려 뺐다. 움직이는
 * 것은 궤도와 맥박, 그리고 로그인 성공 때의 퇴장뿐이다.
 */
const ORBIT_MS = 28_000;
const PULSE_MS = 8_000;

interface Satellite {
  /** 궤도 위 시작 각(라디안) */
  turn: number;
  radiusScale: number;
  size: number;
  /** 회전 = base + orbit * rate (라디안) */
  baseRotation: number;
  rotationRate: number;
}

const SK: Satellite = { turn: 0.15, radiusScale: 1.05, size: 148, baseRotation: 0.2, rotationRate: 0.4 };
const ENCORE: Satellite = {
  turn: Math.PI * 0.95,
  radiusScale: 0.92,
  size: 136,
  baseRotation: -0.12,
  rotationRate: -0.3,
};

/** 안쪽으로 도는 위성의 반지름 배율 — 패널과의 간격은 이 쪽이 가장 좁다. */
const MIN_SCALE = Math.min(SK.radiusScale, ENCORE.radiusScale);

const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t));

/** 가운데 패널의 고정 크기 — Dart의 hubW/hubH */
const HUB_W = 260;
const HUB_H = 150;
/** 위성 카드 중 가장 큰 것 — 궤도 반지름의 최소치를 이 크기로 잡는다. */
const SAT_MAX = 148;

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

export function LoginBrandStage({
  exiting = false,
  exitRef,
}: {
  /** 로그인에 성공해 화면을 떠나는 중인가 */
  exiting?: boolean;
  /** 0 → 1로 흐르는 퇴장 진행도. 로그인 화면이 굴리고 여기서 읽는다. */
  exitRef?: RefObject<number>;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const skRef = useRef<HTMLDivElement>(null);
  const encoreRef = useRef<HTMLDivElement>(null);
  const hubRef = useRef<HTMLDivElement>(null);
  const glowRef = useRef<HTMLSpanElement>(null);
  const ringRef = useRef<SVGSVGElement>(null);
  const dotsRef = useRef<(HTMLSpanElement | null)[]>([]);
  const washRef = useRef<HTMLSpanElement>(null);
  // 퇴장이 시작된 순간의 궤도·맥박을 붙잡아 둔다 — Dart의 _orbit.stop().
  const frozenRef = useRef<{ orbit: number; pulse: number } | null>(null);
  const exitingRef = useRef(exiting);
  exitingRef.current = exiting;

  useEffect(() => {
    const stage = stageRef.current;
    if (stage === null) return;

    // 움직임을 줄여 달라고 한 사람에게는 멈춰 있는 화면을 보여 준다.
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const start = performance.now();
    let frame = 0;
    let stopped = false;

    const draw = (now: number) => {
      const elapsed = still ? 0 : now - start;
      let orbit = (elapsed % ORBIT_MS) / ORBIT_MS;
      // 8초를 왕복하는 삼각파에 ease를 먹인다. Flutter의 repeat(reverse: true).
      const raw = (elapsed % (PULSE_MS * 2)) / PULSE_MS;
      let pulse = easeInOut(raw <= 1 ? raw : 2 - raw);

      // 퇴장하는 동안에는 시계가 멈춘다. 멈춘 자리에서 확대만 일어난다.
      const leaving = exitingRef.current;
      if (leaving) {
        frozenRef.current ??= { orbit, pulse };
        orbit = frozenRef.current.orbit;
        pulse = frozenRef.current.pulse;
      } else {
        frozenRef.current = null;
      }
      const exitT = leaving ? clamp01(exitRef?.current ?? 0) : 0;
      const zoomT = easeInCubic(exitT);
      // 위성·후광·궤도선은 먼저 사라지고, 가운데 패널만 남아 화면을 삼킨다.
      const satellite = clamp01(1 - exitT * 1.6);

      const w = stage.clientWidth;
      const h = stage.clientHeight;

      // 원본 비율은 (0.16W, 0.22H)다. 그대로 두면 창이 좁거나 낮을 때 궤도가
      // 오그라들어 위성 카드가 가운데 패널 위에 포개진다. 그래서 반지름의 아래쪽을
      // 「패널 반 + 카드 반 + 여백」으로 잡아 둔다 — 겹칠 수가 없는 크기다.
      // 위성은 제 반지름 배율(0.92·1.05)로 놓이므로, 작은 쪽 배율로 나눠 둬야
      // 안쪽으로 도는 카드까지 패널을 비껴간다.
      const minRx = (HUB_W / 2 + SAT_MAX / 2 + 18) / MIN_SCALE;
      const minRy = (HUB_H / 2 + SAT_MAX / 2 + 18) / MIN_SCALE;
      // 위쪽은 궤도가 무대 밖으로 나가지 않는 선까지.
      const maxRx = Math.max(minRx, w / 2 - SAT_MAX / 2 - 24);
      const maxRy = Math.max(minRy, h / 2 - SAT_MAX / 2 - 24);
      const rx = clamp(w * 0.16, minRx, maxRx);
      const ry = clamp(h * 0.22, minRy, maxRy);

      // 궤도가 좌우로 삐져나가지 않도록 중심을 안쪽으로 당겨 둔다.
      const edge = rx * 1.05 + SAT_MAX / 2 + 16;
      const cx = clamp(w * 0.72, edge, Math.max(edge, w - edge));
      const cy = h * 0.48;

      const onOrbit = (turn: number, radiusScale = 1) => {
        const a = orbit * Math.PI * 2 + turn;
        return {
          x: cx + Math.cos(a) * rx * radiusScale,
          y: cy + Math.sin(a) * ry * radiusScale + pulse * 4,
        };
      };

      const place = (el: HTMLDivElement | null, sat: Satellite) => {
        if (el === null) return;
        const p = onOrbit(sat.turn, sat.radiusScale);
        const deg = ((sat.baseRotation + orbit * sat.rotationRate) * 180) / Math.PI;
        el.style.transform = `translate(${p.x - sat.size / 2}px, ${p.y - sat.size / 2}px) rotate(${deg}deg)`;
      };

      place(skRef.current, SK);
      place(encoreRef.current, ENCORE);

      if (hubRef.current !== null) {
        // 제자리(궤도 중심)에서 화면 한가운데로 옮겨 가며 22배까지 커진다.
        const left = lerp(cx - HUB_W / 2, (w - HUB_W) / 2, zoomT);
        const top = lerp(cy - HUB_H / 2 + (leaving ? 0 : pulse * 6), (h - HUB_H) / 2, zoomT);
        const scale = lerp(1, 22, zoomT);
        hubRef.current.style.transform = `translate(${left}px, ${top}px) scale(${scale})`;
        hubRef.current.style.borderRadius = `${lerp(22, 4, zoomT)}px`;
        // 청록 후광은 짙어지고, 카드가 바닥에 드리우던 그림자는 사라진다.
        hubRef.current.style.boxShadow =
          `0 0 ${lerp(28, 80, zoomT)}px ${lerp(1, 12, zoomT)}px rgba(0, 194, 212, ${lerp(0.32, 0.55, zoomT)}),` +
          ` 0 ${lerp(18, 0, zoomT)}px 46px rgba(0, 0, 0, ${lerp(0.45, 0, zoomT)})`;
      }
      if (washRef.current !== null) {
        // 마지막 반쯤에서 흰 빛이 차오른다 — 「안으로 들어간다」는 느낌.
        washRef.current.style.opacity = String(easeIn(clamp01((exitT - 0.45) / 0.55)));
      }
      if (glowRef.current !== null) {
        glowRef.current.style.transform = `translate(${cx - 160}px, ${cy - 160}px)`;
        glowRef.current.style.opacity = String(satellite);
      }
      if (skRef.current !== null) skRef.current.style.opacity = String(satellite);
      if (encoreRef.current !== null) encoreRef.current.style.opacity = String(satellite);
      if (ringRef.current !== null) {
        ringRef.current.style.transform = `translate(${cx - rx}px, ${cy - ry}px)`;
        ringRef.current.style.opacity = String(satellite);
        ringRef.current.setAttribute('width', String(rx * 2));
        ringRef.current.setAttribute('height', String(ry * 2));
        const ring = ringRef.current.firstElementChild as SVGEllipseElement | null;
        if (ring !== null) {
          ring.setAttribute('cx', String(rx));
          ring.setAttribute('cy', String(ry));
          ring.setAttribute('rx', String(rx - 1));
          ring.setAttribute('ry', String(ry - 1));
          const circumference = 2 * Math.PI * Math.max(rx, ry);
          ring.setAttribute('stroke-dasharray', `${circumference * 0.18} ${circumference}`);
          ring.setAttribute('stroke-dashoffset', String(-orbit * circumference));
        }
      }

      dotsRef.current.forEach((dot, i) => {
        if (dot === null) return;
        const p = onOrbit(i * ((Math.PI * 2) / 6) + 0.4, 1.25);
        dot.style.transform = `translate(${p.x}px, ${p.y}px)`;
        dot.style.opacity = String(satellite);
      });

      if (!stopped) frame = window.requestAnimationFrame(draw);
    };

    frame = window.requestAnimationFrame(draw);

    return () => {
      stopped = true;
      window.cancelAnimationFrame(frame);
    };
  }, [exitRef]);

  return (
    <div className="stage" ref={stageRef} aria-hidden>
      <span className="stage__glow" ref={glowRef} />

      <svg className="stage__ring" ref={ringRef}>
        <ellipse fill="none" stroke="rgba(0, 194, 212, 0.45)" strokeWidth="1" strokeLinecap="round" />
      </svg>

      {Array.from({ length: 6 }, (_, i) => (
        <span
          key={i}
          className={`stage__dot${i % 2 === 0 ? ' stage__dot--cyan' : ' stage__dot--violet'}`}
          ref={(el) => {
            dotsRef.current[i] = el;
          }}
        />
      ))}

      <div className="stage__panel stage__panel--encore" ref={encoreRef}>
        <img src="/brand/encore.jpg" alt="" />
      </div>

      <div className="stage__hub" ref={hubRef}>
        <img src="/brand/playdata.jpg" alt="" />
        <span className="stage__wash" ref={washRef} />
      </div>

      <div className="stage__panel stage__panel--sk" ref={skRef}>
        <img src="/brand/sk_networks.jpg" alt="" />
      </div>
    </div>
  );
}
