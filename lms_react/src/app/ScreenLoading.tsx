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
 * 화면 경계 — 화면 하나가 멈춰도 앱 전체(레일 · 상단 바)는 살린다.
 *
 * - 화면 청크를 못 받았을 때(네트워크가 끊겼거나, 새로 배포되어 옛 청크 이름이 사라졌을 때): 새로 고침하면 된다.
 * - 화면이 그리다 멈췄을 때(데이터 모양이 예상과 다를 때 등): 네트워크 탓이 아니므로 그렇게 말하지 않는다.
 *   원인은 개발자 도구 콘솔에 남긴다.
 */
const CHUNK_ERROR = /dynamically imported module|Importing a module script failed|Loading chunk|Failed to fetch/i;

export class ScreenErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error('[화면 오류]', error);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const chunk = CHUNK_ERROR.test(error.message);
    return (
      <div className="screen-loading screen-loading--failed" role="alert">
        <span className="screen-loading__text">
          {chunk
            ? '화면을 불러오지 못했어요. 네트워크를 확인하고 다시 시도해 주세요.'
            : '화면을 그리다 문제가 생겼어요. 새로 고침해도 같으면 알려 주세요.'}
        </span>
        {!chunk && <code className="screen-loading__detail">{error.message}</code>}
        <button type="button" className="btn btn--outline btn--sm" onClick={() => window.location.reload()}>
          다시 시도
        </button>
      </div>
    );
  }
}
