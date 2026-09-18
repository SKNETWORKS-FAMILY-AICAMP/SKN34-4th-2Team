import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/app_dropdown.dart';
import '../../../core/widgets/in_page_header.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/user_model.dart';
import '../../../shared/providers/lms_providers.dart';
import '../data/instructor_admin_service.dart';
import 'widgets/admin_page_layout.dart';
import 'widgets/credential_dialog.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 강사 계정 목록 / 기수 배정 / 활성 상태
class AdminInstructorsScreen extends ConsumerWidget {
  const AdminInstructorsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final instructors = ref.watch(instructorsStreamProvider);

    return Scaffold(
      body: Column(
        children: [
          InPageHeader(
            actions: [
              Padding(
                padding: EdgeInsets.only(right: AppSpace.s(8)),
                child: FilledButton.icon(
                  onPressed: () =>
                      context.push(RoutePaths.adminInstructorsCreate),
                  icon: const Icon(Icons.person_add, size: 18),
                  label: const Text('강사 등록'),
                ),
              ),
            ],
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async =>
                  ref.invalidate(instructorsStreamProvider),
              child: instructors.when(
                loading: () =>
                    const Center(child: CircularProgressIndicator()),
                error: (e, _) => ErrorView(
                  message: e.toString(),
                  onRetry: () => ref.invalidate(instructorsStreamProvider),
                ),
                data: (list) {
            if (list.isEmpty) {
              return ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.all(AdminPageLayout.padding),
                children: [
                  EmptyView(
                    message: '등록된 강사가 없습니다.',
                    icon: Icons.school_outlined,
                    actionLabel: '강사 등록',
                    onAction: () =>
                        context.push(RoutePaths.adminInstructorsCreate),
                  ),
                ],
              );
            }

            return ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: EdgeInsets.all(AppSpace.s(16)),
              itemCount: list.length,
              separatorBuilder: (_, _) => SizedBox(height: AppSpace.s(8)),
              itemBuilder: (_, i) => _InstructorTile(instructor: list[i]),
            );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _InstructorTile extends ConsumerWidget {
  const _InstructorTile({required this.instructor});

  final UserModel instructor;

  String _errorMessage(Object e) {
    if (e is FirebaseFunctionsException) {
      return e.message ?? e.code;
    }
    return e.toString();
  }

  Future<void> _edit(BuildContext context, WidgetRef ref) async {
    final cohorts = ref.read(cohortsStreamProvider).asData?.value ?? [];
    final nameCtrl = TextEditingController(text: instructor.displayName);
    var cohortId = instructor.cohortId;

    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) {
          final selected = cohorts.any((c) => c.cohortId == cohortId)
              ? cohortId
              : (cohorts.isNotEmpty ? cohorts.first.cohortId : null);
          return AlertDialog(
            title: const Text('강사 정보 수정'),
            content: SizedBox(
              width: 360,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: nameCtrl,
                    decoration: const InputDecoration(labelText: '이름'),
                  ),
                  SizedBox(height: AppSpace.s(12)),
                  AppDropdownField<String>(
                    key: ValueKey(selected),
                    value: selected,
                    decoration: const InputDecoration(labelText: '담당 기수'),
                    items: [
                      for (final c in cohorts)
                        AppDropdownItem(value: c.cohortId, label: c.name),
                    ],
                    onChanged: (v) {
                      if (v != null) setDialogState(() => cohortId = v);
                    },
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('취소'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('저장'),
              ),
            ],
          );
        },
      ),
    );

    if (saved != true || !context.mounted) return;
    final name = nameCtrl.text.trim();
    if (name.isEmpty) return;

    final cohort = cohorts.where((c) => c.cohortId == cohortId).firstOrNull;
    try {
      await ref.read(instructorAdminServiceProvider).updateInstructor(
            uid: instructor.uid,
            displayName: name,
            cohortId: cohortId,
            cohortName: cohort?.name ?? instructor.cohortName,
          );
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('강사 정보가 저장되었습니다.')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('저장 실패: ${_errorMessage(e)}')),
        );
      }
    }
  }

  Future<void> _resetPassword(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('비밀번호 재발급'),
        content: Text('${instructor.displayName} 강사의 비밀번호를 재발급할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('재발급'),
          ),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;

    try {
      final result =
          await ref.read(instructorAdminServiceProvider).resetPassword(
                instructor.uid,
              );
      if (!context.mounted) return;
      await showCredentialDialog(
        context,
        displayName: instructor.displayName,
        email: instructor.email,
        password: result.password,
        personLabel: '강사',
      );
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('재발급 실패: ${_errorMessage(e)}')),
        );
      }
    }
  }

  Future<void> _toggleActive(BuildContext context, WidgetRef ref) async {
    final next = !instructor.isActive;
    try {
      await ref.read(instructorAdminServiceProvider).setActiveStatus(
            uid: instructor.uid,
            active: next,
          );
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(next ? '활성화했습니다.' : '비활성화했습니다.')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('변경 실패: ${_errorMessage(e)}')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: AppColors.primaryLight,
          child: Text(
            instructor.displayName.isNotEmpty
                ? instructor.displayName.characters.first
                : '강',
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
        title: Text(instructor.displayName),
        subtitle: Text(
          [
            instructor.email,
            instructor.cohortName,
            instructor.isActive ? '활성' : '비활성',
          ].where((s) => s.isNotEmpty).join(' · '),
        ),
        trailing: AppIconMenu<String>(
          onSelected: (value) {
            switch (value) {
              case 'edit':
                _edit(context, ref);
              case 'reset':
                _resetPassword(context, ref);
              case 'toggle':
                _toggleActive(context, ref);
            }
          },
          items: [
            const AppMenuAction(value: 'edit', label: '정보 수정'),
            const AppMenuAction(value: 'reset', label: '비밀번호 재발급'),
            AppMenuAction(
              value: 'toggle',
              label: instructor.isActive ? '비활성화' : '활성화',
            ),
          ],
        ),
      ),
    );
  }
}
