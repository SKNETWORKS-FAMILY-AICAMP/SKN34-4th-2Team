/// 마일리지 미션 규칙 상수 (노션 제도 · 1차 기록실)
abstract final class MissionRules {
  static const studyCertTiers = [
    (count: 3, amount: 10000),
    (count: 5, amount: 30000),
    (count: 10, amount: 50000),
  ];

  static const quizTiers = [
    (count: 1, amount: 10000),
    (count: 3, amount: 30000),
    (count: 5, amount: 50000),
  ];

  static const quizPassScore = 60;
  static const blogUnitReward = 20000;
  static const blogMaxUnits = 5;
  static const studyTeamReward = 50000;
  static const codingPcce = 25000;
  static const codingAdvanced = 50000;

  static int tierTarget(int count, List<({int count, int amount})> tiers) {
    var target = 0;
    for (final t in tiers) {
      if (count >= t.count) target = t.amount;
    }
    return target;
  }

  static ({int count, int amount})? nextTier(
    int count,
    List<({int count, int amount})> tiers,
  ) {
    for (final t in tiers) {
      if (count < t.count) return t;
    }
    return null;
  }
}
