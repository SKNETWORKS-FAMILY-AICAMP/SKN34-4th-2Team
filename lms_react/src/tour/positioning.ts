import type { TargetRect } from './targetRegistry';

export const CARD_WIDTH = 320;
export const HOLE_PADDING = 10;
export const HOLE_RADIUS = 12;
const GAP = 12;
const MARGIN = 16;

export interface Size {
  width: number;
  height: number;
}

export interface Offset {
  left: number;
  top: number;
}

export function inflate(rect: TargetRect, by: number): TargetRect {
  return {
    left: rect.left - by,
    top: rect.top - by,
    width: rect.width + by * 2,
    height: rect.height + by * 2,
  };
}

export function overlapsViewport(rect: TargetRect, viewport: Size): boolean {
  return (
    rect.left < viewport.width &&
    rect.left + rect.width > 0 &&
    rect.top < viewport.height &&
    rect.top + rect.height > 0
  );
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

/**
 * 카드 자리 — Flutter의 _TooltipPositionDelegate를 옮겼다.
 *
 * 왼쪽 레일에 붙은 타깃은 옆에 세우고, 나머지는 아래(안 들어가면 위)에 놓는다.
 * 타깃을 모르면 화면 한가운데.
 */
export function tooltipOffset(
  viewport: Size,
  cardSize: Size,
  targetRect: TargetRect | null,
): Offset {
  const minLeft = MARGIN;
  const minTop = MARGIN;
  const right = viewport.width - MARGIN;
  const bottom = viewport.height - MARGIN;
  const maxLeft = Math.max(minLeft, right - cardSize.width);
  const maxTop = Math.max(minTop, bottom - cardSize.height);

  let left: number;
  let top: number;

  if (targetRect === null) {
    left = (viewport.width - cardSize.width) / 2;
    top = (viewport.height - cardSize.height) / 2;
  } else {
    const centerX = targetRect.left + targetRect.width / 2;
    const centerY = targetRect.top + targetRect.height / 2;
    const targetRight = targetRect.left + targetRect.width;

    if (
      centerX < viewport.width * 0.38 &&
      targetRight + GAP + cardSize.width <= right
    ) {
      // 하단 메뉴도 옆에 둔다. 화면 밖으로 나가는 만큼만 위로 조정한다.
      left = targetRight + GAP;
      top = centerY - cardSize.height / 2;
    } else {
      left = centerX - cardSize.width / 2;
      const below = targetRect.top + targetRect.height + GAP;
      const above = targetRect.top - cardSize.height - GAP;
      top = below + cardSize.height <= bottom ? below : above;
    }
  }

  return {
    left: clamp(left, minLeft, maxLeft),
    top: clamp(top, minTop, maxTop),
  };
}

/** 카드 폭 — 좁은 화면에서는 여백을 뺀 만큼으로 줄어든다. */
export function cardWidth(viewportWidth: number): number {
  return Math.min(CARD_WIDTH, Math.max(0, viewportWidth - 2 * MARGIN));
}
