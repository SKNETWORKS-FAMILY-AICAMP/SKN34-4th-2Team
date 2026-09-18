import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/widgets/app_dropdown.dart';
import '../../../../shared/models/resume_content.dart';
import '../../../../shared/providers/cohort_providers.dart';
import '../data/generated/resume_mocks.g.dart';
import '../models/resume_mock_persona.dart';

/// 빈 이력서에 가상 이력서를 채워 넣는 개발용 메뉴.
///
/// 시드 스크립트 없이 로그인한 계정 그대로 이력서 편집 화면에서 고른다.
/// 채우기만 하고 저장은 하지 않는다 — 사용자가 내용을 보고 '저장'을 눌러야
/// Firestore에 남는다. 디버그 빌드에서만 보인다.
class ResumeMockMenu extends ConsumerWidget {
  const ResumeMockMenu({super.key, required this.onPick});

  /// 고른 목업의 제목과 본문. 호출한 쪽이 상태에 반영하고 dirty 표시를 한다.
  final void Function(String title, ResumeContent content) onPick;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!kDebugMode) return const SizedBox.shrink();
    final user = ref.watch(currentUserSyncProvider);
    return AppIconMenu<ResumeMockPersona>(
      tooltip: '목업 이력서 채우기 (개발용)',
      icon: const Icon(Icons.science_outlined),
      onSelected: (persona) {
        onPick(
          persona.title,
          persona.toContent(
            name: user?.displayName ?? '',
            email: user?.email ?? '',
          ),
        );
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('${persona.title} 로 채웠습니다. 저장을 눌러야 반영됩니다.'),
          ),
        );
      },
      items: [
        for (final persona in resumeMockPersonas)
          AppMenuAction(value: persona, label: persona.title),
      ],
    );
  }
}
