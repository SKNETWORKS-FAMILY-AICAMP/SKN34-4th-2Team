import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/shared/widgets/app_side_rail.dart';

/// 온보딩이 도는 동안 관리자 사이드바는 모든 그룹을 펼쳐야 한다. 접힌 그룹의
/// 메뉴는 화면에 없어서 안내가 비출 대상을 찾지 못한다.
List<AppSideRailSection> _sections({required bool expandAll}) => [
  AppSideRailSection(
    id: 'home',
    initiallyExpanded: true,
    items: const [
      AppSideRailItem(
        icon: Icons.dashboard_rounded,
        label: '대시보드',
        path: '/admin',
      ),
    ],
  ),
  AppSideRailSection(
    id: 'people',
    title: '운영 · 인원',
    initiallyExpanded: expandAll,
    items: const [
      AppSideRailItem(
        icon: Icons.group_rounded,
        label: '학생 관리',
        path: '/admin/students',
      ),
    ],
  ),
  AppSideRailSection(
    id: 'content',
    title: '학습 · 콘텐츠',
    initiallyExpanded: expandAll,
    items: const [
      AppSideRailItem(
        icon: Icons.forum_rounded,
        label: '게시판',
        path: '/admin/board',
      ),
    ],
  ),
];

Future<void> _pumpRail(
  WidgetTester tester, {
  required bool expandAll,
  String location = '/admin',
}) async {
  await tester.pumpWidget(
    ProviderScope(
      child: MaterialApp(
        home: Scaffold(
          body: AppSideRail(
            sections: _sections(expandAll: expandAll),
            location: location,
            onNavigate: (_) {},
          ),
        ),
      ),
    ),
  );
  // 사이드바 색 설정을 읽는 타이머가 있다. 재우고 나가야 테스트가 깨끗하다.
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a later expand-all opens the groups, and ending closes them', (
    tester,
  ) async {
    await _pumpRail(tester, expandAll: false);
    expect(find.text('학생 관리'), findsNothing);
    expect(find.text('게시판'), findsNothing);

    // 투어가 시작된다. 첫 프레임 다음이라 이 목록은 이미 만들어져 있다.
    await _pumpRail(tester, expandAll: true);
    expect(find.text('학생 관리'), findsOneWidget);
    expect(find.text('게시판'), findsOneWidget);

    // 투어가 끝나면 원래대로 접힌다.
    await _pumpRail(tester, expandAll: false);
    expect(find.text('학생 관리'), findsNothing);
    expect(find.text('게시판'), findsNothing);
  });

  testWidgets('a group the user opened stays open after the tour', (
    tester,
  ) async {
    await _pumpRail(tester, expandAll: false);
    await tester.tap(find.text('운영 · 인원'));
    await tester.pumpAndSettle();
    expect(find.text('학생 관리'), findsOneWidget);

    await _pumpRail(tester, expandAll: true);
    await _pumpRail(tester, expandAll: false);

    expect(find.text('학생 관리'), findsOneWidget);
    expect(find.text('게시판'), findsNothing);
  });

  testWidgets('the group holding the current menu is never closed', (
    tester,
  ) async {
    await _pumpRail(tester, expandAll: false);
    await _pumpRail(tester, expandAll: true, location: '/admin/board');
    expect(find.text('게시판'), findsOneWidget);

    await _pumpRail(tester, expandAll: false, location: '/admin/board');
    expect(find.text('게시판'), findsOneWidget);
    expect(find.text('학생 관리'), findsNothing);
  });
}
