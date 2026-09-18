import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

import {
  HOLE_PADDING,
  HOLE_RADIUS,
  cardWidth,
  inflate,
  overlapsViewport,
  tooltipOffset,
  type Offset,
} from './positioning';
import { elementOf, rectOf, sameRect, type TargetRect } from './targetRegistry';
import type { TourStep } from './types';

const MAX_RETRIES = 12;

interface Props {
  step: TourStep;
  stepIndex: number;
  totalSteps: number;
  onNext(): void;
  /** 첫 단계에서는 null. 그때는 되돌아갈 곳이 없다. */
  onPrevious: (() => void) | null;
  onDismissForever(): void;
  onSkipMissing(): void;
}

/** 딤 + 하이라이트 구멍 + 설명 카드 */
export function TourOverlay({
  step,
  stepIndex,
  totalSteps,
  onNext,
  onPrevious,
  onDismissForever,
  onSkipMissing,
}: Props) {
  const [hole, setHole] = useState<TargetRect | null>(null);
  const [resolvedStepId, setResolvedStepId] = useState<string | null>(null);
  // 첫 자리를 잡기 전에는 카드를 내보내지 않는다. 자리를 모르는 채로 그리면
  // 화면 한가운데에 떴다가 제자리로 튄다.
  const [settled, setSettled] = useState(false);
  const [cardOffset, setCardOffset] = useState<Offset | null>(null);

  const cardRef = useRef<HTMLDivElement | null>(null);
  const measuringRef = useRef<TargetRect | null>(null);
  const retriesRef = useRef(0);
  const ensuredVisibleRef = useRef(false);
  const frameRef = useRef<number | null>(null);

  const resolve = useCallback(() => {
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const rect = rectOf(step.targetId);

    if (rect !== null) {
      // 자리가 멎을 때까지 기다린다. 단계가 바뀌면 화면이 함께 바뀌고
      // 목록이 다시 그려지며 메뉴가 밀린다. 멎기 전에 손대면 그때마다 따라간다.
      if (
        !sameRect(measuringRef.current, rect) &&
        retriesRef.current < MAX_RETRIES - 1
      ) {
        measuringRef.current = rect;
        retriesRef.current += 1;
        schedule();
        return;
      }

      // 스크롤 영역 밖으로 가려진 만큼만 드러낸다. 이미 보이면 그대로 둔다.
      if (!ensuredVisibleRef.current && retriesRef.current < MAX_RETRIES - 1) {
        ensuredVisibleRef.current = true;
        if (!overlapsViewport(rect, viewport)) {
          elementOf(step.targetId)?.scrollIntoView({
            block: 'nearest',
            inline: 'nearest',
          });
        }
        measuringRef.current = null;
        retriesRef.current += 1;
        schedule();
        return;
      }

      if (overlapsViewport(rect, viewport)) {
        setResolvedStepId(step.id);
        setHole(inflate(rect, HOLE_PADDING));
        setSettled(true);
        return;
      }
    }

    retriesRef.current += 1;
    if (retriesRef.current >= MAX_RETRIES) {
      if (step.skippableIfMissing === true) {
        onSkipMissing();
        return;
      }
      // 타깃을 못 찾아도 설명은 보여 준다. 구멍 없이 화면 한가운데.
      setResolvedStepId(step.id);
      setHole(null);
      setSettled(true);
      return;
    }
    schedule();
    // schedule은 아래에서 정의된 안정적인 참조라 의존성에 넣지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, onSkipMissing]);

  const resolveRef = useRef(resolve);
  resolveRef.current = resolve;

  function schedule(): void {
    if (frameRef.current !== null) return;
    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = null;
      resolveRef.current();
    });
  }

  // 단계가 바뀌면 처음부터 다시 잰다. 카드 위치는 유지하되 이전 단계의 강조는
  // 새 위치가 확정될 때까지 숨긴다. 스크롤된 목록 위에 이전 좌표의 구멍을
  // 남기면 다른 메뉴를 비춘다.
  useLayoutEffect(() => {
    retriesRef.current = 0;
    measuringRef.current = null;
    ensuredVisibleRef.current = false;
    schedule();
    return () => {
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    };
  }, [step.id]);

  // 창 크기나 스크롤이 바뀌면 자리를 다시 잰다.
  useEffect(() => {
    const remeasure = () => {
      retriesRef.current = MAX_RETRIES - 2;
      measuringRef.current = null;
      schedule();
    };
    window.addEventListener('resize', remeasure);
    window.addEventListener('scroll', remeasure, true);
    return () => {
      window.removeEventListener('resize', remeasure);
      window.removeEventListener('scroll', remeasure, true);
    };
  }, []);

  // 카드 크기를 잰 뒤 한 번에 배치한다.
  useLayoutEffect(() => {
    const card = cardRef.current;
    if (card === null || !settled) return;
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const size = { width: card.offsetWidth, height: card.offsetHeight };
    const spot = resolvedStepId === step.id ? hole : null;
    setCardOffset(tooltipOffset(viewport, size, spot));
  }, [hole, resolvedStepId, settled, step.id, stepIndex]);

  const spot = settled && resolvedStepId === step.id ? hole : null;
  const isLastStep = stepIndex >= totalSteps - 1;
  const width = cardWidth(
    typeof window === 'undefined' ? 1024 : window.innerWidth,
  );

  return (
    <div className="tour-layer" data-testid="tour-overlay">
      {/* 구멍 하나로 딤을 뚫는다. 바깥은 커다란 box-shadow가 덮는다. */}
      {spot === null ? (
        <div className="tour-scrim tour-scrim--full" />
      ) : (
        <div
          className="tour-scrim tour-hole"
          style={{
            left: spot.left,
            top: spot.top,
            width: spot.width,
            height: spot.height,
            borderRadius: HOLE_RADIUS,
          }}
        />
      )}

      <div
        ref={cardRef}
        className="tour-card"
        style={{
          width,
          left: cardOffset?.left ?? 0,
          top: cardOffset?.top ?? 0,
          opacity: settled && cardOffset !== null ? 1 : 0,
        }}
        role="dialog"
        aria-label={step.title}
      >
        <div className="tour-card__head">
          <span className="tour-card__title">{step.title}</span>
          <span className="tour-card__count">
            {stepIndex + 1} / {totalSteps}
          </span>
        </div>
        <p className="tour-card__body">{step.body}</p>
        <div className="tour-card__actions">
          <button type="button" className="btn btn--text" onClick={onDismissForever}>
            다시 보지 않기
          </button>
          <span className="tour-card__spacer" />
          {onPrevious !== null && (
            <button type="button" className="btn btn--text" onClick={onPrevious}>
              이전
            </button>
          )}
          <button type="button" className="btn btn--filled" onClick={onNext}>
            {isLastStep ? '완료' : '다음'}
          </button>
        </div>
      </div>
    </div>
  );
}
