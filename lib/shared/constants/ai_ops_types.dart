/// LLMOps type / outcome 계약. Functions `aiOps.ts` 와 맞춰 둔다.
abstract final class AiOpsTypes {
  static const assessmentQuestions = 'assessment_questions';
  static const assessmentQuestionsRegen = 'assessment_questions_regen';
  static const jobChat = 'job_chat';
  static const jobRecommend = 'job_recommend';
  static const resumeReview = 'resume_review';
  static const studentChatbot = 'student_chatbot';

  static const coachTypes = {jobChat, jobRecommend, resumeReview};
  static const assessmentTypes = {
    assessmentQuestions,
    assessmentQuestionsRegen,
  };

  static String label(String type) => switch (type) {
    assessmentQuestions || assessmentQuestionsRegen => '문제생성',
    jobChat => '공고챗봇',
    jobRecommend => '추천',
    resumeReview => '첨삭',
    studentChatbot => '학생챗봇',
    _ => type,
  };
}

abstract final class AiOpsOutcomes {
  // assessment
  static const adopted = 'adopted';
  static const edited = 'edited';
  static const discarded = 'discarded';
  // job_chat
  static const clickedJob = 'clicked_job';
  static const followedUp = 'followed_up';
  static const ignored = 'ignored';
  // job_recommend
  static const opened = 'opened';
  static const selectedForReview = 'selected_for_review';
  static const dismissed = 'dismissed';
  // resume_review
  static const applied = 'applied';
  static const partialApply = 'partial_apply';
  static const undone = 'undone';
  static const abandoned = 'abandoned';
  // student_chatbot
  static const helpful = 'helpful';
  static const notHelpful = 'not_helpful';

  /// 기능별 "유용"으로 집계할 outcome
  static bool isUseful(String type, String outcome) {
    if (AiOpsTypes.assessmentTypes.contains(type) ||
        type.isEmpty &&
            (outcome == adopted || outcome == edited)) {
      return outcome == adopted || outcome == edited;
    }
    return switch (type) {
      AiOpsTypes.jobChat =>
        outcome == clickedJob || outcome == followedUp,
      AiOpsTypes.jobRecommend =>
        outcome == opened || outcome == selectedForReview,
      AiOpsTypes.resumeReview =>
        outcome == applied ||
            outcome == partialApply ||
            outcome == undone,
      AiOpsTypes.studentChatbot => outcome == helpful,
      _ => outcome == adopted || outcome == edited,
    };
  }
}

/// 서버·앱이 공유하는 기본 프롬프트 버전 (응답에 없으면 fallback).
abstract final class AiOpsPromptVersions {
  static const jobChat = 'job_chat_v1';
  static const jobRecommend = 'job_recommend_v1';
  static const resumeReview = 'resume_review_v1';
  static const studentChatbot = 'student_chatbot_v2';
}
