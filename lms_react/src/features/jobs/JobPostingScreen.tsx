import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { http } from '../../data/http';
import { Icon } from '../../ui/Icon';
import { closedReason } from './postingStatus';
import { formatPostingText, isBrokenBody, type PostingBlock, type PostingFormRow, type PostingTextBlock } from './postingText';
import './jobPosting.css';

/** 공고 원문 화면 주소. 추천 카드가 새 탭으로 연다 */
export const jobPostingPath = (jobId: string) => `/jobs/${encodeURIComponent(jobId)}`;

/**
 * 공고 원문 — 추천 카드에서 새 탭으로 연다.
 *
 * 채용 사이트로 바로 보내지 않는다. 첨삭하던 이력서 화면을 잃지 않고, 마감돼 사이트에서 내려간
 * 공고도 수집해 둔 원문으로 읽을 수 있다. 지원은 「원문 링크 열기」로 사이트에서 한다.
 * 새 탭은 로그인 정보를 넘겨받지 못하므로 로그인 없이 보이는 화면이다(공개된 공고).
 */
export interface Posting {
  job_id: string;
  source: string;
  source_url: string;
  company: string;
  title: string;
  description: string;
  region: string;
  career_type: string;
  min_career_years: number | null;
  employment_type: string;
  education: string;
  deadline: string | null;
  status: string;
  required_skills: string[];
  preferred_skills: string[];
  body_is_image: boolean;
  /** 같은 공고가 여러 사이트에 올라온 경우 사이트마다 하나. 지금 공고가 맨 앞 */
  links: { job_id: string; source: string; source_url: string; status: string }[];
}

const SOURCE_LABEL: Record<string, string> = { SARAMIN_POC: '사람인', JOBKOREA_POC: '잡코리아' };

/** 수집기의 경력 구분(ENTRY · EXPERIENCED · ANY)을 화면 말로 */
export function careerLabel(careerType: string, minYears: number | null): string {
  if (careerType === 'ENTRY') return '신입';
  if (careerType === 'EXPERIENCED') return minYears ? `경력 ${minYears}년 이상` : '경력';
  return '경력무관';
}

/** 마감은 날짜까지만. 시각 · 시간대는 지원 여부를 정하는 데 쓰이지 않는다 */
const dateOnly = (value: string | null) => (value === null ? '' : (/^\d{4}-\d{2}-\d{2}/.exec(value)?.[0] ?? value));

/** 새 탭으로 연 공고 원문 — 주소의 공고를 보여 준다 */
export function JobPostingScreen() {
  const { jobId = '' } = useParams<{ jobId: string }>();
  return <JobPostingView jobId={jobId} asPage />;
}

/**
 * 공고 원문 본문. 새 탭 화면과 추천 카드에서 여는 창이 함께 쓴다.
 * `asPage` 면 브라우저 탭 이름을 공고 제목으로 바꾼다.
 */
export function JobPostingView({ jobId, asPage = false }: { jobId: string; asPage?: boolean }) {
  const [posting, setPosting] = useState<Posting | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    setError(null);
    setPosting(null);
    http
      .get<Posting>(`/postings/${encodeURIComponent(jobId)}`)
      .then(({ data }) => alive && setPosting(data))
      .catch((err: unknown) => {
        if (!alive) return;
        const status = (err as { response?: { status?: number } }).response?.status;
        setError(status === 404 ? '공고를 찾을 수 없어요. 수집 목록에서 빠진 공고일 수 있어요.' : '공고를 불러오지 못했어요.');
      });
    return () => {
      alive = false;
    };
  }, [jobId, attempt]);

  // 탭 이름으로 어느 공고인지 알 수 있게
  useEffect(() => {
    if (asPage && posting !== null) document.title = `${posting.title} · ${posting.company}`;
  }, [asPage, posting]);

  if (error !== null) {
    return (
      <main className="posting posting--state">
        <Icon name="error" size={32} />
        <p>{error}</p>
        <button type="button" className="btn btn--outline btn--md" onClick={() => setAttempt((n) => n + 1)}>
          다시 시도
        </button>
      </main>
    );
  }

  if (posting === null) {
    return (
      <main className="posting posting--state" aria-busy="true">
        <p className="hint">공고를 불러오고 있어요…</p>
      </main>
    );
  }

  const source = SOURCE_LABEL[posting.source] ?? posting.source;
  const closed = posting.status !== 'OPEN';
  // 같은 공고가 사람인 · 잡코리아에 함께 있으면 사이트마다 버튼을 둔다. 지금 공고의 사이트가 앞
  const links = (posting.links ?? []).filter((l) => l.source_url.startsWith('http'));
  const sources = [...new Set(links.map((l) => SOURCE_LABEL[l.source] ?? l.source))];

  return (
    <main className="posting">
      <header className="posting__head">
        <div className="posting__heading">
          <span className="posting__source">{source}</span>
          <h1>{posting.title}</h1>
          <p>{[posting.company, posting.region].filter((v) => v !== '').join(' · ')}</p>
        </div>
        {links.length > 0 && (
          <div className="posting__links">
            {links.map((l, i) => (
              <a
                key={l.job_id}
                className={`btn btn--md ${i === 0 ? 'btn--filled' : 'btn--outline'}`}
                href={l.source_url}
                target="_blank"
                rel="noreferrer"
              >
                <Icon name="open_in_new" size={16} />
                {links.length === 1 ? '원문 링크 열기' : `${SOURCE_LABEL[l.source] ?? l.source}에서 열기`}
                {l.status !== 'OPEN' && <span className="posting__link-closed">마감</span>}
              </a>
            ))}
          </div>
        )}
      </header>

      {closed && (
        <p className="posting__closed">
          <Icon name="info" size={16} />
          {closedReason(posting.status, posting.deadline)} 수집해 둔 원문을 보여 드려요.
        </p>
      )}

      <dl className="posting__facts">
        <div>
          <dt>경력</dt>
          <dd>{careerLabel(posting.career_type, posting.min_career_years)}</dd>
        </div>
        <div>
          <dt>고용형태</dt>
          <dd>{posting.employment_type || '미기재'}</dd>
        </div>
        <div>
          <dt>학력</dt>
          <dd>{posting.education || '미기재'}</dd>
        </div>
        <div>
          <dt>마감</dt>
          <dd>{dateOnly(posting.deadline) || '미기재'}</dd>
        </div>
      </dl>

      {(posting.required_skills.length > 0 || posting.preferred_skills.length > 0) && (
        <section className="posting__skills">
          {posting.required_skills.length > 0 && (
            <div>
              <span className="posting__label">자격 요건</span>
              <div className="posting__tags">
                {posting.required_skills.map((s) => (
                  <span key={s} className="posting__tag is-required">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
          {posting.preferred_skills.length > 0 && (
            <div>
              <span className="posting__label">우대 사항</span>
              <div className="posting__tags">
                {posting.preferred_skills.map((s) => (
                  <span key={s} className="posting__tag">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {posting.body_is_image || posting.description.trim() === '' ? (
        <p className="posting__body posting__body--empty">
          상세 내용이 이미지로만 올라온 공고라 원문 글을 모으지 못했어요. 원문 링크에서 확인해 주세요.
        </p>
      ) : isBrokenBody(posting.description) ? (
        <p className="posting__body posting__body--empty">
          수집할 때 공고 대신 사이트 안내 페이지를 받아 와서 원문 글이 없어요. 원문 링크에서 확인해 주세요.
        </p>
      ) : (
        <PostingBody text={posting.description} />
      )}

      <footer className="posting__foot">
        {(sources.length > 0 ? sources : [source]).join(' · ')}에서 수집한 원문입니다. 지원은 위의 원문 링크에서 진행해 주세요.
      </footer>
    </main>
  );
}

/** 사람인 간편 양식 공고의 표 — 칸 이름 · 값. 직종 분류는 대분류마다 한 줄에 소분류를 태그로 늘어놓는다 */
function PostingForm({ rows }: { rows: PostingFormRow[] }) {
  return (
    <dl className="posting__form">
      {rows.map((row, i) => (
        <div key={i} className="posting__form-row">
          <dt>{row.label}</dt>
          {'groups' in row ? (
            <dd>
              {row.groups.map((group) => (
                <div key={group.name} className="posting__cats">
                  <span className="posting__cat-name">{group.name}</span>
                  <span className="posting__cat-items">
                    {group.items.map((item) => (
                      <span key={item} className="posting__cat">
                        {item}
                      </span>
                    ))}
                  </span>
                </div>
              ))}
            </dd>
          ) : (
            <dd>{row.value}</dd>
          )}
        </div>
      ))}
    </dl>
  );
}

/**
 * 이미지로 된 부분 — 사람인이 공고 이미지에서 글자만 뽑아 둔 것. 포스터 배치가 사라져 줄 순서가 흐트러지므로
 * 원래 이미지는 링크로 연다. 이미지를 이 화면에 띄우지는 않는다(사람인 약관의 무단 복제 · 재제공 금지 — 링크는 원문 링크와 같다).
 * 본문의 곁가지일 때는 글을 접어 두고, 본문 대부분이 이미지면 펼쳐 둔다(postingText.ts 가 영어 번역 줄 · 반복 줄을 뺀다)
 */
function ImageText({ urls, lines, open }: { urls: string[]; lines: string[]; open: boolean }) {
  if (lines.length === 0 && urls.length === 0) return null;
  return (
    <section className="posting__image">
      <div className="posting__image-head">
        <span className="posting__image-title">
          <Icon name="image" size={16} />
          이미지로 된 부분
        </span>
        {urls.map((url, i) => (
          <a key={url} className="btn btn--outline btn--sm" href={url} target="_blank" rel="noreferrer">
            <Icon name="open_in_new" size={14} />
            {urls.length === 1 ? '원본 이미지 보기' : `원본 이미지 ${i + 1}`}
          </a>
        ))}
      </div>
      {lines.length > 0 && (
        <details open={open}>
          <summary>
            이미지에서 읽은 글 <span>{lines.length}줄</span>
          </summary>
          <p className="posting__image-note">
            이미지에서 글자만 뽑아서 줄 순서와 배치가 흐트러져 있을 수 있어요. 정확한 내용은 원본 이미지로 확인해 주세요.
          </p>
          {lines.map((line, i) => (
            <p key={i}>{line}</p>
          ))}
        </details>
      )}
    </section>
  );
}

/** 원문을 소제목 · 목록 · 문단으로 나눠 그린다. 이어지는 목록 항목은 한 목록으로 묶는다 */
function PostingBody({ text }: { text: string }) {
  const blocks = formatPostingText(text);
  // 본문 대부분이 이미지인 공고(글은 제목 한 줄뿐)는 이미지 글을 펼쳐 둔다. 접으면 읽을 게 없다
  const size = (lines: string[]) => lines.join('').length;
  const imageSize = size(blocks.flatMap((b) => (b.type === 'image' ? b.lines : [])));
  const textSize = size(blocks.flatMap((b) => ('text' in b ? [b.text] : [])));
  const imageOpen = imageSize > textSize;
  const groups: (PostingBlock | PostingTextBlock[])[] = [];
  for (const block of blocks) {
    const last = groups[groups.length - 1];
    if (block.type === 'item' && Array.isArray(last)) last.push(block);
    else groups.push(block.type === 'item' ? [block] : block);
  }
  return (
    <article className="posting__body">
      {groups.map((group, i) =>
        Array.isArray(group) ? (
          <ul key={i}>
            {group.map((item, j) => (
              <li key={j}>{item.text}</li>
            ))}
          </ul>
        ) : group.type === 'form' ? (
          <PostingForm key={i} rows={group.rows} />
        ) : group.type === 'image' ? (
          <ImageText key={i} urls={group.urls} lines={group.lines} open={imageOpen} />
        ) : group.type === 'heading' ? (
          <h2 key={i}>{group.text}</h2>
        ) : group.type === 'role' ? (
          <h3 key={i} className="posting__role">
            {group.text}
          </h3>
        ) : group.type === 'sub' ? (
          <h3 key={i}>{group.text}</h3>
        ) : (
          <p key={i}>{group.text}</p>
        ),
      )}
    </article>
  );
}
