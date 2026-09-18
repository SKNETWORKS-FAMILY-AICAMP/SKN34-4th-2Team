import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/user_model.dart';
import '../../features/auth/providers/auth_providers.dart';

/// 현재 로그인 유저 (동기 접근 — redirect/조건 분기용)
final currentUserSyncProvider = Provider<UserModel?>((ref) {
  return ref.watch(currentUserProvider).value;
});

/// 현재 유저 문서의 home cohortId
final cohortIdProvider = Provider<String?>((ref) {
  return ref.watch(currentUserSyncProvider)?.cohortId;
});

/// 관리자가 UI에서 선택한 기수 (null이면 home cohort 사용)
final selectedCohortIdProvider =
    NotifierProvider<_SelectedCohortId, String?>(_SelectedCohortId.new);

class _SelectedCohortId extends Notifier<String?> {
  @override
  String? build() => null;

  void select(String id) => state = id;
}

/// 실제 쿼리/CRUD에 사용하는 cohortId
final effectiveCohortIdProvider = Provider<String?>((ref) {
  final user = ref.watch(currentUserSyncProvider);
  if (user == null) return null;
  if (user.isAdmin) {
    return ref.watch(selectedCohortIdProvider) ?? user.cohortId;
  }
  return user.cohortId;
});

/// 관리자 여부
final isAdminProvider = Provider<bool>((ref) {
  return ref.watch(currentUserSyncProvider)?.isAdmin ?? false;
});

/// 강사 여부
final isInstructorProvider = Provider<bool>((ref) {
  return ref.watch(currentUserSyncProvider)?.isInstructor ?? false;
});

/// 기수 이력서 열람·피드백 (관리자 + 강사)
final canReviewResumesProvider = Provider<bool>((ref) {
  final role = ref.watch(currentUserSyncProvider)?.role;
  return role?.canReviewResumes ?? false;
});

/// 기수 공지 작성 (관리자 + 강사)
final canWriteNoticesProvider = Provider<bool>((ref) {
  final role = ref.watch(currentUserSyncProvider)?.role;
  return role?.canWriteNotices ?? false;
});

/// 관리자 기수 선택 헬퍼
void selectCohort(WidgetRef ref, String cohortId) {
  ref.read(selectedCohortIdProvider.notifier).select(cohortId);
}
