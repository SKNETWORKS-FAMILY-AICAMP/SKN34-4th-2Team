import { Icon } from '../../ui/Icon';

/** 학습실 · 대시보드가 같이 쓰는 YouTube 영상 카드 */

export function youtubeThumb(videoId?: string): string | undefined {
  return videoId ? `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg` : undefined;
}

/** 영상 카드 한 장 — 썸네일 · 제목 · 채널/주제 */
export function VideoCard({
  href,
  title,
  thumb,
  meta,
  chips,
}: {
  href: string;
  title: string;
  thumb?: string;
  meta: string[];
  chips?: { label: string; on?: boolean }[];
}) {
  return (
    <a className="study-video" href={href} target="_blank" rel="noreferrer">
      <span className="study-video__thumb">
        {thumb !== undefined && <img src={thumb} alt="" loading="lazy" />}
        <Icon
          name="play_circle"
          size={36}
          className={thumb !== undefined ? 'study-video__play' : undefined}
        />
      </span>
      <strong className="study-video__title">{title}</strong>
      {meta.length > 0 && (
        <span className="study-video__meta">
          {meta.map((m, i) => (
            <span key={m}>{i > 0 ? `· ${m}` : m}</span>
          ))}
        </span>
      )}
      {chips !== undefined && chips.length > 0 && (
        <span className="study-video__tags">
          {chips.map((c) => (
            <span key={c.label} className={`chip${c.on ? ' chip--on' : ''}`}>
              {c.label}
            </span>
          ))}
        </span>
      )}
    </a>
  );
}
