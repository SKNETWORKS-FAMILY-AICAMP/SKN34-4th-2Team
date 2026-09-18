import type { Notice } from '../../domain/types';
import { Badge, Button, Dialog, Row } from '../../ui/components';
import { formatDateTime } from '../../utils/format';

/** 공지 상세 — features/hub/presentation/widgets/notice_list_widgets.dart의 바텀시트 */
export function NoticeDetailDialog({ notice, onClose }: { notice: Notice; onClose(): void }) {
  return (
    <Dialog
      title={notice.title}
      onClose={onClose}
      width={560}
      actions={<Button onClick={onClose}>닫기</Button>}
    >
      <Row gap={6}>
        {notice.isFavorite && <Badge tone="error">중요</Badge>}
        {notice.channelLabel !== undefined && <Badge tone="info">{notice.channelLabel}</Badge>}
        <span className="hint">
          {notice.authorName} · {formatDateTime(notice.createdAt)}
        </span>
      </Row>
      <p className="muted" style={{ whiteSpace: 'pre-wrap' }}>
        {notice.content}
      </p>
    </Dialog>
  );
}
