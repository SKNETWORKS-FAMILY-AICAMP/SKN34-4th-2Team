import { describe, expect, it } from 'vitest';

import { cardWidth, inflate, overlapsViewport, tooltipOffset } from '../positioning';

const viewport = { width: 1280, height: 800 };
const card = { width: 320, height: 180 };

describe('툴팁 배치', () => {
  it('타깃을 모르면 화면 한가운데', () => {
    const { left, top } = tooltipOffset(viewport, card, null);
    expect(left).toBe((1280 - 320) / 2);
    expect(top).toBe((800 - 180) / 2);
  });

  it('왼쪽 레일 메뉴는 옆에 세운다', () => {
    const rect = { left: 12, top: 300, width: 192, height: 40 };
    const { left, top } = tooltipOffset(viewport, card, rect);
    expect(left).toBe(12 + 192 + 12);
    expect(top).toBe(320 - 90);
  });

  it('레일 맨 아래 메뉴도 옆에 두되 화면 안으로 끌어올린다', () => {
    const rect = { left: 12, top: 760, width: 192, height: 40 };
    const { top } = tooltipOffset(viewport, card, rect);
    expect(top).toBe(800 - 16 - 180);
  });

  it('가운데 타깃은 아래에 놓는다', () => {
    const rect = { left: 600, top: 200, width: 200, height: 60 };
    const { left, top } = tooltipOffset(viewport, card, rect);
    expect(left).toBe(700 - 160);
    expect(top).toBe(260 + 12);
  });

  it('아래에 자리가 없으면 위로 올린다', () => {
    const rect = { left: 600, top: 700, width: 200, height: 60 };
    const { top } = tooltipOffset(viewport, card, rect);
    expect(top).toBe(700 - 180 - 12);
  });

  it('여백 밖으로는 나가지 않는다', () => {
    const rect = { left: 1240, top: 10, width: 30, height: 30 };
    const { left, top } = tooltipOffset(viewport, card, rect);
    expect(left).toBeLessThanOrEqual(1280 - 16 - 320);
    expect(top).toBeGreaterThanOrEqual(16);
  });
});

describe('보조 계산', () => {
  it('좁은 화면에서는 카드가 여백만큼 줄어든다', () => {
    expect(cardWidth(1280)).toBe(320);
    expect(cardWidth(300)).toBe(268);
  });

  it('구멍은 타깃보다 패딩만큼 크다', () => {
    expect(inflate({ left: 100, top: 100, width: 50, height: 20 }, 10)).toEqual({
      left: 90,
      top: 90,
      width: 70,
      height: 40,
    });
  });

  it('화면 밖 타깃은 겹치지 않는다', () => {
    expect(overlapsViewport({ left: 10, top: 10, width: 10, height: 10 }, viewport)).toBe(true);
    expect(overlapsViewport({ left: 10, top: 900, width: 10, height: 10 }, viewport)).toBe(false);
  });
});
