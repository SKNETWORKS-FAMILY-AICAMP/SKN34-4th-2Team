class AiJobCoachResult {
  const AiJobCoachResult({
    required this.testMode,
    required this.notice,
    required this.recommendations,
    required this.selectedJob,
    required this.skillJudgements,
    required this.resumeFeedback,
    required this.learningRecommendations,
    required this.analysisId,
    this.fromServer = false,
    this.searchQuery = '',
    this.profileSummary = '',
    this.warnings = const [],
    this.promptVersion = '',
    this.model = '',
    this.reasoningEffort = '',
    this.reranked = false,
  });

  final bool testMode;
  final String notice;
  final List<JobRecommendation> recommendations;
  final SelectedJob? selectedJob;
  final List<SkillJudgement> skillJudgements;
  final List<String> resumeFeedback;
  final List<LearningRecommendation> learningRecommendations;
  final String analysisId;

  /// 추천 서버(벡터 검색 + LLM 재정렬)가 만든 결과인지. false면 앱 안의 규칙 기반.
  final bool fromServer;

  /// 서버가 이력서에서 만든 검색 질의문. 규칙 기반 결과에는 없다.
  final String searchQuery;
  final String profileSummary;

  /// 서버가 근거 검증에서 제거한 내용.
  final List<String> warnings;
  final String promptVersion;
  final String model;
  final String reasoningEffort;
  final bool reranked;

  factory AiJobCoachResult.fromMap(Map<String, dynamic> map) {
    final skillAnalysis = _map(map['skillAnalysis']);
    return AiJobCoachResult(
      testMode: map['testMode'] as bool? ?? false,
      notice: map['recommendationNotice'] as String? ?? '',
      recommendations: _mapList(
        map['recommendations'],
      ).map(JobRecommendation.fromMap).toList(),
      selectedJob: map['selectedJob'] == null
          ? null
          : SelectedJob.fromMap(_map(map['selectedJob'])),
      skillJudgements: _mapList(
        skillAnalysis['judgements'],
      ).map(SkillJudgement.fromMap).toList(),
      resumeFeedback: _stringList(skillAnalysis['resumeFeedback']),
      learningRecommendations: _mapList(
        skillAnalysis['learningRecommendations'],
      ).map(LearningRecommendation.fromMap).toList(),
      analysisId: map['analysisId'] as String? ?? '',
    );
  }
}

extension AiJobCoachResultCopy on AiJobCoachResult {
  AiJobCoachResult copyWith({
    List<JobRecommendation>? recommendations,
    String? notice,
  }) {
    return AiJobCoachResult(
      testMode: testMode,
      notice: notice ?? this.notice,
      recommendations: recommendations ?? this.recommendations,
      selectedJob: selectedJob,
      skillJudgements: skillJudgements,
      resumeFeedback: resumeFeedback,
      learningRecommendations: learningRecommendations,
      analysisId: analysisId,
      fromServer: fromServer,
      searchQuery: searchQuery,
      profileSummary: profileSummary,
      warnings: warnings,
      promptVersion: promptVersion,
      model: model,
      reasoningEffort: reasoningEffort,
      reranked: reranked,
    );
  }
}

class JobRecommendation {
  const JobRecommendation({
    required this.jobId,
    required this.source,
    required this.sourceUrl,
    required this.company,
    required this.title,
    required this.score,
    required this.grade,
    required this.hardFilterStatus,
    required this.unknownConditions,
    required this.evidence,
    this.passedConditions = const [],
    this.roleTerms = const [],
    this.matchedSkills = const [],
    this.projectSkills = const [],
    this.unmatchedSkills = const [],
    this.scoreDetail,
    this.bodyIsImage = false,
    this.region = '',
    this.employmentType,
    this.careerType = '',
    this.minCareerYears,
    this.education = '',
    this.requiredMajors = const [],
    this.requiredCertifications = const [],
    this.militaryRequired = false,
    this.matchedRequired = const [],
    this.matchedPreferred = const [],
    this.matchedTags = const [],
    this.unmatchedRequired = const [],
    this.unmatchedPreferred = const [],
    this.unmatchedTags = const [],
    this.embeddingRank,
    this.fusedScore,
    this.careerText = '',
    this.deadline,
    this.reasons = const [],
    this.concerns = const [],
    this.searchRank,
  });

  final String jobId;
  final String source;
  final String sourceUrl;
  final String company;
  final String title;
  final double score;
  final String grade;
  final String hardFilterStatus;
  final List<String> unknownConditions;

  /// 직무 키워드·일치 기술을 합친 짧은 목록. 요약 표시와 예전 응답 호환용.
  final List<String> evidence;

  /// 하드 필터를 통과한 조건 문구(예: '학력 조건 충족').
  final List<String> passedConditions;

  /// 공고 제목·본문에서 맞은 희망 직무 키워드.
  final List<String> roleTerms;

  /// 공고가 언급한 기술 중 이력서 기술스택과 겹친 것(공고 쪽 표기).
  final List<String> matchedSkills;

  /// 공고가 언급한 기술 중 프로젝트 경험에서 확인된 것.
  final List<String> projectSkills;

  /// 공고가 언급하지만 이력서 어디에도 근거가 없는 기술. 경험 없음 판단이 아니다.
  final List<String> unmatchedSkills;

  /// 점수 구성. 예전 응답에는 없을 수 있다.
  final RecommendationScoreDetail? scoreDetail;

  /// 공고 상세가 이미지뿐이라 기업이 고른 기술 태그로만 비교한 경우.
  final bool bodyIsImage;

  /// 공고에 적힌 조건. 카드가 희망 조건과 나란히 보여준다.
  final String region;
  final String? employmentType;
  final String careerType;
  final int? minCareerYears;
  final String education;

  /// 자격요건 구간에서 뽑은 전공·자격증·병역 요건.
  final List<String> requiredMajors;
  final List<String> requiredCertifications;
  final bool militaryRequired;

  /// 출처별 기술 근거. 필수·우대는 본문에서 뽑은 것, 태그는 기업이 등록 때 고른 것.
  final List<String> matchedRequired;
  final List<String> matchedPreferred;
  final List<String> matchedTags;
  final List<String> unmatchedRequired;
  final List<String> unmatchedPreferred;
  final List<String> unmatchedTags;

  /// 추천 서버가 이미 문구로 만든 경력 조건(예: '경력 3년 이상'). 규칙 기반 결과에는 없다.
  final String careerText;

  /// 마감일. 서버 결과에만 있다.
  final String? deadline;

  /// 추천 서버의 근거. 이력서 원문과 공고 원문 인용 한 쌍씩.
  final List<RecommendReason> reasons;

  /// 공고 자격요건 중 이력서에서 확인되지 않은 것. 경험이 없다는 판단이 아니다.
  final List<String> concerns;

  /// 벡터 검색에서의 순위. 서버 결과에만 있고, 있으면 서버 결과다.
  final int? searchRank;

  bool get isFromServer => searchRank != null;

  /// 신입/경력무관/경력 n년 이상 같은 표시용 문구.
  String get careerLabel {
    if (careerText.isNotEmpty) return careerText;
    switch (careerType) {
      case 'ENTRY':
        return '신입';
      case 'ANY':
        return '경력무관';
      case 'EXPERIENCED':
        return minCareerYears == null ? '경력' : '경력 $minCareerYears년 이상';
      default:
        return '미기재';
    }
  }

  /// 예전 임베딩 재정렬 경로의 순위. 지금은 쓰지 않으며 항상 null.
  final int? embeddingRank;

  /// 키워드 순위와 임베딩 순위를 RRF로 합친 값. 재정렬 전에는 null.
  final double? fusedScore;

  JobRecommendation copyWith({
    List<String>? evidence,
    int? embeddingRank,
    double? fusedScore,
  }) {
    return JobRecommendation(
      jobId: jobId,
      source: source,
      sourceUrl: sourceUrl,
      company: company,
      title: title,
      score: score,
      grade: grade,
      hardFilterStatus: hardFilterStatus,
      unknownConditions: unknownConditions,
      evidence: evidence ?? this.evidence,
      passedConditions: passedConditions,
      roleTerms: roleTerms,
      matchedSkills: matchedSkills,
      projectSkills: projectSkills,
      unmatchedSkills: unmatchedSkills,
      scoreDetail: scoreDetail,
      bodyIsImage: bodyIsImage,
      region: region,
      employmentType: employmentType,
      careerType: careerType,
      minCareerYears: minCareerYears,
      education: education,
      requiredMajors: requiredMajors,
      requiredCertifications: requiredCertifications,
      militaryRequired: militaryRequired,
      matchedRequired: matchedRequired,
      matchedPreferred: matchedPreferred,
      matchedTags: matchedTags,
      unmatchedRequired: unmatchedRequired,
      unmatchedPreferred: unmatchedPreferred,
      unmatchedTags: unmatchedTags,
      embeddingRank: embeddingRank ?? this.embeddingRank,
      fusedScore: fusedScore ?? this.fusedScore,
      careerText: careerText,
      deadline: deadline,
      reasons: reasons,
      concerns: concerns,
      searchRank: searchRank,
    );
  }

  factory JobRecommendation.fromMap(Map<String, dynamic> map) {
    final hardFilter = _map(map['hardFilter']);
    final evidenceMap = _map(map['evidence']);
    final detail = _map(map['scoreDetail']);
    final matchedSkills = _stringList(evidenceMap['matchedSkills']);
    return JobRecommendation(
      jobId: map['jobId'] as String? ?? '',
      source: map['source'] as String? ?? '',
      sourceUrl: map['sourceUrl'] as String? ?? '',
      company: map['company'] as String? ?? '',
      title: map['title'] as String? ?? '',
      score: (map['recommendationScore'] as num?)?.toDouble() ?? 0,
      grade: map['grade'] as String? ?? '낮음',
      hardFilterStatus: hardFilter['status'] as String? ?? '',
      unknownConditions: _stringList(hardFilter['unknown']),
      passedConditions: _stringList(hardFilter['passed']),
      evidence: {
        ..._stringList(evidenceMap['roleTerms']),
        ...matchedSkills,
        // 예전 응답 형식(필수/우대를 따로 채점하던 때)도 읽는다.
        ..._stringList(evidenceMap['requiredSkills']),
        ..._stringList(evidenceMap['preferredSkills']),
      }.toList(),
      roleTerms: _stringList(evidenceMap['roleTerms']),
      matchedSkills: matchedSkills,
      projectSkills: _stringList(evidenceMap['projectSkills']),
      unmatchedSkills: _stringList(evidenceMap['unmatchedSkills']),
      scoreDetail: detail.isEmpty ? null : RecommendationScoreDetail.fromMap(detail),
      bodyIsImage: map['bodyIsImage'] as bool? ?? false,
      region: map['region'] as String? ?? '',
      employmentType: map['employmentType'] as String?,
      careerType: map['careerType'] as String? ?? '',
      minCareerYears: (map['minCareerYears'] as num?)?.toInt(),
      education: map['education'] as String? ?? '',
      requiredMajors: _stringList(map['requiredMajors']),
      requiredCertifications: _stringList(map['requiredCertifications']),
      militaryRequired: map['militaryRequired'] as bool? ?? false,
      matchedRequired: _stringList(evidenceMap['matchedRequired']),
      matchedPreferred: _stringList(evidenceMap['matchedPreferred']),
      matchedTags: _stringList(evidenceMap['matchedTags']),
      unmatchedRequired: _stringList(evidenceMap['unmatchedRequired']),
      unmatchedPreferred: _stringList(evidenceMap['unmatchedPreferred']),
      unmatchedTags: _stringList(evidenceMap['unmatchedTags']),
      embeddingRank: (map['embeddingRank'] as num?)?.toInt(),
      fusedScore: (map['fusedScore'] as num?)?.toDouble(),
    );
  }

  /// 추천 서버(`POST /api/v1/jobs/recommend`) 응답의 공고 하나.
  ///
  /// 서버는 점수 대신 적합도(높음/보통/낮음)와 근거 인용을 준다. 점수 구성이나
  /// 기술 버킷은 없으므로 비워 두고, 카드는 그 경우 근거·우려를 대신 보여 준다.
  factory JobRecommendation.fromRecommendApi(Map<String, dynamic> map) {
    final conditions = _map(map['conditions']);
    final reasons = _mapList(map['reasons']).map(RecommendReason.fromMap).toList();
    return JobRecommendation(
      jobId: map['job_id'] as String? ?? '',
      source: '',
      sourceUrl: map['source_url'] as String? ?? '',
      company: map['company'] as String? ?? '',
      title: map['title'] as String? ?? '',
      score: 0,
      grade: map['fit'] as String? ?? '보통',
      hardFilterStatus: map['filter_status'] as String? ?? 'PASS',
      unknownConditions: _stringList(map['unknown_conditions']),
      passedConditions: _stringList(map['passed_conditions']),
      evidence: [for (final reason in reasons) reason.claim],
      bodyIsImage: map['body_is_image'] as bool? ?? false,
      region: conditions['region'] as String? ?? '',
      employmentType: conditions['employment_type'] as String?,
      education: conditions['education'] as String? ?? '',
      careerText: conditions['career'] as String? ?? '',
      deadline: conditions['deadline'] as String?,
      reasons: reasons,
      concerns: _stringList(map['concerns']),
      searchRank: (map['search_rank'] as num?)?.toInt() ?? 0,
    );
  }
}

/// 추천 서버가 든 근거 하나. 두 인용은 각각 이력서·공고 원문에 그대로 있는 문장이다.
class RecommendReason {
  const RecommendReason({
    required this.claim,
    required this.resumeQuote,
    required this.jobQuote,
  });

  final String claim;
  final String resumeQuote;
  final String jobQuote;

  factory RecommendReason.fromMap(Map<String, dynamic> map) {
    return RecommendReason(
      claim: map['claim'] as String? ?? '',
      resumeQuote: map['resume_quote'] as String? ?? '',
      jobQuote: map['job_quote'] as String? ?? '',
    );
  }
}

/// 추천 점수 구성. 각 값은 0~1 비율이고, 가중치를 곱한 것이 점수 기여분이다.
class RecommendationScoreDetail {
  const RecommendationScoreDetail({
    required this.role,
    required this.skills,
    required this.project,
    required this.conditions,
    required this.skillsTotal,
  });

  final double role;
  final double skills;
  final double project;
  final double conditions;

  /// 공고가 언급한 기술 수(필수·우대·태그 합산, 중복 제거).
  final int skillsTotal;

  factory RecommendationScoreDetail.fromMap(Map<String, dynamic> map) {
    return RecommendationScoreDetail(
      role: (map['role'] as num?)?.toDouble() ?? 0,
      skills: (map['skills'] as num?)?.toDouble() ?? 0,
      project: (map['project'] as num?)?.toDouble() ?? 0,
      conditions: (map['conditions'] as num?)?.toDouble() ?? 0,
      skillsTotal: (map['skillsTotal'] as num?)?.toInt() ?? 0,
    );
  }
}

class SelectedJob {
  const SelectedJob({
    required this.jobId,
    required this.company,
    required this.title,
    required this.requiredSkills,
    required this.preferredSkills,
  });

  final String jobId;
  final String company;
  final String title;
  final List<String> requiredSkills;
  final List<String> preferredSkills;

  factory SelectedJob.fromMap(Map<String, dynamic> map) {
    return SelectedJob(
      jobId: map['jobId'] as String? ?? '',
      company: map['company'] as String? ?? '',
      title: map['title'] as String? ?? '',
      requiredSkills: _stringList(map['requiredSkills']),
      preferredSkills: _stringList(map['preferredSkills']),
    );
  }
}

class SkillJudgement {
  const SkillJudgement({
    required this.criterion,
    required this.requirementType,
    required this.judgement,
    required this.resumeEvidence,
    required this.jobEvidence,
    required this.confirmationQuestion,
  });

  final String criterion;
  final String requirementType;
  final String judgement;
  final List<String> resumeEvidence;
  final List<String> jobEvidence;
  final String? confirmationQuestion;

  factory SkillJudgement.fromMap(Map<String, dynamic> map) {
    return SkillJudgement(
      criterion: map['criterion'] as String? ?? '',
      requirementType: map['requirementType'] as String? ?? '',
      judgement: map['judgement'] as String? ?? '',
      resumeEvidence: _stringList(map['resumeEvidence']),
      jobEvidence: _stringList(map['jobEvidence']),
      confirmationQuestion: map['confirmationQuestion'] as String?,
    );
  }
}

class LearningRecommendation {
  const LearningRecommendation({
    required this.skill,
    required this.provider,
    required this.title,
    required this.url,
    required this.level,
    required this.estimatedDuration,
    required this.lastCheckedAt,
  });

  final String skill;
  final String provider;
  final String title;
  final String url;
  final String level;
  final String estimatedDuration;
  final String lastCheckedAt;

  factory LearningRecommendation.fromMap(Map<String, dynamic> map) {
    return LearningRecommendation(
      skill: map['skill'] as String? ?? '',
      provider: map['provider'] as String? ?? '',
      title: map['title'] as String? ?? '',
      url: map['url'] as String? ?? '',
      level: map['level'] as String? ?? '',
      estimatedDuration: map['estimatedDuration'] as String? ?? '',
      lastCheckedAt: map['lastCheckedAt'] as String? ?? '',
    );
  }
}

Map<String, dynamic> _map(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

List<Map<String, dynamic>> _mapList(dynamic value) {
  if (value is! List) return const [];
  return value.map(_map).toList();
}

List<String> _stringList(dynamic value) {
  if (value is! List) return const [];
  return value.whereType<String>().toList();
}
