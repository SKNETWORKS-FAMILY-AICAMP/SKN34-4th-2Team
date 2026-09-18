import { beforeEach, describe, expect, it } from 'vitest';

import { clearDismiss, debugReset, dismiss, isDismissed, storageKey } from '../dismissStore';

const key = { tourId: 'student', version: 1, uid: 'u1' };

beforeEach(() => {
  debugReset();
  window.localStorage.clear();
});

describe('다시 보지 않기', () => {
  it('키 모양이 Flutter와 같다', () => {
    expect(storageKey(key)).toBe('onboarding_student_v1_u1');
  });

  it('처음에는 보여 준다', () => {
    expect(isDismissed(key)).toBe(false);
  });

  it('한 번 끄면 다시 뜨지 않는다', () => {
    dismiss(key);
    debugReset(); // 새로고침한 셈
    expect(isDismissed(key)).toBe(true);
  });

  it('버전이 오르면 다시 보여 준다', () => {
    dismiss(key);
    expect(isDismissed({ ...key, version: 2 })).toBe(false);
  });

  it('사용자가 다르면 따로 센다', () => {
    dismiss(key);
    expect(isDismissed({ ...key, uid: 'u2' })).toBe(false);
  });

  it('다시 보기를 누르면 되살아난다', () => {
    dismiss(key);
    clearDismiss(key);
    debugReset();
    expect(isDismissed(key)).toBe(false);
  });
});
