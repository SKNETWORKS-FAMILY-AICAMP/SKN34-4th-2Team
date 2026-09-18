import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from 'react';

import { clearDismiss, dismiss, isDismissed } from './dismissStore';
import {
  currentStep,
  isLast,
  tourReducer,
  type TourState,
} from './tourState';
import type { TourDefinition, TourStep } from './types';

export interface TourApi {
  state: TourState | null;
  step: TourStep | null;
  active: boolean;
  total: number;
  index: number;
  isLastStep: boolean;
  maybeStart(tour: TourDefinition, uid: string): void;
  restart(tour: TourDefinition, uid: string): void;
  goToIndex(index: number): void;
  next(): void;
  previous(): void;
  dismissForever(): void;
}

const TourContext = createContext<TourApi | null>(null);

export function TourProvider({ children }: { children: ReactNode }) {
  const [state, send] = useReducer(tourReducer, null);

  const maybeStart = useCallback(
    (tour: TourDefinition, uid: string) => {
      if (state?.active === true) return;
      if (uid === '' || tour.steps.length === 0) return;
      if (isDismissed({ tourId: tour.tourId, version: tour.version, uid })) {
        return;
      }
      send({
        type: 'start',
        state: {
          tourId: tour.tourId,
          version: tour.version,
          uid,
          steps: tour.steps,
          index: 0,
          active: true,
        },
      });
    },
    [state?.active],
  );

  const restart = useCallback((tour: TourDefinition, uid: string) => {
    clearDismiss({ tourId: tour.tourId, version: tour.version, uid });
    send({
      type: 'start',
      state: {
        tourId: tour.tourId,
        version: tour.version,
        uid,
        steps: tour.steps,
        index: 0,
        active: true,
      },
    });
  }, []);

  const dismissForever = useCallback(() => {
    if (state === null) return;
    dismiss({ tourId: state.tourId, version: state.version, uid: state.uid });
    send({ type: 'end' });
  }, [state]);

  const api = useMemo<TourApi>(
    () => ({
      state,
      step: currentStep(state),
      active: state?.active === true,
      total: state?.steps.length ?? 0,
      index: state?.index ?? 0,
      isLastStep: state !== null && isLast(state),
      maybeStart,
      restart,
      goToIndex: (index: number) => send({ type: 'goToIndex', index }),
      next: () => send({ type: 'next' }),
      previous: () => send({ type: 'previous' }),
      dismissForever,
    }),
    [state, maybeStart, restart, dismissForever],
  );

  return <TourContext.Provider value={api}>{children}</TourContext.Provider>;
}

export function useTour(): TourApi {
  const api = useContext(TourContext);
  if (api === null) throw new Error('TourProvider 밖에서 useTour를 불렀다');
  return api;
}
