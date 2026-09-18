import type { TourStep } from './types';

/**
 * 투어 상태와 전이 — Flutter의 OnboardingTourNotifier를 순수 함수로 옮겼다.
 * React에 기대지 않으므로 테스트에서 그대로 부를 수 있다.
 */
export interface TourState {
  readonly tourId: string;
  readonly version: number;
  readonly uid: string;
  readonly steps: readonly TourStep[];
  readonly index: number;
  readonly active: boolean;
}

export function currentStep(state: TourState | null): TourStep | null {
  if (state === null || !state.active) return null;
  if (state.index < 0 || state.index >= state.steps.length) return null;
  return state.steps[state.index];
}

export function isLast(state: TourState): boolean {
  return state.index >= state.steps.length - 1;
}

export type TourAction =
  | { type: 'start'; state: TourState }
  | { type: 'goToIndex'; index: number }
  | { type: 'next' }
  | { type: 'previous' }
  | { type: 'end' };

export function tourReducer(
  state: TourState | null,
  action: TourAction,
): TourState | null {
  switch (action.type) {
    case 'start':
      return action.state;
    case 'end':
      return null;
    case 'goToIndex': {
      if (state === null || !state.active) return state;
      if (action.index < 0 || action.index >= state.steps.length) return state;
      return { ...state, index: action.index };
    }
    case 'next': {
      if (state === null || !state.active || isLast(state)) return state;
      return { ...state, index: state.index + 1 };
    }
    case 'previous': {
      if (state === null || !state.active || state.index <= 0) return state;
      return { ...state, index: state.index - 1 };
    }
    default:
      return state;
  }
}

/**
 * 현재 위치가 스텝이 원하는 라우트인가.
 *
 * rootRoutes에 든 경로는 exact match만 인정한다. `/admin`이 `/admin/students`를
 * 품어 버리면 관리자 첫 스텝이 어느 하위 화면에서든 만족돼 버린다.
 */
export function isAtRoute(
  location: string,
  route: string,
  rootRoutes: readonly string[],
): boolean {
  if (route === '/') return location === '/' || location === '';
  if (rootRoutes.includes(route)) return location === route;
  return location === route || location.startsWith(`${route}/`);
}
