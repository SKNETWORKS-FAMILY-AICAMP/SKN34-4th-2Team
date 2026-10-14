import { useState } from 'react';

import { http } from '../../data/http';
import { Icon } from '../../ui/Icon';
import { Button } from '../../ui/components';

/**
 * 「회사 채용 사이트 열기」 — 홈페이지 지원 공고면 회사 채용 사이트로 바로 간다.
 *
 * 대기업 공채는 사람인 · 잡코리아 공고가 요약이고, 직무 설명과 자기소개서 문항은 회사 채용 사이트에 있다.
 * 서버(`/postings/{id}/apply-link`, lms_api/lms/apply_link.py)가 그 주소를 찾는다. 같은 공고의 잡코리아 사본이
 * 있으면 공고 페이지로 바로 가고, 사람인뿐이면 채용 사이트 첫 화면일 때가 많다. 못 찾으면 공고 원문을 연다.
 *
 * 주소를 받는 데 1초쯤 걸린다. 받은 뒤에 새 탭을 열면 브라우저가 팝업으로 막으므로, 누르자마자 빈 탭을 열어 두고
 * 주소가 오면 그 탭을 옮긴다.
 */
export function ApplySiteButton({
  jobId,
  fallbackUrl,
  size = 'sm',
  onNote,
}: {
  jobId: string;
  /** 회사 사이트를 못 찾았을 때 열 사람인 · 잡코리아 공고 */
  fallbackUrl: string;
  size?: 'sm' | 'md';
  /**
   * 열고 난 뒤 알릴 말(첫 화면일 수 있음 · 원문을 열었음). 주면 부모가 알맞은 자리에 보여 준다 —
   * 버튼 밑에 붙이면 좁은 칸에서 여러 줄로 꺾여 옆 링크를 밀어낸다. 안 주면 버튼 밑에 둔다
   */
  onNote?(note: string): void;
}) {
  const [finding, setFinding] = useState(false);
  const [ownNote, setOwnNote] = useState('');
  const note = onNote === undefined ? ownNote : '';
  const setNote = onNote ?? setOwnNote;

  const go = (tab: Window | null, url: string) => {
    if (tab === null) {
      window.open(url, '_blank', 'noopener');
      return;
    }
    tab.opener = null;
    tab.location.href = url;
  };

  const open = async () => {
    const tab = window.open('', '_blank');
    setFinding(true);
    setNote('');
    try {
      const { data } = await http.get<{ url: string | null; precise: boolean }>(
        `/postings/${encodeURIComponent(jobId)}/apply-link`,
      );
      if (data.url) {
        go(tab, data.url);
        if (!data.precise) setNote('채용 사이트 첫 화면일 수 있어요. 진행 중인 공고에서 지원할 직무를 찾아 주세요.');
      } else {
        go(tab, fallbackUrl);
        setNote('회사 채용 사이트 주소를 찾지 못해 공고 원문을 열었어요. 거기서 「홈페이지 지원」을 눌러 주세요.');
      }
    } catch {
      go(tab, fallbackUrl);
      setNote('회사 채용 사이트를 찾지 못해 공고 원문을 열었어요.');
    } finally {
      setFinding(false);
    }
  };

  const button = (
    <Button size={size} className="apply-site" onClick={() => void open()} disabled={finding}>
      <Icon name="open_in_new" size={16} />
      {finding ? '채용 사이트 찾는 중…' : '회사 채용 사이트 열기'}
    </Button>
  );
  if (note === '') return button;
  return (
    <span className="apply-site-wrap">
      {button}
      <span className="hint">{note}</span>
    </span>
  );
}
