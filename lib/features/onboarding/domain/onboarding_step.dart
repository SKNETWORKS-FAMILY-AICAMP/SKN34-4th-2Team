/// 온보딩 한 스텝 — 역할별 스텝 목록에서 재사용
class OnboardingStep {
  const OnboardingStep({
    required this.id,
    required this.title,
    required this.body,
    required this.targetId,
    this.route,
    this.skippableIfMissing = false,
  });

  final String id;
  final String title;
  final String body;

  /// [OnboardingTargetRegistry]에 등록된 타깃 id
  final String targetId;

  /// 표시 전 이동할 라우트 (null이면 현재 위치 유지)
  final String? route;

  /// 타깃이 없으면 자동으로 다음 스텝으로 넘김
  final bool skippableIfMissing;
}
