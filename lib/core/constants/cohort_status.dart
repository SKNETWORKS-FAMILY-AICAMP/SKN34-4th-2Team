/// 기수 운영 상태
enum CohortStatus {
  upcoming('upcoming', '예정'),
  active('active', '진행중'),
  archived('archived', '종료');

  const CohortStatus(this.value, this.label);

  final String value;
  final String label;

  static CohortStatus fromString(String? raw) {
    return CohortStatus.values.firstWhere(
      (s) => s.value == raw,
      orElse: () => CohortStatus.active,
    );
  }
}
