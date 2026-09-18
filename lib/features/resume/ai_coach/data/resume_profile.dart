import '../../../../shared/models/resume_content.dart';

/// 추천 서버 요청에 넣는 이력서 조건. 학력·연차·전공·자격증을 이력서에서 뽑는다.
///
/// 서버의 하드 필터(`job_matching_bot/matching/hard_filter.py`)가 이 값으로 연차·학력·
/// 전공·자격증 조건을 판정한다. 기술·경험은 여기 없고 이력서 평문으로 보낸다.
class RecommendResumeProfile {
  const RecommendResumeProfile({
    required this.educationLevel,
    required this.careerYears,
    required this.majors,
    required this.certifications,
  });

  /// 하드 필터의 `EDUCATION_RANK` 와 같은 값. 미기재·고졸·초대졸·대졸·석사·박사.
  final String educationLevel;
  final double careerYears;

  /// 학력사항의 전공과 자격사항 이름.
  final List<String> majors;
  final List<String> certifications;

  factory RecommendResumeProfile.fromContent(ResumeContent content) {
    final education = content.education.where((e) => e.isFilled).toList();
    final experience = content.experience.where((e) => e.isFilled).toList();
    return RecommendResumeProfile(
      educationLevel: educationLevelOf(education),
      careerYears: estimateCareerYears(experience),
      majors: [for (final e in education) if (e.major.trim().isNotEmpty) e.major.trim()],
      certifications: [
        for (final c in content.certifications)
          if (c.name.trim().isNotEmpty) c.name.trim(),
      ],
    );
  }
}

/// 하드 필터가 쓰는 순서. 뒤로 갈수록 높다.
const educationOrder = ['미기재', '고졸', '초대졸', '대졸', '석사', '박사'];

/// 학위를 못 받았을 때 실제로 인정되는 수준.
///
/// 한 칸씩 내리면 안 된다. 대학교 중퇴는 초대졸이 아니라 고졸이다.
const _beforeDegree = {
  '박사': '석사',
  '석사': '대졸',
  '대졸': '고졸',
  '초대졸': '고졸',
  '고졸': '미기재',
};

/// 학교 이름·전공에서 학위 수준을 읽는다. 못 읽으면 빈 문자열.
String _degreeOf(ResumeEducationItem item) {
  final text = '${item.school} ${item.major}'.replaceAll(RegExp(r'\s'), '');
  if (text.contains('박사')) return '박사';
  if (text.contains('대학원') || text.contains('석사')) return '석사';
  // `전문대학`은 `대학`을 품고 있다. 반드시 먼저 본다.
  if (text.contains('전문대') || RegExp(r'\([23]년제\)').hasMatch(text)) return '초대졸';
  if (text.contains('대학')) return '대졸';
  if (text.contains('고등학교') || text.contains('고교')) return '고졸';
  return '';
}

/// 학위를 실제로 받았는가.
///
/// 상태 칸은 자유 입력이라(`상태 (졸업/재학/수료)`) 정해진 목록이 없다. `졸업`이
/// 들어 있으면 받은 것으로 본다. `졸업예정`도 대졸 공고에 지원할 수 있으니 포함한다.
/// `재학`·`휴학`·`중퇴`·`자퇴`·`수료`에는 `졸업`이 없어 자연히 걸러진다.
///
/// 비워 둔 경우는 받은 것으로 본다. 학교를 적고 상태만 안 쓴 이력서가 흔하고,
/// 안 썼다는 이유로 학력을 깎으면 멀쩡한 공고가 사라진다.
bool _hasDegree(String status) {
  final s = status.trim();
  return s.isEmpty || s.contains('졸업') || s.contains('학위취득');
}

/// 학력사항에서 가장 높은 학력을 고른다.
///
/// 예전에는 학력 항목이 한 줄이라도 있으면 무조건 `대졸`이었다. 전공을 적었다는 것과
/// 그 학위를 받았다는 것은 다른 이야기인데 둘을 같이 봤다. 그래서 전문학사도 대졸로
/// 나가 대졸 필수 공고(모집 중 6,877건)를 그대로 통과했고, 대학교 재학 중인 사람도
/// 마찬가지였다. 반대로 석사는 대졸로 낮춰져 석사 필수 공고에서 떨어졌다.
String educationLevelOf(List<ResumeEducationItem> education) {
  var best = 0;
  for (final item in education) {
    if (!item.isFilled) continue;
    final degree = _degreeOf(item);
    if (degree.isEmpty) continue;
    final level = _hasDegree(item.status) ? degree : (_beforeDegree[degree] ?? '미기재');
    final rank = educationOrder.indexOf(level);
    if (rank > best) best = rank;
  }
  return educationOrder[best];
}

DateTime? _parseMonth(String value) {
  final trimmed = value.trim();
  if (trimmed.isEmpty) return null;
  final normalized = RegExp(r'^\d{4}-\d{2}$').hasMatch(trimmed) ? '$trimmed-01' : trimmed;
  return DateTime.tryParse(normalized);
}

/// 경력사항의 재직 기간을 월 단위로 더해 소수 첫째 자리까지. 재직 중은 오늘까지.
double estimateCareerYears(List<ResumeExperienceItem> experience) {
  var months = 0;
  final now = DateTime.now();
  for (final item in experience) {
    final start = _parseMonth(item.startDate);
    final end = item.isCurrent ? now : _parseMonth(item.endDate);
    if (start == null || end == null || end.isBefore(start)) continue;
    final diff = (end.year - start.year) * 12 + end.month - start.month;
    months += diff < 0 ? 0 : diff;
  }
  return (months / 12 * 10).round() / 10;
}
