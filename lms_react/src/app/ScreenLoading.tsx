import { Component, type ReactNode } from 'react';

/**
 * 화면 청크를 받는 동안의 자리 표시. 셸(레일·상단 바)은 그대로 두고 본문 자리만 채운다.
 * 이용 안내 투어는 이 표시가 있는 동안 타깃 찾기를 미룬다(data-screen-loading).
 * 빠르게 받으면 깜빡이지 않도록 0.2초 뒤에 나타난다(CSS animation-delay).
 */
export function ScreenLoading() {
  return (
    <div className="screen-loading" data-screen-loading role="status" aria-live="polite">
      <span className="screen-loading__bar" />
      <span className="screen-loading__text">화면을 불러오는 중…</span>
    </div>
  );
}


/**
 * 화면 청크를 받지 못했을 때 — 네트워크가 끊겼거나, 새로 배포되어 옛 청크 이름이 사라졌을 때.
 * 앱 전체를 멈추지 않고 본문 자리에 「다시 시도」를 띄운다. 새로 고침하면 새 청크 이름을 받는다.
 */
export class ScreenErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="screen-loading screen-loading--failed" role="alert">
        <span className="screen-loading__text">화면을 불러오지 못했어요. 네트워크를 확인하고 다시 시도해 주세요.</span>
        <button type="button" className="btn btn--outline btn--sm" onClick={() => window.location.reload()}>
          다시 시도
        </button>
      </div>
    );
  }
}
