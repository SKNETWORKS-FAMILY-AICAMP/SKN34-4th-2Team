import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/shared/constants/ai_ops_types.dart';
import 'package:playdata_lms/shared/models/ai_ops_models.dart';
import 'package:playdata_lms/shared/providers/ai_ops_providers.dart';

void main() {
  group('AiOpsTypes / outcomes', () {
    test('labels', () {
      expect(AiOpsTypes.label(AiOpsTypes.jobChat), '공고챗봇');
      expect(AiOpsTypes.label(AiOpsTypes.jobRecommend), '추천');
      expect(AiOpsTypes.label(AiOpsTypes.resumeReview), '첨삭');
      expect(AiOpsTypes.label(AiOpsTypes.assessmentQuestions), '문제생성');
      expect(AiOpsTypes.label(AiOpsTypes.studentChatbot), '학생챗봇');
    });

    test('usefulness by type', () {
      expect(
        AiOpsOutcomes.isUseful(AiOpsTypes.jobChat, AiOpsOutcomes.clickedJob),
        isTrue,
      );
      expect(
        AiOpsOutcomes.isUseful(AiOpsTypes.jobChat, AiOpsOutcomes.ignored),
        isFalse,
      );
      expect(
        AiOpsOutcomes.isUseful(
          AiOpsTypes.jobRecommend,
          AiOpsOutcomes.selectedForReview,
        ),
        isTrue,
      );
      expect(
        AiOpsOutcomes.isUseful(
          AiOpsTypes.resumeReview,
          AiOpsOutcomes.partialApply,
        ),
        isTrue,
      );
      expect(
        AiOpsOutcomes.isUseful(
          AiOpsTypes.assessmentQuestions,
          AiOpsOutcomes.adopted,
        ),
        isTrue,
      );
      expect(
        AiOpsOutcomes.isUseful(
          AiOpsTypes.assessmentQuestions,
          AiOpsOutcomes.discarded,
        ),
        isFalse,
      );
      expect(
        AiOpsOutcomes.isUseful(
          AiOpsTypes.studentChatbot,
          AiOpsOutcomes.helpful,
        ),
        isTrue,
      );
      expect(
        AiOpsOutcomes.isUseful(
          AiOpsTypes.studentChatbot,
          AiOpsOutcomes.notHelpful,
        ),
        isFalse,
      );
    });
  });

  group('filterLogsByType', () {
    AiGenerationLogModel log(String type) => AiGenerationLogModel(
          id: type,
          type: type,
          promptVersion: 'v1',
          model: 'm',
          cohortId: 'c',
        );

    test('null = all', () {
      final logs = [
        log(AiOpsTypes.jobChat),
        log(AiOpsTypes.assessmentQuestions),
      ];
      expect(filterLogsByType(logs, null), hasLength(2));
    });

    test('assessment groups regen', () {
      final logs = [
        log(AiOpsTypes.assessmentQuestions),
        log(AiOpsTypes.assessmentQuestionsRegen),
        log(AiOpsTypes.jobChat),
      ];
      final filtered = filterLogsByType(logs, 'assessment');
      expect(filtered, hasLength(2));
      expect(
        filtered.every((l) => AiOpsTypes.assessmentTypes.contains(l.type)),
        isTrue,
      );
    });

    test('exact type', () {
      final logs = [
        log(AiOpsTypes.jobChat),
        log(AiOpsTypes.jobRecommend),
        log(AiOpsTypes.studentChatbot),
      ];
      expect(filterLogsByType(logs, AiOpsTypes.jobChat).single.type,
          AiOpsTypes.jobChat);
      expect(
        filterLogsByType(logs, AiOpsTypes.studentChatbot).single.type,
        AiOpsTypes.studentChatbot,
      );
    });
  });
}
