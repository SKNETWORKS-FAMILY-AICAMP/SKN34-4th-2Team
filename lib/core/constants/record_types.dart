/// 기록실 제출 유형
abstract final class RecordTypes {
  static const certification = 'certification';
  static const study = 'study';
  static const blog = 'blog';
  static const studyCert = 'studyCert';
  static const precourseQuiz = 'precourseQuiz';

  static const all = [
    certification,
    study,
    blog,
    studyCert,
    precourseQuiz,
  ];

  static const labels = {
    certification: '자격증',
    study: '스터디',
    blog: '블로그',
    studyCert: '학습인증',
    precourseQuiz: '프리코스 퀴즈',
  };

  static const descriptions = {
    certification:
        'PCCE / PCCP / PCSQL 합격·레벨 취득 증빙을 제출하세요. '
        '승인 시 코딩테스트 미션 규칙(최대 50,000M)으로 적립됩니다.',
    study:
        '팀 스터디만 인정됩니다(개인 스터디 제외). '
        '오프라인 스터디 사진(날짜·시간 확인 가능)을 주 1회 이상 제출하세요. '
        '1~2단위기간 주 1회 이상 승인 시 50,000M이 적립됩니다.',
    blog:
        '안내된 블로그 양식에 맞춰 주차별 링크를 제출하세요. '
        '단위기간 내 모든 주차를 연속 작성·승인받으면 단위기간당 20,000M '
        '(최대 5단위·100,000M)이 적립됩니다.',
    studyCert:
        '개강 전 학습인증(예수학제)입니다. 학습일자·학습 내용·인증 사진을 올려 주세요. '
        '승인 횟수에 따라 3회 10,000 / 5회 30,000 / 10회 50,000M이 적립됩니다.',
    precourseQuiz:
        '프리코스 퀴즈 응시 결과(점수·증빙)를 제출하세요. '
        '60점 이상 승인 횟수에 따라 1회 10,000 / 3회 30,000 / 5회 50,000M이 적립됩니다.',
  };

  static const certKinds = ['PCCE', 'PCCP', 'PCSQL'];
}

class BlogWeekOption {
  const BlogWeekOption({
    required this.weekNumber,
    required this.label,
    required this.start,
    required this.end,
  });

  final int weekNumber;
  final String label;
  final DateTime start;
  final DateTime end;

  String get key => 'week_$weekNumber';
}

List<BlogWeekOption> generateBlogWeeks({DateTime? campStart, int count = 12}) {
  final start = campStart ?? DateTime(DateTime.now().year, 6, 1);
  return List.generate(count, (i) {
    final weekStart = start.add(Duration(days: i * 7));
    final weekEnd = weekStart.add(const Duration(days: 6));
    final n = i + 1;
    return BlogWeekOption(
      weekNumber: n,
      label:
          '$n주차 ${weekStart.month}/${weekStart.day}~${weekEnd.month}/${weekEnd.day}',
      start: weekStart,
      end: weekEnd,
    );
  });
}
