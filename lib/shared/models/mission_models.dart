import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/constants/mission_rules.dart';
import '../../core/utils/date_utils.dart';

/// `cohorts/{cohortId}/missionProgress/{userId}`
class MissionProgressModel {
  const MissionProgressModel({
    this.studyCertCount = 0,
    this.studyCertGranted = 0,
    this.quizPassCount = 0,
    this.quizGranted = 0,
    this.codingPcce = false,
    this.codingPccp = false,
    this.codingPcsql = false,
    this.codingGranted = 0,
    this.blogWeeks = const [],
    this.blogUnitsGranted = const [],
    this.studyWeekKeys = const [],
    this.studyGranted = false,
    this.updatedAt,
  });

  final int studyCertCount;
  final int studyCertGranted;
  final int quizPassCount;
  final int quizGranted;
  final bool codingPcce;
  final bool codingPccp;
  final bool codingPcsql;
  final int codingGranted;
  final List<int> blogWeeks;
  final List<int> blogUnitsGranted;
  final List<String> studyWeekKeys;
  final bool studyGranted;
  final DateTime? updatedAt;

  int get codingTarget {
    if (codingPccp || codingPcsql) return MissionRules.codingAdvanced;
    if (codingPcce) return MissionRules.codingPcce;
    return 0;
  }

  factory MissionProgressModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    if (!doc.exists) return const MissionProgressModel();
    final data = doc.data() ?? {};
    return MissionProgressModel(
      studyCertCount: (data['studyCertCount'] as num?)?.toInt() ?? 0,
      studyCertGranted: (data['studyCertGranted'] as num?)?.toInt() ?? 0,
      quizPassCount: (data['quizPassCount'] as num?)?.toInt() ?? 0,
      quizGranted: (data['quizGranted'] as num?)?.toInt() ?? 0,
      codingPcce: data['codingPcce'] == true,
      codingPccp: data['codingPccp'] == true,
      codingPcsql: data['codingPcsql'] == true,
      codingGranted: (data['codingGranted'] as num?)?.toInt() ?? 0,
      blogWeeks: List<int>.from(
        (data['blogWeeks'] as List? ?? []).map((e) => (e as num).toInt()),
      ),
      blogUnitsGranted: List<int>.from(
        (data['blogUnitsGranted'] as List? ?? [])
            .map((e) => (e as num).toInt()),
      ),
      studyWeekKeys: List<String>.from(data['studyWeekKeys'] as List? ?? []),
      studyGranted: data['studyGranted'] == true,
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
    );
  }
}

/// 학생 안내용 미션 카드 한 줄
class MissionGuidanceItem {
  const MissionGuidanceItem({
    required this.id,
    required this.title,
    required this.statusText,
    required this.hint,
    required this.progressLabel,
    this.earned = 0,
    this.maxEarn = 0,
  });

  final String id;
  final String title;
  final String statusText;
  final String hint;
  final String progressLabel;
  final int earned;
  final int maxEarn;
}

List<MissionGuidanceItem> buildMissionGuidance(MissionProgressModel p) {
  final items = <MissionGuidanceItem>[];

  final nextStudy = MissionRules.nextTier(
    p.studyCertCount,
    MissionRules.studyCertTiers,
  );
  items.add(
    MissionGuidanceItem(
      id: 'studyCert',
      title: '학습인증 (예수학제)',
      earned: p.studyCertGranted,
      maxEarn: 50000,
      progressLabel: '승인 ${p.studyCertCount}회 · 적립 ${p.studyCertGranted}M',
      statusText: nextStudy == null
          ? '최대 금액 달성'
          : '다음: ${nextStudy.count}회 → ${nextStudy.amount}M',
      hint: nextStudy == null
          ? '학습인증 미션을 모두 달성했어요.'
          : '${nextStudy.count - p.studyCertCount}회 더 승인되면 '
              '${nextStudy.amount - p.studyCertGranted}M을 더 받을 수 있어요.',
    ),
  );

  final nextQuiz = MissionRules.nextTier(
    p.quizPassCount,
    MissionRules.quizTiers,
  );
  items.add(
    MissionGuidanceItem(
      id: 'precourseQuiz',
      title: '프리코스 퀴즈 (60점↑)',
      earned: p.quizGranted,
      maxEarn: 50000,
      progressLabel: '통과 ${p.quizPassCount}회 · 적립 ${p.quizGranted}M',
      statusText: nextQuiz == null
          ? '최대 금액 달성'
          : '다음: ${nextQuiz.count}회 → ${nextQuiz.amount}M',
      hint: nextQuiz == null
          ? '프리코스 퀴즈 미션을 모두 달성했어요.'
          : '${nextQuiz.count - p.quizPassCount}회 더 통과·승인되면 '
              '${nextQuiz.amount - p.quizGranted}M을 더 받을 수 있어요.',
    ),
  );

  items.add(
    MissionGuidanceItem(
      id: 'coding',
      title: '코딩테스트 (PCCE/PCCP/PCSQL)',
      earned: p.codingGranted,
      maxEarn: 50000,
      progressLabel: [
        if (p.codingPcce) 'PCCE',
        if (p.codingPccp) 'PCCP',
        if (p.codingPcsql) 'PCSQL',
        if (!p.codingPcce && !p.codingPccp && !p.codingPcsql) '미취득',
      ].join(' · '),
      statusText: p.codingGranted >= 50000
          ? '최대 금액 달성'
          : p.codingPcce
              ? 'PCCP/PCSQL 취득 시 총 50,000M'
              : 'PCCE 25,000M / PCCP·PCSQL 50,000M',
      hint: p.codingGranted >= 50000
          ? '코딩테스트 미션 적립이 완료됐어요.'
          : '자격증 유형으로 제출·승인되면 규칙에 따라 적립됩니다.',
    ),
  );

  items.add(
    MissionGuidanceItem(
      id: 'blog',
      title: '블로그 (단위기간 연속)',
      earned: p.blogUnitsGranted.length * MissionRules.blogUnitReward,
      maxEarn: MissionRules.blogMaxUnits * MissionRules.blogUnitReward,
      progressLabel:
          '완료 단위 ${p.blogUnitsGranted.length}/${MissionRules.blogMaxUnits} · '
          '승인 주차 ${p.blogWeeks.length}개',
      statusText: p.blogUnitsGranted.length >= MissionRules.blogMaxUnits
          ? '최대 금액 달성'
          : '단위기간 전 주차 작성 시 +${MissionRules.blogUnitReward}M',
      hint: '단위기간마다 모든 주차를 빠짐없이 작성·승인받으면 적립됩니다.',
    ),
  );

  items.add(
    MissionGuidanceItem(
      id: 'study',
      title: '팀 스터디 (1~2단위)',
      earned: p.studyGranted ? MissionRules.studyTeamReward : 0,
      maxEarn: MissionRules.studyTeamReward,
      progressLabel: p.studyGranted
          ? '달성 · ${MissionRules.studyTeamReward}M'
          : '인증 주 ${p.studyWeekKeys.length}개',
      statusText: p.studyGranted
          ? '미션 달성'
          : '1~2단위기간 매주 1회 이상 팀 스터디 인증',
      hint: p.studyGranted
          ? '팀 스터디 미션을 달성했어요.'
          : '오프라인 팀 스터디 사진을 주 1회 이상 올려 주세요.',
    ),
  );

  return items;
}
