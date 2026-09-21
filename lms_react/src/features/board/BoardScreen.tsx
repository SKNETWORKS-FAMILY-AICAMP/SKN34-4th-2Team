import { useState } from 'react';

import {
  createPostComment,
  createPost,
  deletePostComment,
  deletePost,
  likePost,
  useNotices,
  usePostComments,
  usePosts,
} from '../../data/repository';
import type { Notice, Post } from '../../domain/types';
import { StudentTargets } from '../../tour/targets';
import { useTourTarget } from '../../tour/useTourTarget';
import {
  Avatar,
  Badge,
  Button,
  Card,
  EmptyState,
  Row,
  Spacer,
  TextArea,
} from '../../ui/components';
import { Icon } from '../../ui/Icon';
import { formatDateTime, formatRelative } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { NoticeDetailDialog } from './NoticeDetailDialog';

/**
 * 게시판 — features/hub/presentation/board_screen.dart (공지사항 / 소통 피드)
 *
 * 머리글이 없다. 화면 맨 위에 두 칸짜리 탭 줄이 가로로 꽉 차고, 공지사항 탭에만
 * 검색 줄이 붙는다. 숫자는 붙지 않는다.
 */
export function BoardScreen() {
  const [tab, setTab] = useState<'notices' | 'feed'>('notices');

  return (
    <div className="board-page">
      <div className="board-tabs">
        {(
          [
            ['notices', '공지사항'],
            ['feed', '소통 피드'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`board-tab${tab === id ? ' board-tab--on' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === 'notices' ? <NoticesTab /> : <FeedTab />}
    </div>
  );
}

function NoticesTab() {
  const notices = useNotices();
  const ref = useTourTarget(StudentTargets.boardNotices);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState<Notice | null>(null);

  const q = query.trim().toLowerCase();
  const matched = q === ''
    ? notices
    : notices.filter(
        (n) =>
          n.title.toLowerCase().includes(q) ||
          n.content.toLowerCase().includes(q) ||
          n.authorName.toLowerCase().includes(q),
      );

  const important = matched.filter((n) => n.isFavorite);
  const rest = matched.filter((n) => !n.isFavorite);

  return (
    <div className="board-body" ref={ref}>
      <div className="board-search-strip">
        <label className="board-search">
          <Icon name="search" size={20} />
          <input
            className="board-search__input"
            value={query}
            placeholder="공지 제목·내용·작성자 검색"
            onChange={(e) => setQuery(e.target.value)}
          />
          {query !== '' && (
            <button type="button" className="icon-btn" aria-label="지우기" onClick={() => setQuery('')}>
              <Icon name="close" size={18} />
            </button>
          )}
        </label>
      </div>

      {matched.length === 0 ? (
        <div className="board-empty">
          <Icon name={q === '' ? 'campaign' : 'search_off'} size={36} />
          <p>{q === '' ? '등록된 공지가 없습니다.' : '검색 결과가 없습니다.'}</p>
        </div>
      ) : (
        <div className="board-column">
          {important.length > 0 && (
            <section className="section">
              <h2 className="board-section__title">
                <Icon name="star" size={16} className="board-section__star" />
                중요 공지
              </h2>
              <NoticeList notices={important} onOpen={setOpen} />
            </section>
          )}
          {rest.length > 0 && (
            <section className="section">
              <h2 className="board-section__title">
                <Icon name="campaign" size={16} />
                전체 공지
              </h2>
              <NoticeList notices={rest} onOpen={setOpen} />
            </section>
          )}
        </div>
      )}

      {open !== null && <NoticeDetailDialog notice={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

export function NoticeList({
  notices,
  onOpen,
}: {
  notices: Notice[];
  onOpen(notice: Notice): void;
}) {
  return (
    <Card padded={false}>
      <ul className="notice-rows">
        {notices.map((notice) => (
          <li key={notice.id}>
            <button type="button" className="notice-row" onClick={() => onOpen(notice)}>
              {notice.isFavorite && <Badge tone="error">중요</Badge>}
              <span className="notice-row__title">{notice.title}</span>
              <span className="notice-row__author">{notice.authorName}</span>
              <span className="notice-row__date">{formatDateTime(notice.createdAt)}</span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function FeedTab() {
  const user = useCurrentUser();
  const posts = usePosts();
  const [draft, setDraft] = useState('');

  const submit = () => {
    const content = draft.trim();
    if (content === '') return;
    createPost(user.uid, user.displayName, content);
    setDraft('');
  };

  return (
    <div className="stack">
      <Card>
        <TextArea
          value={draft}
          rows={3}
          placeholder="기수 동료들과 나누고 싶은 이야기를 적어 보세요."
          onChange={(e) => setDraft(e.target.value)}
        />
        <Row>
          <Spacer />
          <Button onClick={submit} disabled={draft.trim() === ''}>
            올리기
          </Button>
        </Row>
      </Card>

      {posts.length === 0 ? (
        <Card>
          <EmptyState message="아직 올라온 글이 없습니다" />
        </Card>
      ) : (
        posts.map((post) => <FeedPost key={post.id} post={post} />)
      )}
    </div>
  );
}

function FeedPost({ post }: { post: Post }) {
  const user = useCurrentUser();
  const comments = usePostComments(post.id);
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState('');

  const submitComment = () => {
    const content = draft.trim();
    if (content === '') return;
    createPostComment(post.id, user.uid, user.displayName, content);
    setDraft('');
    setExpanded(true);
  };

  return (
    <Card>
      <Row gap={10}>
        <Avatar name={post.authorName} />
        <div>
          <strong>{post.authorName}</strong>
          <p className="hint">{formatRelative(post.createdAt)}</p>
        </div>
        <Spacer />
        {post.authorId === user.uid && (
          <Button variant="text" size="sm" onClick={() => deletePost(post.id)}>
            삭제
          </Button>
        )}
      </Row>
      <p className="muted feed-post__content">{post.content}</p>
      <Row gap={8}>
        <Button variant="outline" size="sm" onClick={() => likePost(post.id)}>
          ♡ {post.likeCount}
        </Button>
        <Button
          variant="text"
          size="sm"
          aria-label={`댓글 ${post.commentCount}`}
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          댓글 {post.commentCount}
          <Icon name={expanded ? 'expand_less' : 'expand_more'} size={17} />
        </Button>
      </Row>

      {expanded && (
        <div className="feed-comments">
          {comments.length === 0 ? (
            <p className="hint">첫 댓글을 남겨 보세요.</p>
          ) : (
            <ul className="feed-comments__list">
              {comments.map((comment) => (
                <li key={comment.id} className="feed-comment">
                  <Avatar name={comment.authorName} size={28} />
                  <div className="feed-comment__body">
                    <Row gap={6}>
                      <strong>{comment.authorName}</strong>
                      <span className="hint">{formatRelative(comment.createdAt)}</span>
                      <Spacer />
                      {comment.authorId === user.uid && (
                        <button
                          type="button"
                          className="feed-comment__delete"
                          onClick={() => deletePostComment(post.id, comment.id)}
                        >
                          삭제
                        </button>
                      )}
                    </Row>
                    <p>{comment.content}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <div className="feed-comments__form">
            <TextArea
              value={draft}
              rows={2}
              aria-label={`${post.authorName} 게시글에 댓글 작성`}
              placeholder="댓글을 입력하세요."
              onChange={(event) => setDraft(event.target.value)}
            />
            <Button size="sm" disabled={draft.trim() === ''} onClick={submitComment}>댓글 등록</Button>
          </div>
        </div>
      )}
    </Card>
  );
}
