import { RecordsBoard } from '../records/RecordsScreen';

/**
 * 기록실(관리자) — records_screen.dart의 isAdmin 가지
 *
 * 학생 화면과 같은 틀을 쓴다. 다른 것은 모두의 기록을 본다는 점과, 카드에서 바로
 * 승인·반려한다는 점뿐이다.
 */
export function AdminRecordsScreen() {
  return <RecordsBoard reviewer />;
}
