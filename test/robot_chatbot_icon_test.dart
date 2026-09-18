import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:playdata_lms/core/constants/role.dart';
import 'package:playdata_lms/features/chatbot/data/student_chatbot_api_client.dart';
import 'package:playdata_lms/features/chatbot/presentation/robot_head_icon.dart';
import 'package:playdata_lms/features/chatbot/presentation/student_chatbot_host.dart';
import 'package:playdata_lms/shared/models/user_model.dart';

Future<Uint8List> _pixels(WidgetTester tester, GlobalKey key) async {
  return (await tester.runAsync(() async {
    final boundary =
        key.currentContext!.findRenderObject() as RenderRepaintBoundary;
    final image = await boundary.toImage();
    final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    image.dispose();
    return data!.buffer.asUint8List();
  }))!;
}

Future<Uint8List> _iconPixels(WidgetTester tester, Finder icon) async {
  final paint = tester.renderObject<RenderCustomPaint>(
    find.descendant(of: icon, matching: find.byType(CustomPaint)),
  );
  return (await tester.runAsync(() async {
    final recorder = ui.PictureRecorder();
    paint.painter!.paint(Canvas(recorder), paint.size);
    final picture = recorder.endRecording();
    final image = await picture.toImage(
      paint.size.width.ceil(),
      paint.size.height.ceil(),
    );
    final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    image.dispose();
    picture.dispose();
    return data!.buffer.asUint8List();
  }))!;
}

void main() {
  for (final reduced in [false, true]) {
    testWidgets(
      reduced
          ? 'reduced motion keeps the default head'
          : 'click bounce changes shape and returns automatically',
      (tester) async {
        final clicks = ValueNotifier(0);
        addTearDown(clicks.dispose);
        final key = GlobalKey();
        await tester.pumpWidget(
          MaterialApp(
            home: MediaQuery(
              data: MediaQueryData(disableAnimations: reduced),
              child: Center(
                child: RepaintBoundary(
                  key: key,
                  child: ValueListenableBuilder(
                    valueListenable: clicks,
                    builder: (context, value, child) =>
                        RobotHeadIcon(size: 104, bounce: value),
                  ),
                ),
              ),
            ),
          ),
        );
        final initial = await _pixels(tester, key);
        clicks.value++;
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 210));
        final wide = await _pixels(tester, key);
        expect(
          wide,
          reduced ? orderedEquals(initial) : isNot(orderedEquals(initial)),
        );
        // Repeated presses restart the effect instead of leaving a wide icon.
        clicks.value++;
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 710));
        expect(await _pixels(tester, key), orderedEquals(initial));
        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets('robot button opens and closes the existing student chatbot', (
    tester,
  ) async {
    final api = StudentChatbotApiClient(
      token: () async => 'test',
      baseUrl: 'https://chatbot.example',
      client: MockClient((request) async => http.Response('{}', 200)),
    );
    addTearDown(api.close);
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: StudentChatbotHost(
              user: const UserModel(
                uid: 'student',
                email: 'student@example.com',
                displayName: '학생',
                role: UserRole.student,
                cohortId: 'c1',
                cohortName: '1기',
              ),
              apiClient: api,
              child: const SizedBox.expand(),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    expect(find.byType(RobotHeadIcon), findsOneWidget);
    final launcherIcon = find.descendant(
      of: find.byType(FloatingActionButton),
      matching: find.byType(RobotHeadIcon),
    );
    final originalState = tester.state(launcherIcon);
    final originalPixels = await _iconPixels(tester, launcherIcon);
    await tester.tap(find.byType(FloatingActionButton));
    await tester.pump();
    expect(find.byKey(const Key('student-chatbot-panel')), findsOneWidget);
    expect(tester.state(launcherIcon), same(originalState));
    expect(tester.widget<RobotHeadIcon>(launcherIcon).bounce, 1);
    await tester.pump(const Duration(milliseconds: 210));
    expect(
      await _iconPixels(tester, launcherIcon),
      isNot(orderedEquals(originalPixels)),
    );
    await tester.pump(const Duration(milliseconds: 510));
    expect(
      await _iconPixels(tester, launcherIcon),
      orderedEquals(originalPixels),
    );
    expect(find.byType(RobotHeadIcon), findsNWidgets(3));
    await tester.tap(find.byType(FloatingActionButton));
    await tester.pump();
    expect(find.byKey(const Key('student-chatbot-panel')), findsNothing);
    expect(tester.widget<RobotHeadIcon>(launcherIcon).bounce, 2);
    expect(tester.state(launcherIcon), same(originalState));
    await tester.pump(const Duration(milliseconds: 210));
    expect(
      await _iconPixels(tester, launcherIcon),
      isNot(orderedEquals(originalPixels)),
    );
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 1));
    expect(tester.takeException(), isNull);
  });

  testWidgets('hovering the robot greets instead of showing the tooltip', (
    tester,
  ) async {
    final api = StudentChatbotApiClient(
      token: () async => 'test',
      baseUrl: 'https://chatbot.example',
      client: MockClient((request) async => http.Response('{}', 200)),
    );
    addTearDown(api.close);
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: StudentChatbotHost(
              user: const UserModel(
                uid: 'student',
                email: 'student@example.com',
                displayName: '학생',
                role: UserRole.student,
                cohortId: 'c1',
                cohortName: '1기',
              ),
              apiClient: api,
              child: const SizedBox.expand(),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    final semantics = tester.ensureSemantics();
    expect(find.bySemanticsLabel('학생 챗봇 열기'), findsOneWidget);
    final greeting = find.text('안녕하세요! 궁금한 점이 있으신가요? 저를 눌러 주세요!');
    expect(greeting, findsOneWidget);
    double opacity() => tester
        .widget<FadeTransition>(
          find
              .ancestor(of: greeting, matching: find.byType(FadeTransition))
              .first,
        )
        .opacity
        .value;
    expect(opacity(), 0);

    final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
    await mouse.addPointer(location: Offset.zero);
    addTearDown(() => mouse.removePointer());
    await mouse.moveTo(tester.getCenter(find.byType(FloatingActionButton)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(opacity(), 1);
    // 툴팁은 말풍선과 같은 말을 두 번 하지 않는다.
    await tester.pump(const Duration(seconds: 2));
    expect(find.text('학생 챗봇 열기'), findsNothing);

    // 로봇을 벗어나면 잦아든다.
    await mouse.moveTo(Offset.zero);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(opacity(), 0);
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });
}
