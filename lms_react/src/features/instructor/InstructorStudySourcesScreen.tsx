import { PageHeader } from '../../ui/components';
import { useCurrentUser } from '../auth/session';
import { StudySourcesPanel } from '../study/StudySourcesPanel';

/** 수업 저장소 — 강사가 자기 기수의 GitHub 조직·개인 계정을 연결하고, 학생에게 보일 저장소를 고른다 */
export function InstructorStudySourcesScreen() {
  const user = useCurrentUser();
  return (
    <div className="screen__inner">
      <PageHeader
        title="수업 저장소"
        description="연결한 GitHub 조직·계정의 저장소가 학생 공부방에 자동으로 올라갑니다. 학생은 여기 공개된 저장소로 복습 노트를 만들어요."
      />
      <StudySourcesPanel cohortId={user.cohortId} />
    </div>
  );
}
