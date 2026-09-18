/// 취업 희망 조건. 이력서 문서가 아니라 `users/{uid}.jobPreferences`에 저장한다.
///
/// 이력서에 넣으면 PDF와 피드백 화면에 같이 찍히고, 이력서를 여러 개 만들면
/// 조건이 갈라진다. 맞춤 공고 추천의 하드 필터(지역·고용형태)와 직무 점수
/// (희망 직무)는 이 값을 이력서 내용과 별도로 받는다.
class JobPreferences {
  const JobPreferences({
    this.targetRoles = const [],
    this.regions = const [],
    this.employmentTypes = const [],
  });

  /// 희망 직무. 매처의 ROLE_TERMS 키와 같은 문자열이어야 점수에 반영된다.
  final List<String> targetRoles;

  /// 희망 근무지역. 공고의 지역 문자열에 포함되는지로 거른다(예: '서울' ⊂ '서울 성동구').
  final List<String> regions;

  /// 희망 고용형태. 공고의 고용형태와 정확히 같아야 통과한다(예: '정규직').
  final List<String> employmentTypes;

  bool get isEmpty =>
      targetRoles.isEmpty && regions.isEmpty && employmentTypes.isEmpty;

  bool get isNotEmpty => !isEmpty;

  factory JobPreferences.fromMap(Map<dynamic, dynamic>? map) {
    if (map == null) return const JobPreferences();
    return JobPreferences(
      targetRoles: _stringList(map['targetRoles']),
      regions: _stringList(map['regions']),
      employmentTypes: _stringList(map['employmentTypes']),
    );
  }

  Map<String, dynamic> toMap() => {
    'targetRoles': targetRoles,
    'regions': regions,
    'employmentTypes': employmentTypes,
  };

  JobPreferences copyWith({
    List<String>? targetRoles,
    List<String>? regions,
    List<String>? employmentTypes,
  }) {
    return JobPreferences(
      targetRoles: targetRoles ?? this.targetRoles,
      regions: regions ?? this.regions,
      employmentTypes: employmentTypes ?? this.employmentTypes,
    );
  }

  /// 한 줄 요약. 예: "백엔드 개발자 · 서울, 경기 · 정규직". 비어 있으면 빈 문자열.
  String get summary => [
    if (targetRoles.isNotEmpty) targetRoles.join(', '),
    if (regions.isNotEmpty) regions.join(', '),
    if (employmentTypes.isNotEmpty) employmentTypes.join(', '),
  ].join(' · ');

  static List<String> _stringList(dynamic value) {
    if (value is! List) return const [];
    return value
        .whereType<String>()
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
  }
}

/// 선택지. 공고 데이터에 실제로 나오는 표기와 맞춰야 필터가 걸린다.
abstract final class JobPreferenceOptions {
  /// 추천 서버(job_matching_bot/matching/ranking.py)의 ROLE_TERMS 키와 같아야 한다.
  static const roles = <String>[
    '백엔드 개발자',
    '프론트엔드 개발자',
    'AI 엔지니어',
    '데이터 엔지니어',
    '임베디드 개발자',
  ];

  /// 공고 지역은 "서울 성동구", "경기전체", "전국"처럼 적혀 있어 시·도 이름으로 거른다.
  static const regions = <String>[
    '서울', '경기', '인천', '부산', '대구', '대전', '광주', '울산', '세종',
    '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주', '전국',
  ];

  static const employmentTypes = <String>[
    '정규직',
    '계약직',
    '인턴',
    '파견직',
    '프리랜서',
  ];
}
