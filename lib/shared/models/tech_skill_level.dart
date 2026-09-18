/// 기술스택 숙련도 단계.
///
/// 이력서에는 [label]만 저장한다(`ResumeTechStackItem.level`). 설명은 사용자가
/// 단계를 고를 때 기준을 맞추기 위한 것이고, 숫자 대신 말로 보여준다.
class TechSkillLevel {
  const TechSkillLevel({
    required this.label,
    required this.description,
  });

  final String label;
  final String description;
}

const techSkillLevels = <TechSkillLevel>[
  TechSkillLevel(label: '입문', description: '기본 문법과 개념을 학습했다'),
  TechSkillLevel(label: '초급', description: '예제나 과제 수준을 혼자 구현할 수 있다'),
  TechSkillLevel(label: '중급', description: '프로젝트에 실제로 사용해 기능을 완성했다'),
  TechSkillLevel(label: '고급', description: '구조 설계와 성능 개선을 주도할 수 있다'),
  TechSkillLevel(label: '전문가', description: '기술 선정과 다른 사람 지도가 가능하다'),
];

/// 저장된 숙련도 문자열에 맞는 단계. 예전 자유 입력 값이면 null.
TechSkillLevel? techSkillLevelOf(String value) {
  final trimmed = value.trim();
  for (final level in techSkillLevels) {
    if (level.label == trimmed) return level;
  }
  return null;
}
