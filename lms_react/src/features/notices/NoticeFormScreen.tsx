import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { createNotice, updateNotice, uploadNoticeImage, useNotice } from '../../data/repository';
import { readApiError } from '../../data/http';
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
  const [imageStorageKey, setImageStorageKey] = useState(existing?.imageStorageKey);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!imageFile) return;
    const url = URL.createObjectURL(imageFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [imageFile]);

  const save = async () => {
    if (saving) return;
    if (title.trim() === '') {
      setError('제목을 입력해 주세요.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const uploaded = imageFile ? await uploadNoticeImage(imageFile) : null;
      const url = uploaded?.url ?? imageUrl.trim();
      const image = {
        imageUrl: url || undefined,
        imageStorageKey: uploaded?.key ?? (url ? imageStorageKey ?? url : ''),
      };
      if (existing === undefined) {
        await createNotice({
          title: title.trim(), content: content.trim(), authorName: user.displayName,
          authorId: user.uid, isFavorite, priority: isFavorite ? 1 : 0, ...image,
        });
      } else {
        await updateNotice(existing.id, {
          title: title.trim(), content: content.trim(), isFavorite,
          priority: isFavorite ? 1 : 0, ...image,
        });
      }
      navigate(backTo);
    } catch (cause) {
      setError(`공지를 저장하지 못했습니다 · ${await readApiError(cause)}`);
    } finally {
      setSaving(false);
    }
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
        <Field label="사진" hint="JPG, PNG, GIF, WEBP · 최대 10MB. 이미지 주소도 사용할 수 있습니다.">
          <input type="file" accept="image/jpeg,image/png,image/gif,image/webp" onChange={(e) => {
            const file = e.target.files?.[0] ?? null;
            if (file && (!['image/jpeg', 'image/png', 'image/gif', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024)) {
              setError('JPG, PNG, GIF, WEBP 이미지를 10MB 이하로 선택해 주세요.');
              e.target.value = '';
              return;
            }
            setImageFile(file);
            setError(null);
          }} />
          <TextInput value={imageUrl} onChange={(e) => {
            setImageUrl(e.target.value);
            setImageStorageKey(undefined);
            setImageFile(null);
          }} placeholder="https://" aria-label="이미지 주소" />
        </Field>
        {(imageFile ? previewUrl : imageUrl.trim()) !== '' && <>
          <img className="notice-form__image" src={imageFile ? previewUrl : imageUrl.trim()} alt="첨부 이미지 미리보기" />
          <Button variant="text" onClick={() => {
            setImageFile(null);
            setImageUrl('');
            setImageStorageKey(undefined);
          }}>사진 제거</Button>
        </>}
        <Checkbox checked={isFavorite} onChange={setFavorite} label="중요 공지로 올립니다 (목록 위쪽에 고정)" />
        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(backTo)}>
            취소
          </Button>
          <Button onClick={save} disabled={saving}>{saving ? '저장 중…' : existing === undefined ? '등록' : '수정'}</Button>
        </Row>
      </Card>
    </div>
  );
}
