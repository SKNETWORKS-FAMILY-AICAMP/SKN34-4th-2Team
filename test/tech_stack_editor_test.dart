import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:playdata_lms/features/resume/presentation/widgets/skill_catalog.dart';
import 'package:playdata_lms/features/resume/presentation/widgets/tech_stack_editor.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';
import 'package:playdata_lms/shared/models/tech_skill_level.dart';

void main() {
  group('SkillCatalog', () {
    test('기본 목록과 수집 공고 기술을 표기 중복 없이 합친다', () {
      final lower = SkillCatalog.all.map((s) => s.toLowerCase()).toList();
      expect(lower.toSet().length, lower.length);
      expect(SkillCatalog.all, contains('Python'));
      expect(SkillCatalog.all.length, greaterThanOrEqualTo(SkillCatalog.baseSkills.length));
    });

    test('검색은 앞글자 일치를 먼저, 포함 일치를 뒤에 둔다', () {
      final results = SkillCatalog.search('py');
      expect(results.first.toLowerCase(), startsWith('py'));
      expect(results, contains('NumPy'));
      expect(results.indexOf('Python'), lessThan(results.indexOf('NumPy')));
    });

    test('같은 기술의 다른 표기는 하나만 남는다', () {
      // 기본 목록은 영문, 공고 태그는 한글이라 그대로 두면 둘 다 선택지에 나온다.
      // 이력서에 적히는 이름이라 영문을 남긴다. 추천은 벡터라 표기가 달라도 걸린다.
      expect(SkillCatalog.all, contains('Deep Learning'));
      expect(SkillCatalog.all, isNot(contains('딥러닝')));
      expect(SkillCatalog.all, contains('Machine Learning'));
      expect(SkillCatalog.all, isNot(contains('머신러닝')));
    });

    test('한글로 적어도 영문 표기로 맞춰 준다', () {
      // 예전에 저장된 이력서나 직접 입력한 값이 선택지에 없는 채로 남지 않게 한다.
      expect(SkillCatalog.canonical('딥러닝'), 'Deep Learning');
      expect(SkillCatalog.canonical('머신러닝'), 'Machine Learning');
      expect(SkillCatalog.canonical('NLP(자연어처리)'), 'NLP');
    });

    test('이름만 비슷하고 다른 제품은 합치지 않는다', () {
      // Power BI(시각화)와 파워빌더(개발도구)는 다른 것이다.
      expect(SkillCatalog.all, contains('Power BI'));
      expect(SkillCatalog.all, contains('파워빌더'));
    });

    test('대소문자만 다른 입력은 후보 표기로 맞춘다', () {
      expect(SkillCatalog.canonical('python'), 'Python');
      expect(SkillCatalog.canonical('  Neo4j '), 'Neo4j');
      expect(SkillCatalog.canonical('MyOwnTool'), 'MyOwnTool');
    });
  });

  group('techSkillLevelOf', () {
    test('저장된 단계 이름을 찾고, 옛 자유 입력은 null', () {
      expect(techSkillLevelOf('중급')?.description, isNotEmpty);
      expect(techSkillLevelOf('3'), isNull);
      expect(techSkillLevelOf(''), isNull);
    });
  });

  group('TechStackEditor', () {
    testWidgets('태그를 누르면 추가되고, 숙련도 단계를 설명과 함께 고른다', (tester) async {
      var items = <ResumeTechStackItem>[];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: StatefulBuilder(
                builder: (context, setState) => TechStackEditor(
                  items: items,
                  readOnly: false,
                  onChanged: (next) => setState(() => items = next),
                ),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.widgetWithText(FilterChip, 'Python'));
      await tester.pumpAndSettle();
      expect(items.map((e) => e.name), ['Python']);
      // 방금 추가한 기술의 숙련도 선택 영역이 열린다.
      expect(find.text('Python 숙련도'), findsOneWidget);
      expect(find.text('프로젝트에 실제로 사용해 기능을 완성했다'), findsOneWidget);

      await tester.tap(find.text('중급'));
      await tester.pumpAndSettle();
      expect(items.single.level, '중급');
      expect(find.widgetWithText(InputChip, 'Python · 중급'), findsOneWidget);
    });

    testWidgets('직접 입력한 기술은 Enter로 추가되고 중복은 막는다', (tester) async {
      var items = <ResumeTechStackItem>[
        const ResumeTechStackItem(id: 't1', name: 'Python', level: '초급'),
      ];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: StatefulBuilder(
                builder: (context, setState) => TechStackEditor(
                  items: items,
                  readOnly: false,
                  onChanged: (next) => setState(() => items = next),
                ),
              ),
            ),
          ),
        ),
      );

      await tester.enterText(find.byType(TextField), 'MyInternalTool');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();
      expect(items.map((e) => e.name), ['Python', 'MyInternalTool']);

      await tester.enterText(find.byType(TextField), 'python');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();
      expect(items.length, 2);
    });

    testWidgets('읽기 전용에서는 태그와 숙련도만 보여준다', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: TechStackEditor(
              items: const [
                ResumeTechStackItem(id: 't1', name: 'Flutter', level: '고급'),
              ],
              readOnly: true,
              onChanged: (_) {},
            ),
          ),
        ),
      );
      expect(find.text('Flutter · 고급'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
    });
  });
}
