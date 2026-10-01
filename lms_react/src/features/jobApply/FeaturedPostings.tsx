import { useEffect, useState, type CSSProperties } from 'react';

import { http } from '../../data/http';
import { Button } from '../../ui/components';

/**
 * 공고 맞춤 지원 첫 화면 — 대기업 · 인기 기업 · 외국계 공고 카드.
 *
 * 서버(`/featured-postings`, lms_api/lms/featured_postings.py)가 회사마다 한 장씩 준다. 사람인 · 잡코리아에
 * 함께 올라온 공고는 서버가 한 공고로 합친다. 「진행 중」은 마감 임박순, 「지난 공채」는 최근 마감순이다.
 * 카드를 누르면 그 공고로 2단계(요건 확인)를 연다 — 코치 대화에서 고른 공고와 같은 길(?job=…).
 * 로고 · 홈페이지 지원 여부는 수집되어 있을 때만 온다. 없으면 회사명 첫 글자 · 「공채」만 보인다.
 */

type Tier = '인기 기업' | '대기업' | '외국계';
type View = 'live' | 'past';

export interface FeaturedPosting {
  job_id: string;
  company: string;
  title: string;
  tier: Tier;
  /** YYYY-MM-DD. 상시채용이면 null. 지난 공채면 마지막 마감일 */
  deadline: string | null;
  /** 「2026 하반기」 · 「수시」 */
  season: string;
  career_type: string;
  /** 이 회사(지난 공채면 이 회사 · 시즌)에서 조건에 맞는 공고 수 */
  posting_count: number;
  skills: string[];
  open_hiring: boolean;
  /** 회사 채용 사이트에서 지원하는 공고인가. 모르면 null */
  homepage: boolean | null;
  logo_url: string | null;
  closed: boolean;
}

interface FeaturedPage {
  items: FeaturedPosting[];
  total: number;
  counts: Record<Tier, number>;
}

const TIERS: Tier[] = ['인기 기업', '대기업', '외국계'];
const PAGE = 12;

const VIEWS: { id: View; label: string; hint: string }[] = [
  { id: 'live', label: '진행 중', hint: '신입 지원 가능 · 마감 임박순' },
  { id: 'past', label: '지난 공채', hint: '최근 1년 · 최근 마감순 · 다음 공채 준비용' },
];

/** 카드 오른쪽 위 마감 표시. 오늘 · 이틀 안은 색으로 알린다 */
export function ddayOf(
  deadline: string | null,
  today: Date,
  closed = false,
): { label: string; tone: 'today' | 'soon' | 'later' | 'rolling' | 'closed' } {
  if (deadline === null) return { label: '상시', tone: 'rolling' };
  if (closed) return { label: `${Number(deadline.slice(5, 7))}/${Number(deadline.slice(8, 10))} 마감`, tone: 'closed' };
  const start = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const [y, m, d] = deadline.split('-').map(Number);
  const days = Math.round((Date.UTC(y, m - 1, d) - start) / 86_400_000);
  if (days <= 0) return { label: '오늘마감', tone: 'today' };
  return { label: `D-${days}`, tone: days <= 2 ? 'soon' : 'later' };
}

/** 회사명으로 정한 색 — 같은 회사는 늘 같은 색 */
function hueOf(name: string): number {
  let h = 0;
  for (const ch of name) h = (h * 31 + (ch.codePointAt(0) ?? 0)) % 360;
  return h;
}

function CompanyMark({ posting }: { posting: FeaturedPosting }) {
  const [broken, setBroken] = useState(false);
  if (posting.logo_url && !broken) {
    return (
      <span className="featured-card__logo">
        <img src={posting.logo_url} alt={`${posting.company} 로고`} loading="lazy" onError={() => setBroken(true)} />
      </span>
    );
  }
  return (
    <span className="featured-card__mono" style={{ '--h': hueOf(posting.company) } as CSSProperties} aria-hidden="true">
      {posting.company.slice(0, 1)}
    </span>
  );
}

export function FeaturedPostings({ onPick, busy = false }: { onPick(jobId: string): void; busy?: boolean }) {
  const [view, setView] = useState<View>('live');
  const [tier, setTier] = useState<Tier | ''>('');
  const [page, setPage] = useState<FeaturedPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(false);
    setPage(null);
    http
      .get<FeaturedPage>('/featured-postings', { params: { view, tier, offset: 0, limit: PAGE } })
      .then(({ data }) => alive && setPage(data))
      .catch(() => alive && setError(true))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [view, tier, reload]);

  const more = async () => {
    if (page === null || loading) return;
    setLoading(true);
    try {
      const { data } = await http.get<FeaturedPage>('/featured-postings', {
        params: { view, tier, offset: page.items.length, limit: PAGE },
      });
      setPage({ ...data, items: [...page.items, ...data.items] });
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  const allCount = page === null ? null : TIERS.reduce((sum, t) => sum + (page.counts[t] ?? 0), 0);
  const today = new Date();
  const hint = VIEWS.find((v) => v.id === view)?.hint ?? '';

  return (
    <section className="featured" aria-labelledby="featured-title">
      <div className="featured__head">
        <div className="featured__title">
          <h2 id="featured-title">
            주요 기업 채용
            <small>{hint}</small>
          </h2>
          <div className="featured__views" role="tablist" aria-label="공채 상태">
            {VIEWS.map((v) => (
              <button
                key={v.id}
                type="button"
                role="tab"
                aria-selected={view === v.id}
                onClick={() => {
                  setView(v.id);
                  setTier('');
                }}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>
        <div className="featured__chips" role="group" aria-label="기업 구분">
          {(['', ...TIERS] as const).map((t) => {
            const count = page === null || tier !== '' ? null : t === '' ? allCount : page.counts[t];
            return (
              <button key={t || 'all'} type="button" className="featured__chip" aria-pressed={tier === t} onClick={() => setTier(t)}>
                {t || '전체'}
                {count !== null && <span>{count}</span>}
              </button>
            );
          })}
        </div>
      </div>

      {error && page === null ? (
        <div className="apply-error-row">
          <p className="apply-error">공고를 불러오지 못했어요.</p>
          <Button variant="text" size="sm" onClick={() => setReload((n) => n + 1)}>
            다시 시도
          </Button>
        </div>
      ) : page !== null && page.items.length === 0 ? (
        <p className="hint">지금 조건에 맞는 공고가 없어요. 링크를 붙여 넣거나 코치에게 물어 찾아 주세요.</p>
      ) : (
        <ul className="featured__grid" aria-busy={loading}>
          {page === null
            ? Array.from({ length: 8 }, (_, i) => <li key={i} className="featured-card featured-card--skeleton" aria-hidden="true" />)
            : page.items.map((p) => {
                const due = ddayOf(p.deadline, today, p.closed);
                return (
                  <li key={p.job_id}>
                    <button
                      type="button"
                      className={`featured-card${p.closed ? ' is-closed' : ''}`}
                      disabled={busy}
                      onClick={() => onPick(p.job_id)}
                    >
                      <span className="featured-card__top">
                        <CompanyMark posting={p} />
                        <span className={`featured-card__due featured-card__due--${due.tone}`}>{due.label}</span>
                      </span>
                      <span className="featured-card__badges">
                        <span className={`featured-card__badge${p.tier === '인기 기업' ? ' is-accent' : ''}`}>{p.tier}</span>
                        {p.open_hiring ? (
                          <span className="featured-card__badge">{p.homepage ? '공채 · 홈페이지 지원' : '공채'}</span>
                        ) : (
                          <>
                            <span className="featured-card__badge">{p.career_type === 'ENTRY' ? '신입' : '경력무관'}</span>
                            {p.homepage && <span className="featured-card__badge">홈페이지 지원</span>}
                          </>
                        )}
                        {p.posting_count > 1 && <span className="featured-card__badge">공고 {p.posting_count}건</span>}
                      </span>
                      <strong className="featured-card__company">
                        {p.company}
                        {p.season !== '' && <span className="featured-card__season">{p.season}</span>}
                      </strong>
                      <span className="featured-card__title">{p.title}</span>
                      {p.skills.length > 0 && <span className="featured-card__skills">{p.skills.map((s) => `#${s}`).join(' ')}</span>}
                    </button>
                  </li>
                );
              })}
        </ul>
      )}

      {page !== null && page.items.length < page.total && (
        <div className="featured__more">
          <Button variant="outline" onClick={() => void more()} disabled={loading}>
            {loading ? '불러오는 중…' : `더 보기 (${page.total - page.items.length})`}
          </Button>
        </div>
      )}
      {error && page !== null && <p className="apply-error">더 불러오지 못했어요. 다시 눌러 주세요.</p>}
    </section>
  );
}
