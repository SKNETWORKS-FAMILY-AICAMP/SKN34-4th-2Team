import { useEffect, useRef, type ReactNode } from 'react';

import { TourOverlay } from './TourOverlay';
import { isAtRoute } from './tourState';
import { useTour } from './useTour';
import type { TourDefinition } from './types';

interface Props {
  tour: TourDefinition;
  uid: string;
  location: string;
  navigate(path: string): void;
  children: ReactNode;
}

/**
 * 역할 공통 온보딩 호스트 — 셸 위에 오버레이 + 스텝별 라우트 이동
 */
export function TourHost({ tour, uid, location, navigate, children }: Props) {
  const api = useTour();
  const bootstrappedUidRef = useRef<string | null>(null);
  const navigatingForStepIdRef = useRef<string | null>(null);

  // 로그인한 사용자마다 한 번만 띄운다.
  useEffect(() => {
    if (uid === '' || bootstrappedUidRef.current === uid) return;
    bootstrappedUidRef.current = uid;
    api.maybeStart(tour, uid);
  }, [api, tour, uid]);

  const active = api.state !== null && api.active && api.state.tourId === tour.tourId;
  const step = active ? api.step : null;

  // 단계가 원하는 화면으로 데려다 놓는다. 이미 그 화면이면 가만히 둔다.
  useEffect(() => {
    if (step?.route === undefined || step.route === null) return;
    if (isAtRoute(location, step.route, tour.rootRoutes)) {
      navigatingForStepIdRef.current = null;
      return;
    }
    if (navigatingForStepIdRef.current === step.id) return;
    navigatingForStepIdRef.current = step.id;
    navigate(step.route);
  }, [step, location, navigate, tour.rootRoutes]);

  const handleNext = () => {
    if (api.state === null) return;
    if (api.isLastStep) {
      // 투어는 화면을 옮겨 다니므로 마지막 단계의 화면에서 끝난다. 첫 단계의
      // 화면으로 데려다 놓아야 둘러보기 전에 있던 자리로 돌아온 것이 된다.
      const home = api.state.steps[0]?.route;
      api.dismissForever();
      if (home !== undefined) navigate(home);
      return;
    }
    api.next();
  };

  const handleSkipMissing = () => {
    if (api.isLastStep) {
      api.dismissForever();
      return;
    }
    api.next();
  };

  return (
    <>
      {children}
      {step !== null && (
        <TourOverlay
          step={step}
          stepIndex={api.index}
          totalSteps={api.total}
          onNext={handleNext}
          onPrevious={api.index > 0 ? api.previous : null}
          onDismissForever={api.dismissForever}
          onSkipMissing={handleSkipMissing}
        />
      )}
    </>
  );
}
