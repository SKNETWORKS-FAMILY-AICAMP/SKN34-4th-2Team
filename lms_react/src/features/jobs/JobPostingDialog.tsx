import { useEffect } from 'react';

import { Icon } from '../../ui/Icon';
import { JobPostingView, jobPostingPath } from './JobPostingScreen';

/**
 * 공고 원문 창 — 추천 카드에서 누르면 첨삭 창처럼 화면 위에 뜬다.
 *
 * 보던 이력서 · 추천 목록 위에 겹쳐 열고, 닫으면 그 자리로 돌아온다. 다른 공고와 나란히 두고
 * 보고 싶으면 머리줄의 「새 탭으로 열기」로 같은 원문을 브라우저 탭에 연다.
 */
export function JobPostingDialog({ jobId, onClose }: { jobId: string; onClose(): void }) {
  // Esc 로 닫는다. 창이 떠 있는 동안 뒤 화면이 스크롤되지 않게 한다
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
    };
  }, [onClose]);

  return (
    <div className="posting-layer" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="posting-window" role="dialog" aria-modal="true" aria-label="공고 원문">
        <header className="posting-window__head">
          <Icon name="description" size={20} className="posting-window__icon" />
          <strong>공고 원문</strong>
          <span className="spacer" />
          <a className="btn btn--text btn--sm" href={jobPostingPath(jobId)} target="_blank" rel="noreferrer">
            <Icon name="open_in_new" size={16} />
            새 탭으로 열기
          </a>
          <button type="button" className="icon-btn" aria-label="닫기" title="닫기" onClick={onClose}>
            <Icon name="close" size={22} />
          </button>
        </header>
        <div className="posting-window__body">
          <JobPostingView jobId={jobId} />
        </div>
      </div>
    </div>
  );
}
