import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/utils/date_utils.dart';

/// 상담 시 수집하는 학생 정보 + 계정 메타 (관리자 전용 `studentIntakes` 컬렉션)
class StudentIntakeModel {
  const StudentIntakeModel({
    required this.uid,
    required this.email,
    this.personalEmail,
    required this.displayName,
    required this.cohortId,
    required this.cohortName,
    required this.initialPassword,
    this.seatNumber,
    this.passwordChanged = false,
    this.educationMajor = '',
    this.currentStatus = '',
    this.weeklyStudyHours = '',
    this.programmingLevel = '',
    this.collaborationTools = '',
    this.aiLlmExperience = '',
    this.motivation = '',
    this.desiredRole = '',
    this.postCompletionGoal = '',
    this.awards = '',
    this.projectLinks = '',
    this.teamRole = '',
    this.selfLearningStyle = '',
    this.slumpOvercomeExperience = '',
    this.isActive = true,
    this.createdAt,
    this.createdBy,
  });

  final String uid;
  final String email;
  final String? personalEmail;
  final String displayName;
  final String cohortId;
  final String cohortName;
  final String initialPassword;
  final int? seatNumber;
  final bool passwordChanged;

  // 기본 인적 사항
  final String educationMajor;
  final String currentStatus;
  final String weeklyStudyHours;

  // 기술 역량
  final String programmingLevel;
  final String collaborationTools;
  final String aiLlmExperience;

  // 지원 동기·목표
  final String motivation;
  final String desiredRole;
  final String postCompletionGoal;

  // 수상·프로젝트
  final String awards;
  final String projectLinks;

  // 협업 성향
  final String teamRole;
  final String selfLearningStyle;
  final String slumpOvercomeExperience;

  final bool isActive;

  final DateTime? createdAt;
  final String? createdBy;

  String get passwordLabel =>
      passwordChanged ? '비밀번호 변경됨 (재발급 가능)' : initialPassword;

  factory StudentIntakeModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    final intake = data['intake'] as Map<String, dynamic>? ?? {};

    return StudentIntakeModel(
      uid: doc.id,
      email: data['email'] as String? ?? '',
      personalEmail: data['personalEmail'] as String?,
      displayName: data['displayName'] as String? ?? '',
      cohortId: data['cohortId'] as String? ?? '',
      cohortName: data['cohortName'] as String? ?? '',
      initialPassword: data['initialPassword'] as String? ?? '',
      seatNumber: data['seatNumber'] as int?,
      passwordChanged: data['passwordChanged'] as bool? ?? false,
      educationMajor: intake['educationMajor'] as String? ?? '',
      currentStatus: intake['currentStatus'] as String? ?? '',
      weeklyStudyHours: intake['weeklyStudyHours'] as String? ?? '',
      programmingLevel: intake['programmingLevel'] as String? ?? '',
      collaborationTools: intake['collaborationTools'] as String? ?? '',
      aiLlmExperience: intake['aiLlmExperience'] as String? ?? '',
      motivation: intake['motivation'] as String? ?? '',
      desiredRole: intake['desiredRole'] as String? ?? '',
      postCompletionGoal: intake['postCompletionGoal'] as String? ?? '',
      awards: intake['awards'] as String? ?? '',
      projectLinks: intake['projectLinks'] as String? ?? '',
      teamRole: intake['teamRole'] as String? ?? '',
      selfLearningStyle: intake['selfLearningStyle'] as String? ?? '',
      slumpOvercomeExperience:
          intake['slumpOvercomeExperience'] as String? ?? '',
      isActive: data['isActive'] as bool? ?? true,
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
      createdBy: data['createdBy'] as String?,
    );
  }

  Map<String, dynamic> toFirestore() => {
        'email': email,
        if (personalEmail != null && personalEmail!.isNotEmpty)
          'personalEmail': personalEmail,
        'displayName': displayName,
        'cohortId': cohortId,
        'cohortName': cohortName,
        'initialPassword': initialPassword,
        if (seatNumber != null) 'seatNumber': seatNumber,
        'passwordChanged': passwordChanged,
        'isActive': isActive,
        'intake': {
          'educationMajor': educationMajor,
          'currentStatus': currentStatus,
          'weeklyStudyHours': weeklyStudyHours,
          'programmingLevel': programmingLevel,
          'collaborationTools': collaborationTools,
          'aiLlmExperience': aiLlmExperience,
          'motivation': motivation,
          'desiredRole': desiredRole,
          'postCompletionGoal': postCompletionGoal,
          'awards': awards,
          'projectLinks': projectLinks,
          'teamRole': teamRole,
          'selfLearningStyle': selfLearningStyle,
          'slumpOvercomeExperience': slumpOvercomeExperience,
        },
        'createdAt': FieldValue.serverTimestamp(),
        if (createdBy != null) 'createdBy': createdBy,
      };
}

/// 상담 등록 폼 → Cloud Function 요청 payload
class StudentIntakeFormData {
  const StudentIntakeFormData({
    required this.displayName,
    required this.personalEmail,
    required this.cohortId,
    required this.cohortName,
    this.seatNumber,
    required this.educationMajor,
    required this.currentStatus,
    required this.weeklyStudyHours,
    required this.programmingLevel,
    required this.collaborationTools,
    required this.aiLlmExperience,
    required this.motivation,
    required this.desiredRole,
    required this.postCompletionGoal,
    required this.awards,
    required this.projectLinks,
    required this.teamRole,
    required this.selfLearningStyle,
    required this.slumpOvercomeExperience,
  });

  final String displayName;
  final String personalEmail;
  final String cohortId;
  final String cohortName;
  final int? seatNumber;
  final String educationMajor;
  final String currentStatus;
  final String weeklyStudyHours;
  final String programmingLevel;
  final String collaborationTools;
  final String aiLlmExperience;
  final String motivation;
  final String desiredRole;
  final String postCompletionGoal;
  final String awards;
  final String projectLinks;
  final String teamRole;
  final String selfLearningStyle;
  final String slumpOvercomeExperience;

  Map<String, dynamic> toJson() => {
        'displayName': displayName,
        'personalEmail': personalEmail.trim().toLowerCase(),
        'cohortId': cohortId,
        'cohortName': cohortName,
        if (seatNumber != null) 'seatNumber': seatNumber,
        'intake': {
          'educationMajor': educationMajor,
          'currentStatus': currentStatus,
          'weeklyStudyHours': weeklyStudyHours,
          'programmingLevel': programmingLevel,
          'collaborationTools': collaborationTools,
          'aiLlmExperience': aiLlmExperience,
          'motivation': motivation,
          'desiredRole': desiredRole,
          'postCompletionGoal': postCompletionGoal,
          'awards': awards,
          'projectLinks': projectLinks,
          'teamRole': teamRole,
          'selfLearningStyle': selfLearningStyle,
          'slumpOvercomeExperience': slumpOvercomeExperience,
        },
      };

  Map<String, dynamic> toUpdateJson(String uid) => {
        'uid': uid,
        ...toJson(),
      };

  factory StudentIntakeFormData.fromModel(StudentIntakeModel model) {
    return StudentIntakeFormData(
      displayName: model.displayName,
      personalEmail: model.personalEmail ?? '',
      cohortId: model.cohortId,
      cohortName: model.cohortName,
      seatNumber: model.seatNumber,
      educationMajor: model.educationMajor,
      currentStatus: model.currentStatus,
      weeklyStudyHours: model.weeklyStudyHours,
      programmingLevel: model.programmingLevel,
      collaborationTools: model.collaborationTools,
      aiLlmExperience: model.aiLlmExperience,
      motivation: model.motivation,
      desiredRole: model.desiredRole,
      postCompletionGoal: model.postCompletionGoal,
      awards: model.awards,
      projectLinks: model.projectLinks,
      teamRole: model.teamRole,
      selfLearningStyle: model.selfLearningStyle,
      slumpOvercomeExperience: model.slumpOvercomeExperience,
    );
  }
}
