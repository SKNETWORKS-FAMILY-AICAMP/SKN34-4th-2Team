/** 온보딩 한 스텝 — 역할별 스텝 목록에서 재사용 */
export interface TourStep {
  readonly id: string;
  readonly title: string;
  readonly body: string;

  /** targetRegistry에 등록된 타깃 id */
  readonly targetId: string;

  /** 표시 전 이동할 라우트 (없으면 현재 위치 유지) */
  readonly route?: string;

  /** 타깃이 없으면 자동으로 다음 스텝으로 넘김 */
  readonly skippableIfMissing?: boolean;
}

export interface TourDefinition {
  readonly tourId: string;
  readonly version: number;
  readonly steps: readonly TourStep[];

  /** exact match만 허용할 루트 경로 (`/`, `/admin`, `/instructor`) */
  readonly rootRoutes: readonly string[];
}
