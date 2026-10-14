/**
 * Flutter Curves를 그대로 옮긴 것 — core의 애니메이션이 같은 모양으로 움직이게 한다.
 *
 * Flutter의 Curves.easeInCubic 같은 것들은 전부 3차 베지에다. 근사식을 쓰면 끝이
 * 미세하게 어긋나므로, 여기서는 같은 제어점을 뉴턴법으로 풀어 값을 낸다.
 */
function cubicBezier(x1: number, y1: number, x2: number, y2: number) {
  const ax = 3 * x1 - 3 * x2 + 1;
  const bx = 3 * x2 - 6 * x1;
  const cx = 3 * x1;
  const ay = 3 * y1 - 3 * y2 + 1;
  const by = 3 * y2 - 6 * y1;
  const cy = 3 * y1;

  const sampleX = (t: number) => ((ax * t + bx) * t + cx) * t;
  const slopeX = (t: number) => (3 * ax * t + 2 * bx) * t + cx;

  return (x: number): number => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    // 여덟 번이면 화면에서 구별되지 않을 만큼 수렴한다.
    let t = x;
    for (let i = 0; i < 8; i += 1) {
      const dx = sampleX(t) - x;
      if (Math.abs(dx) < 1e-6) break;
      const d = slopeX(t);
      if (Math.abs(d) < 1e-6) break;
      t -= dx / d;
    }
    return ((ay * t + by) * t + cy) * t;
  };
}

export const easeIn = cubicBezier(0.42, 0, 1, 1);
export const easeInCubic = cubicBezier(0.55, 0.055, 0.675, 0.19);
export const easeInOutCubic = cubicBezier(0.645, 0.045, 0.355, 1);
export const easeOutCubic = cubicBezier(0.215, 0.61, 0.355, 1);

export const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

/** Flutter Interval(begin, end) — 구간 밖은 0과 1로 눌린다. */
export const interval = (t: number, begin: number, end: number) =>
  clamp01((t - begin) / (end - begin));

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
