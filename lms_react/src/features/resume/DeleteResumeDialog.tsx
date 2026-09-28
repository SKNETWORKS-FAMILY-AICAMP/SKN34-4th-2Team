import { deleteResume } from '../../data/repository';
import type { Resume } from '../../domain/types';
import { Button, Dialog } from '../../ui/components';

/**
 * 공고용 사본 지우기 확인 — 이력서 관리의 공고 맞춤 이력서, 공고 맞춤 지원의 자소서가 함께 쓴다.
 *
 * 지우면 서버(commands._delete_resume)가 첨삭 기록 · 강사 피드백 · 공고 맞춤 정보까지 지운다. 되돌릴 수 없어 한 번 묻는다.
 * 바탕 이력서는 그대로다. 이 사본을 첨삭 완료로 옮긴 이력서가 있으면 그것도 남는다(연결만 끊긴다).
 */
export function DeleteResumeDialog({
  resume,
  title,
  onClose,
  onDeleted,
}: {
  resume: Resume;
  /** 화면에서 부르는 이름 — 자소서 목록은 「OO 자소서」로 보여 준다 */
  title?: string;
  onClose(): void;
  onDeleted?(): void;
}) {
  return (
    <Dialog
      title={`「${title ?? resume.title}」을 삭제할까요?`}
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              deleteResume(resume.id);
              onClose();
              onDeleted?.();
            }}
          >
            삭제
          </Button>
        </>
      }
    >
      <p className="hint">써 둔 내용과 첨삭 기록 · 강사 피드백이 함께 지워지고 되돌릴 수 없어요. 바탕 이력서는 그대로예요.</p>
    </Dialog>
  );
}
