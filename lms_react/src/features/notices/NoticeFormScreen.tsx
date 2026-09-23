import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { createNotice, updateNotice, useNotice } from '../../data/repository';
import {
  Button,
  Card,
  Checkbox,
  Field,
  PageHeader,
  Row,
  Spacer,
  TextArea,
  TextInput,
} from '../../ui/components';
import { useCurrentUser } from '../auth/session';

/**
 * 공지 작성·수정 — features/admin/presentation/admin_notice_form_screen.dart
 *
 * 강사 게시물관리와 관리자 게시판이 같은 폼을 쓴다. 돌아갈 곳만 다르다.
 */
export function NoticeFormScreen({ backTo }: { backTo: string }) {
  const { noticeId } = useParams<{ noticeId: string }>();
  const existing = useNotice(noticeId);
  const user = useCurrentUser();
  const navigate = useNavigate();

  const [title, setTitle] = useState(existing?.title ?? '');
  const [content, setContent] = useState(existing?.content ?? '');
  const [isFavorite, setFavorite] = useState(existing?.isFavorite ?? false);
  const [imageUrl, setImageUrl] = useState(existing?.imageUrl ?? '');
  const [error, setError] = useState<string | null>(null);

  const save = () => {
    if (title.trim() === '') {
      setError('제목을 입력해 주세요.');
      return;
    }
    if (existing === undefined) {
      createNotice({
        title: title.trim(),
        content: content.trim(),
        authorName: user.displayName,
        authorId: user.uid,
        isFavorite,
        priority: isFavorite ? 1 : 0,
        imageUrl: imageUrl.trim() === '' ? undefined : imageUrl.trim(),
      });
    } else {
      updateNotice(existing.id, {
        title: title.trim(),
        content: content.trim(),
        isFavorite,
        priority: isFavorite ? 1 : 0,
        imageUrl: imageUrl.trim() === '' ? undefined : imageUrl.trim(),
      });
    }
    navigate(backTo);
  };

  return (
    <div className="screen__inner">
      <PageHeader title={existing === undefined ? '공지 작성' : '공지 수정'} />
      <Card>
        <Field label="제목" error={error ?? undefined}>
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="내용">
          <TextArea rows={10} value={content} onChange={(e) => setContent(e.target.value)} />
        </Field>
        {/* 원본은 사진을 직접 올린다(Storage). 서버에 올리는 길이 아직 없어 주소로 받는다 */}
        <Field label="사진" hint="이미지 주소를 넣으면 공지 본문 위에 보입니다.">
          <TextInput value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} placeholder="https://" />
        </Field>
        {imageUrl.trim() !== '' && <img className="notice-form__image" src={imageUrl.trim()} alt="" />}
        <Checkbox checked={isFavorite} onChange={setFavorite} label="중요 공지로 올립니다 (목록 위쪽에 고정)" />
        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(backTo)}>
            취소
          </Button>
          <Button onClick={save}>{existing === undefined ? '등록' : '수정'}</Button>
        </Row>
      </Card>
    </div>
  );
}
