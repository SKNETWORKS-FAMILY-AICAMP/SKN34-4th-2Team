import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';

import { Icon } from '../../ui/Icon';

/**
 * 마일리지 카드 — features/mileage/presentation/widgets/mileage_credit_card.dart
 *
 * 포인터를 올리면 그 위치만큼 3D로 기울고, 광택이 기운 쪽을 따라 흐른다.
 * 포인터가 떠나면 easeOutCubic으로 제자리에 돌아온다. 최대 기울기 0.14rad,
 * 세로는 그 0.85배 — Dart 쪽 값 그대로다.
 */
const MAX_TILT = 0.14;
const RESET_MS = 320;

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

export function MileageCreditCard({
  balance,
  holderName,
  validThru,
  width = 252,
}: {
  balance: number;
  holderName?: string;
  validThru?: Date;
  width?: number;
}) {
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const resetRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (resetRef.current !== null) window.cancelAnimationFrame(resetRef.current);
    },
    [],
  );

  const stopReset = () => {
    if (resetRef.current !== null) {
      window.cancelAnimationFrame(resetRef.current);
      resetRef.current = null;
    }
  };

  const onMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    stopReset();
    const rect = e.currentTarget.getBoundingClientRect();
    const nx = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
    const ny = ((e.clientY - rect.top) / rect.height - 0.5) * 2;
    setTilt({
      y: Math.max(-1, Math.min(1, nx)) * MAX_TILT,
      x: -Math.max(-1, Math.min(1, ny)) * MAX_TILT * 0.85,
    });
  };

  const reset = useCallback(() => {
    stopReset();
    const from = { ...tilt };
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / RESET_MS);
      const k = 1 - easeOutCubic(t);
      setTilt({ x: from.x * k, y: from.y * k });
      if (t < 1) resetRef.current = window.requestAnimationFrame(step);
      else resetRef.current = null;
    };
    resetRef.current = window.requestAnimationFrame(step);
  }, [tilt]);

  // 광택은 기운 쪽 반대편에서 흐른다. Dart의 glareAlignment와 같은 식.
  const glareX = Math.max(-1, Math.min(1, tilt.y / MAX_TILT));
  const glareY = Math.max(-1, Math.min(1, -tilt.x / (MAX_TILT * 0.85)));

  const height = Math.round(width / 1.586);
  const holder = holderName === undefined || holderName.trim() === '' ? 'PLAYDATA MEMBER' : holderName;
  const thru =
    validThru === undefined
      ? '--/--'
      : `${String(validThru.getMonth() + 1).padStart(2, '0')}/${String(validThru.getFullYear()).slice(2)}`;

  return (
    <div
      className="mileage-card"
      style={{
        width,
        height,
        transform: `perspective(830px) rotateX(${tilt.x}rad) rotateY(${tilt.y}rad)`,
      }}
      onPointerMove={onMove}
      onPointerLeave={reset}
      onPointerUp={reset}
      onPointerCancel={reset}
    >
      <span
        className="mileage-card__glare"
        style={{
          background: `radial-gradient(60% 70% at ${50 + glareX * 42}% ${50 + glareY * 42}%, rgba(255,255,255,0.22) 0%, transparent 62%)`,
        }}
        aria-hidden
      />

      <div className="mileage-card__top">
        <div>
          <strong className="mileage-card__brand">PLAYDATA</strong>
          <span className="mileage-card__brand-sub">MILEAGE</span>
        </div>
        <span className="mileage-card__chip" aria-hidden />
        <Icon name="contactless" size={20} className="mileage-card__wave" />
      </div>

      <span className="mileage-card__label">TOTAL POINTS</span>
      <strong className="mileage-card__points">{balance.toLocaleString()} P</strong>

      <div className="mileage-card__foot">
        <div>
          <span className="mileage-card__label">CARD HOLDER</span>
          <strong>{holder}</strong>
        </div>
        <div className="mileage-card__thru">
          <span className="mileage-card__label">VALID THRU</span>
          <strong>{thru}</strong>
        </div>
      </div>
    </div>
  );
}
