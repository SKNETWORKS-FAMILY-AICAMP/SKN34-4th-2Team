import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/date_utils.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/student_intake_model.dart';
import '../../../shared/providers/lms_providers.dart';
import '../data/student_admin_service.dart';
import '../providers/student_admin_providers.dart';
import 'widgets/admin_page_layout.dart';
import 'widgets/credential_dialog.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 학생 상담 상세 + 계정 정보
class AdminStudentDetailScreen extends ConsumerStatefulWidget {
  const AdminStudentDetailScreen({super.key, required this.studentUid});

  final String studentUid;

  @override
  ConsumerState<AdminStudentDetailScreen> createState() =>
      _AdminStudentDetailScreenState();
}

class _AdminStudentDetailScreenState
    extends ConsumerState<AdminStudentDetailScreen> {
  bool _isResetting = false;
  bool _isChangingStatus = false;

  Future<void> _setActiveStatus(StudentIntakeModel intake, bool active) async {
    final actionLabel = active ? '복학' : '퇴소';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('학생 $actionLabel 처리'),
        content: Text(
          active
              ? '${intake.displayName} 학생을 복학 처리하시겠습니까?\n'
                    '로그인이 다시 가능해집니다.'
              : '${intake.displayName} 학생을 퇴소 처리하시겠습니까?\n'
                    '로그인이 차단되며 재원 목록에서 숨겨집니다.\n'
                    '출결·제출 기록은 유지됩니다.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: active
                ? null
                : FilledButton.styleFrom(
                    backgroundColor: AppColors.error,
                  ),
            child: Text(actionLabel),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _isChangingStatus = true);
    try {
      await ref
          .read(studentAdminServiceProvider)
          .setStudentActiveStatus(
            uid: widget.studentUid,
            active: active,
          );

      ref.invalidate(studentIntakeDetailProvider(widget.studentUid));
      ref.invalidate(cohortStudentIntakesProvider);
      ref.invalidate(cohortStudentsProvider);

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(active ? '복학 처리되었습니다.' : '퇴소 처리되었습니다.'),
        ),
      );
      if (!active) {
        context.go(RoutePaths.adminStudents);
      }
    } on FirebaseFunctionsException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message ?? '$actionLabel 처리 실패')),
        );
      }
    } finally {
      if (mounted) setState(() => _isChangingStatus = false);
    }
  }

  Future<void> _resetPassword(StudentIntakeModel intake) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('비밀번호 재발급'),
        content: Text(
          '${intake.displayName} 학생의 비밀번호를 새로 발급하시겠습니까?\n'
          '기존 비밀번호는 더 이상 사용할 수 없습니다.',
        ),
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
    if (confirmed != true || !mounted) return;

    setState(() => _isResetting = true);
    try {
      final result = await ref
          .read(studentAdminServiceProvider)
          .resetStudentPassword(widget.studentUid);

      ref.invalidate(studentIntakeDetailProvider(widget.studentUid));

      if (!mounted) return;
      await showCredentialDialog(
        context,
        displayName: intake.displayName,
        email: intake.email,
        password: result.password,
      );
    } on FirebaseFunctionsException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message ?? '재발급 실패')),
        );
      }
    } finally {
      if (mounted) setState(() => _isResetting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final intakeAsync = ref.watch(
      studentIntakeDetailProvider(widget.studentUid),
    );

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go(RoutePaths.adminStudents),
        ),
        title: const Text('학생 상세'),
      ),
      body: intakeAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(message: e.toString()),
        data: (intake) {
          if (intake == null) {
            return const Center(child: Text('학생 정보를 찾을 수 없습니다'));
          }
          return SingleChildScrollView(
            child: adminPageWrapper(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      CircleAvatar(
                        radius: 28,
                        backgroundColor: AppColors.primaryLight,
                        child: Text(
                          intake.displayName.isNotEmpty
                              ? intake.displayName[0]
                              : '?',
                          style: TextStyle(
                            fontSize: 22,
                            color: AppColors.primary,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                      SizedBox(width: AppSpace.s(12)),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    intake.displayName,
                                    style: const TextStyle(
                                      fontSize: 20,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ),
                                if (!intake.isActive)
                                  const Chip(
                                    label: Text(
                                      '퇴소',
                                      style: TextStyle(fontSize: 11),
                                    ),
                                    visualDensity: VisualDensity.compact,
                                  ),
                              ],
                            ),
                            Text(
                              intake.cohortName,
                              style: TextStyle(
                                fontSize: 13,
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                      OutlinedButton.icon(
                        onPressed: () => context.push(
                          RoutePaths.adminStudentEditPath(widget.studentUid),
                        ),
                        icon: const Icon(Icons.edit_outlined, size: 18),
                        label: const Text('수정'),
                      ),
                    ],
                  ),
                  SizedBox(height: AppSpace.s(20)),
                  _CredentialCard(
                    intake: intake,
                    isResetting: _isResetting,
                    onReset: () => _resetPassword(intake),
                  ),
                  SizedBox(height: AppSpace.s(16)),
                  AdminFormSection(
                    title: '1. 기본 인적 사항',
                    children: [
                      AdminDetailRow(
                        label: '학력 / 전공',
                        value: intake.educationMajor,
                      ),
                      AdminDetailRow(
                        label: '현재 상태',
                        value: intake.currentStatus,
                      ),
                      AdminDetailRow(
                        label: '주당 학습 가능 시간',
                        value: intake.weeklyStudyHours,
                      ),
                    ],
                  ),
                  AdminFormSection(
                    title: '2. 기술 역량 및 사전 준비도',
                    children: [
                      AdminDetailRow(
                        label: '프로그래밍 언어 숙련도',
                        value: intake.programmingLevel,
                      ),
                      AdminDetailRow(
                        label: '협업 툴',
                        value: intake.collaborationTools,
                      ),
                      AdminDetailRow(
                        label: 'AI/LLM 활용 경험',
                        value: intake.aiLlmExperience,
                      ),
                    ],
                  ),
                  AdminFormSection(
                    title: '3. 지원 동기 및 수료 후 목표',
                    children: [
                      AdminDetailRow(
                        label: '지원 동기',
                        value: intake.motivation,
                      ),
                      AdminDetailRow(
                        label: '희망 직무',
                        value: intake.desiredRole,
                      ),
                      AdminDetailRow(
                        label: '수료 후 목표',
                        value: intake.postCompletionGoal,
                      ),
                    ],
                  ),
                  AdminFormSection(
                    title: '4. 수상 경력 및 프로젝트',
                    children: [
                      AdminDetailRow(
                        label: '수상 경력',
                        value: intake.awards,
                      ),
                      AdminDetailRow(
                        label: '프로젝트 링크',
                        value: intake.projectLinks,
                      ),
                    ],
                  ),
                  AdminFormSection(
                    title: '5. 협업 성향',
                    children: [
                      AdminDetailRow(
                        label: '팀 프로젝트 역할',
                        value: intake.teamRole,
                      ),
                      AdminDetailRow(
                        label: '자기주도 학습 방식',
                        value: intake.selfLearningStyle,
                      ),
                      AdminDetailRow(
                        label: '슬럼프 극복 경험',
                        value: intake.slumpOvercomeExperience,
                      ),
                    ],
                  ),
                  if (intake.createdAt != null)
                    Text(
                      '등록일: ${AppDateUtils.formatDisplay(intake.createdAt!)}',
                      style: TextStyle(
                        fontSize: 12,
                        color: AppColors.textSecondary,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  SizedBox(height: AppSpace.s(16)),
                  if (_isChangingStatus)
                    const Center(child: CircularProgressIndicator())
                  else if (intake.isActive)
                    OutlinedButton.icon(
                      onPressed: () => _setActiveStatus(intake, false),
                      icon: const Icon(Icons.person_off_outlined, size: 18),
                      label: const Text('퇴소 처리'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.error,
                        side: BorderSide(color: AppColors.error),
                        minimumSize: const Size.fromHeight(44),
                      ),
                    )
                  else
                    FilledButton.icon(
                      onPressed: () => _setActiveStatus(intake, true),
                      icon: const Icon(Icons.person_add_alt_1, size: 18),
                      label: const Text('복학 처리'),
                      style: FilledButton.styleFrom(
                        minimumSize: const Size.fromHeight(44),
                      ),
                    ),
                  SizedBox(height: AppSpace.s(24)),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _CredentialCard extends StatelessWidget {
  const _CredentialCard({
    required this.intake,
    required this.isResetting,
    required this.onReset,
  });

  final StudentIntakeModel intake;
  final bool isResetting;
  final VoidCallback onReset;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: AppColors.tint(const Color(0xFFF8FAFC)),
      child: Padding(
        padding: EdgeInsets.all(AppSpace.s(16)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              '로그인 계정',
              style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
            ),
            SizedBox(height: AppSpace.s(12)),
            _CopyRow(label: '아이디 (이메일)', value: intake.email),
            if (intake.personalEmail != null &&
                intake.personalEmail!.isNotEmpty) ...[
              SizedBox(height: AppSpace.s(8)),
              _CopyRow(
                label: '개인 이메일 (구글폼)',
                value: intake.personalEmail!,
              ),
            ],
            SizedBox(height: AppSpace.s(8)),
            _CopyRow(
              label: intake.passwordChanged ? '비밀번호 (학생이 변경함)' : '비밀번호',
              value: intake.passwordChanged
                  ? '변경됨 — 재발급 필요'
                  : intake.initialPassword,
              obscured: false,
            ),
            if (intake.passwordChanged) ...[
              SizedBox(height: AppSpace.s(8)),
              Text(
                '학생이 비밀번호를 변경했습니다. 잊어버린 경우 재발급하세요.',
                style: TextStyle(fontSize: 11, color: AppColors.warning),
              ),
            ],
            SizedBox(height: AppSpace.s(12)),
            OutlinedButton.icon(
              onPressed: isResetting ? null : onReset,
              icon: isResetting
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.lock_reset, size: 18),
              label: Text(intake.passwordChanged ? '비밀번호 재발급' : '비밀번호 재설정'),
            ),
          ],
        ),
      ),
    );
  }
}

class _CopyRow extends StatelessWidget {
  const _CopyRow({
    required this.label,
    required this.value,
    this.obscured = false,
  });

  final String label;
  final String value;
  final bool obscured;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  color: AppColors.textSecondary,
                ),
              ),
              SizedBox(height: AppSpace.s(2)),
              SelectableText(
                value,
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                ),
              ),
            ],
          ),
        ),
        if (!value.contains('변경됨'))
          IconButton(
            icon: const Icon(Icons.copy, size: 18),
            onPressed: () {
              Clipboard.setData(ClipboardData(text: value));
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('$label 복사됨')),
              );
            },
          ),
      ],
    );
  }
}
