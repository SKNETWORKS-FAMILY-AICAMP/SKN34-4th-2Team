import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/date_utils.dart';
import '../../../core/utils/validators.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/user_model.dart';
import '../../../shared/widgets/profile_nav_chip.dart';
import '../../../core/errors/app_exception.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../auth/presentation/widgets/password_change_panel.dart';
import '../../auth/providers/auth_providers.dart';
import '../../../shared/models/job_preferences.dart';
import '../../onboarding/admin/admin_onboarding_steps.dart';
import '../../onboarding/instructor/instructor_onboarding_steps.dart';
import '../../onboarding/presentation/onboarding_controller.dart';
import '../../onboarding/student/student_onboarding_steps.dart';
import '../../../core/theme/app_space.dart';

/// 마이페이지 — 프로필 요약, 개인 정보, 비밀번호 변경
class MyPageScreen extends ConsumerStatefulWidget {
  const MyPageScreen({super.key});

  @override
  ConsumerState<MyPageScreen> createState() => _MyPageScreenState();
}

class _MyPageScreenState extends ConsumerState<MyPageScreen> {
  String _manualFileName(UserModel user) {
    if (user.isAdmin) return 'admin_manual.pdf';
    if (user.isInstructor) return 'instructor_manual.pdf';
    return 'student_manual.pdf';
  }

  Future<void> _openRoleManual(UserModel user) async {
    final uri = Uri.base.resolve('manuals/${_manualFileName(user)}');
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('PDF 매뉴얼을 열 수 없습니다.')),
      );
    }
  }

  Future<void> _savePersonalEmail(UserModel user, String email) async {
    try {
      await ref
          .read(lmsRepositoryProvider)
          .updatePersonalEmail(
            uid: user.uid,
            personalEmail: email,
          );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('개인 이메일이 저장되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        final message = e is DataException ? e.message : '$e';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(message)),
        );
      }
    }
  }

  Future<void> _editPersonalEmail(UserModel user) async {
    final controller = TextEditingController(text: user.personalEmail ?? '');
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('개인 이메일'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '구글폼 제출 시 이 이메일로 LMS 계정과 자동 매칭됩니다.',
              style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
            ),
            SizedBox(height: AppSpace.s(12)),
            TextField(
              controller: controller,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                hintText: 'your@gmail.com',
                labelText: 'Gmail / 개인 이메일',
              ),
              autofocus: true,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () {
              final error = Validators.email(controller.text);
              if (error != null) {
                ScaffoldMessenger.of(
                  ctx,
                ).showSnackBar(SnackBar(content: Text(error)));
                return;
              }
              Navigator.pop(ctx, true);
            },
            child: const Text('저장'),
          ),
        ],
      ),
    );
    if (saved == true) {
      await _savePersonalEmail(user, controller.text);
    }
    controller.dispose();
  }

  Future<void> _saveBirthDate(UserModel user, String birthDate) async {
    try {
      final repository = ref.read(lmsRepositoryProvider);
      await repository.updateProfile(
        uid: user.uid,
        birthDate: birthDate,
      );
      final updatedResumes = await repository.syncBirthDateToMyResumes(
        cohortId: user.cohortId,
        userId: user.uid,
        birthDate: birthDate,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              updatedResumes > 0
                  ? '생년월일을 저장하고 작성 중 이력서 $updatedResumes개에 반영했습니다.'
                  : '생년월일이 저장되었습니다.',
            ),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('저장 실패: $e')),
        );
      }
    }
  }

  Future<void> _saveSocialLink(
    UserModel user, {
    required String key,
    required String value,
  }) async {
    final links = Map<String, String>.from(user.socialLinks);
    if (value.trim().isEmpty) {
      links.remove(key);
    } else {
      links[key] = value.trim();
    }
    try {
      await ref
          .read(lmsRepositoryProvider)
          .updateProfile(
            uid: user.uid,
            socialLinks: links,
          );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('저장되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('저장 실패: $e')),
        );
      }
    }
  }

  Future<void> _pickBirthDate(UserModel user) async {
    final initial = user.birthDate != null && user.birthDate!.isNotEmpty
        ? DateTime.tryParse(user.birthDate!) ?? DateTime(2000, 1, 1)
        : DateTime(2000, 1, 1);
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(1950),
      lastDate: DateTime.now(),
    );
    if (picked == null) return;
    await _saveBirthDate(user, AppDateUtils.toDateKey(picked));
  }

  Future<void> _editLinkDialog({
    required String title,
    required String initial,
    required ValueChanged<String> onSave,
  }) async {
    final controller = TextEditingController(text: initial);
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(hintText: 'https://'),
          autofocus: true,
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
      ),
    );
    if (saved == true) onSave(controller.text);
    controller.dispose();
  }

  Future<void> _editJobPreferences(UserModel user) async {
    final result = await showDialog<JobPreferences>(
      context: context,
      builder: (ctx) => _JobPreferencesDialog(initial: user.jobPreferences),
    );
    if (result == null) return;
    try {
      await ref
          .read(lmsRepositoryProvider)
          .updateProfile(
            uid: user.uid,
            jobPreferences: result,
          );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('저장되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('저장 실패: $e')),
        );
      }
    }
  }

  void _goBack(UserModel user) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(RoutePaths.homeFor(user.role));
    }
  }

  @override
  Widget build(BuildContext context) {
    final currentUser = ref.watch(currentUserProvider);

    return currentUser.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => ErrorView(message: e.toString()),
      data: (user) {
        if (user == null) return const SizedBox.shrink();

        return Center(
          child: SingleChildScrollView(
            padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(12), AppSpace.s(20), AppSpace.s(24)),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _PageHeader(onBack: () => _goBack(user)),
                  SizedBox(height: AppSpace.s(16)),
                  _ProfileOverviewCard(user: user),
                  SizedBox(height: AppSpace.s(12)),
                  _PersonalInfoCard(
                    user: user,
                    onEditPersonalEmail: () => _editPersonalEmail(user),
                    onPickBirthDate: () => _pickBirthDate(user),
                    onEditGithub: () => _editLinkDialog(
                      title: 'GitHub URL',
                      initial: user.socialLinks['github'] ?? '',
                      onSave: (v) =>
                          _saveSocialLink(user, key: 'github', value: v),
                    ),
                    onEditBlog: () => _editLinkDialog(
                      title: '블로그 URL',
                      initial: user.socialLinks['blog'] ?? '',
                      onSave: (v) =>
                          _saveSocialLink(user, key: 'blog', value: v),
                    ),
                  ),
                  SizedBox(height: AppSpace.s(12)),
                  _JobPreferencesCard(
                    preferences: user.jobPreferences,
                    onEdit: () => _editJobPreferences(user),
                  ),
                  SizedBox(height: AppSpace.s(12)),
                  MyPagePasswordSection(
                    userEmail: user.email,
                    initiallyExpanded: user.mustChangePassword,
                  ),
                  if (user.isInstructor || user.isStudent || user.isAdmin) ...[
                    SizedBox(height: AppSpace.s(12)),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Wrap(
                        spacing: AppSpace.s(8),
                        runSpacing: AppSpace.s(4),
                        children: [
                          TextButton.icon(
                            onPressed: () async {
                              final notifier = ref.read(
                                onboardingTourProvider.notifier,
                              );
                              if (user.isInstructor) {
                                await notifier.restart(
                                  tourId: InstructorOnboarding.tourId,
                                  version: InstructorOnboarding.version,
                                  uid: user.uid,
                                  steps: InstructorOnboarding.steps,
                                );
                                if (!context.mounted) return;
                                context.go(RoutePaths.instructor);
                              } else if (user.isAdmin) {
                                await notifier.restart(
                                  tourId: AdminOnboarding.tourId,
                                  version: AdminOnboarding.version,
                                  uid: user.uid,
                                  steps: AdminOnboarding.steps,
                                );
                                if (!context.mounted) return;
                                context.go(RoutePaths.admin);
                              } else {
                                await notifier.restart(
                                  tourId: StudentOnboarding.tourId,
                                  version: StudentOnboarding.version,
                                  uid: user.uid,
                                  steps: StudentOnboarding.steps,
                                );
                                if (!context.mounted) return;
                                context.go(RoutePaths.dashboard);
                              }
                            },
                            icon: const Icon(Icons.tour_outlined, size: 18),
                            label: const Text('이용 안내 다시보기'),
                          ),
                          TextButton.icon(
                            onPressed: () => _openRoleManual(user),
                            icon: const Icon(Icons.picture_as_pdf_outlined, size: 18),
                            label: const Text('PDF 매뉴얼 보기'),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _PageHeader extends StatelessWidget {
  const _PageHeader({required this.onBack});

  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        IconButton(
          onPressed: onBack,
          icon: const Icon(Icons.arrow_back),
          style: IconButton.styleFrom(
            backgroundColor: AppColors.surfaceVariant.withValues(alpha: 0.5),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
          ),
        ),
        SizedBox(width: AppSpace.s(8)),
        const Text(
          '마이페이지',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
      ],
    );
  }
}

class _ProfileOverviewCard extends StatelessWidget {
  const _ProfileOverviewCard({required this.user});

  final UserModel user;

  String get _courseName {
    final match = RegExp(r'^(.*)\s+\d+기$').firstMatch(user.cohortName.trim());
    return match?.group(1)?.trim() ?? user.cohortName;
  }

  String get _termLabel {
    final match = RegExp(r'(\d+기)$').firstMatch(user.cohortName.trim());
    return match?.group(1) ?? '-';
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppSpace.s(20), vertical: AppSpace.s(20)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ProfileSummaryRow(
              user: user,
              avatarRadius: 32,
              showEditBadge: true,
            ),
            SizedBox(height: AppSpace.s(16)),
            Container(
              width: double.infinity,
              padding: EdgeInsets.symmetric(horizontal: AppSpace.s(14), vertical: AppSpace.s(12)),
              decoration: BoxDecoration(
                color: AppColors.surfaceVariant.withValues(alpha: 0.45),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                children: [
                  _InfoRow(label: '교육과정', value: _courseName),
                  SizedBox(height: AppSpace.s(8)),
                  _InfoRow(label: '기수', value: _termLabel),
                  SizedBox(height: AppSpace.s(8)),
                  _InfoRow(
                    label: '계정 생성일',
                    value: user.createdAt != null
                        ? AppDateUtils.formatDetailDateTime(user.createdAt!)
                        : '-',
                  ),
                  SizedBox(height: AppSpace.s(8)),
                  _InfoRow(
                    label: '마지막 로그인',
                    value: user.lastLoginAt != null
                        ? AppDateUtils.formatDetailDateTime(user.lastLoginAt!)
                        : '-',
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 88,
          child: Text(
            label,
            style: TextStyle(
              fontSize: 12,
              color: AppColors.textSecondary,
            ),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
          ),
        ),
      ],
    );
  }
}

class _PersonalInfoCard extends StatelessWidget {
  const _PersonalInfoCard({
    required this.user,
    required this.onEditPersonalEmail,
    required this.onPickBirthDate,
    required this.onEditGithub,
    required this.onEditBlog,
  });

  final UserModel user;
  final VoidCallback onEditPersonalEmail;
  final VoidCallback onPickBirthDate;
  final VoidCallback onEditGithub;
  final VoidCallback onEditBlog;

  @override
  Widget build(BuildContext context) {
    final birthLabel = user.birthDate != null && user.birthDate!.isNotEmpty
        ? user.birthDate!
        : '생년월일 선택';
    final hasPersonalEmail =
        user.personalEmail != null && user.personalEmail!.isNotEmpty;

    return Card(
      child: Padding(
        padding: EdgeInsets.all(AppSpace.s(16)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '개인 정보',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
            ),
            if (!hasPersonalEmail) ...[
              SizedBox(height: AppSpace.s(10)),
              Container(
                width: double.infinity,
                padding: EdgeInsets.all(AppSpace.s(10)),
                decoration: BoxDecoration(
                  color: AppColors.warning.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  '개인 이메일이 등록되지 않았습니다. 구글폼 제출 연동을 위해 등록해 주세요.',
                  style: TextStyle(fontSize: 11, color: AppColors.warning),
                ),
              ),
            ],
            SizedBox(height: AppSpace.s(14)),
            _LinkRow(
              icon: Icons.mail_outline,
              label: '개인 이메일 (구글폼)',
              url: user.personalEmail,
              emptyLabel: '등록된 이메일 없음',
              onEdit: onEditPersonalEmail,
            ),
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpace.s(12)),
              child: Divider(height: 1),
            ),
            const Text(
              '생년월일',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
            SizedBox(height: AppSpace.s(6)),
            InkWell(
              onTap: onPickBirthDate,
              borderRadius: BorderRadius.circular(8),
              child: Container(
                width: double.infinity,
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpace.s(12),
                  vertical: AppSpace.s(10),
                ),
                decoration: BoxDecoration(
                  border: Border.all(color: AppColors.border),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.calendar_today_outlined,
                      size: 16,
                      color: AppColors.textHint,
                    ),
                    SizedBox(width: AppSpace.s(8)),
                    Text(
                      birthLabel,
                      style: TextStyle(
                        fontSize: 13,
                        color:
                            user.birthDate != null && user.birthDate!.isNotEmpty
                            ? AppColors.textPrimary
                            : AppColors.textHint,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpace.s(12)),
              child: Divider(height: 1),
            ),
            _LinkRow(
              icon: Icons.code,
              label: 'GitHub',
              url: user.socialLinks['github'],
              onEdit: onEditGithub,
            ),
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpace.s(12)),
              child: Divider(height: 1),
            ),
            _LinkRow(
              icon: Icons.article_outlined,
              label: '블로그',
              url: user.socialLinks['blog'],
              onEdit: onEditBlog,
            ),
          ],
        ),
      ),
    );
  }
}

class _LinkRow extends StatelessWidget {
  const _LinkRow({
    required this.icon,
    required this.label,
    required this.url,
    required this.onEdit,
    this.emptyLabel = '등록된 링크 없음',
  });

  final IconData icon;
  final String label;
  final String? url;
  final VoidCallback onEdit;
  final String emptyLabel;

  @override
  Widget build(BuildContext context) {
    final hasUrl = url != null && url!.isNotEmpty;
    final isHttpUrl = hasUrl && url!.startsWith('http');

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 18, color: AppColors.textSecondary),
        SizedBox(width: AppSpace.s(8)),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
              SizedBox(height: AppSpace.s(4)),
              if (hasUrl)
                isHttpUrl
                    ? InkWell(
                        onTap: () => launchUrl(Uri.parse(url!)),
                        child: Text(
                          url!,
                          style: TextStyle(
                            fontSize: 12,
                            color: AppColors.primary,
                            decoration: TextDecoration.underline,
                          ),
                        ),
                      )
                    : Text(
                        url!,
                        style: TextStyle(
                          fontSize: 12,
                          color: AppColors.textPrimary,
                        ),
                      )
              else
                Text(
                  emptyLabel,
                  style: TextStyle(fontSize: 12, color: AppColors.textHint),
                ),
            ],
          ),
        ),
        IconButton(
          onPressed: onEdit,
          icon: const Icon(Icons.edit_outlined, size: 18),
          visualDensity: VisualDensity.compact,
          tooltip: '수정',
        ),
      ],
    );
  }
}

/// 취업 희망 조건 카드. 이력서 문서에는 찍히지 않고 맞춤 공고 추천에만 쓰인다.
class _JobPreferencesCard extends StatelessWidget {
  const _JobPreferencesCard({required this.preferences, required this.onEdit});

  final JobPreferences preferences;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: EdgeInsets.all(AppSpace.s(16)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    '취업 희망 조건',
                    style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                  ),
                ),
                IconButton(
                  onPressed: onEdit,
                  icon: const Icon(Icons.edit_outlined, size: 18),
                  visualDensity: VisualDensity.compact,
                  tooltip: '수정',
                ),
              ],
            ),
            SizedBox(height: AppSpace.s(4)),
            Text(
              '이력서에는 표시되지 않고 커리어 코치의 맞춤 공고 추천에만 쓰입니다.',
              style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
            ),
            SizedBox(height: AppSpace.s(12)),
            _PreferenceRow(label: '희망 직무', values: preferences.targetRoles),
            SizedBox(height: AppSpace.s(10)),
            _PreferenceRow(label: '희망 근무지역', values: preferences.regions),
            SizedBox(height: AppSpace.s(10)),
            _PreferenceRow(
              label: '희망 고용형태',
              values: preferences.employmentTypes,
            ),
          ],
        ),
      ),
    );
  }
}

class _PreferenceRow extends StatelessWidget {
  const _PreferenceRow({required this.label, required this.values});

  final String label;
  final List<String> values;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
        ),
        SizedBox(height: AppSpace.s(4)),
        if (values.isEmpty)
          Text(
            '미입력',
            style: TextStyle(fontSize: 12, color: AppColors.textHint),
          )
        else
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final value in values)
                Chip(
                  label: Text(value),
                  labelStyle: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                  backgroundColor: AppColors.primaryLight,
                  side: BorderSide.none,
                  visualDensity: VisualDensity.compact,
                ),
            ],
          ),
      ],
    );
  }
}

/// 직무·지역·고용형태를 태그로 고르는 편집 대화상자.
/// 선택지는 공고 데이터의 표기와 맞춰 두어 하드 필터 문자열 비교에 걸리게 한다.
class _JobPreferencesDialog extends StatefulWidget {
  const _JobPreferencesDialog({required this.initial});

  final JobPreferences initial;

  @override
  State<_JobPreferencesDialog> createState() => _JobPreferencesDialogState();
}

class _JobPreferencesDialogState extends State<_JobPreferencesDialog> {
  late Set<String> _roles = widget.initial.targetRoles.toSet();
  late Set<String> _regions = widget.initial.regions.toSet();
  late Set<String> _employmentTypes = widget.initial.employmentTypes.toSet();

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('취업 희망 조건'),
      content: SizedBox(
        width: 420,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ChoiceGroup(
                label: '희망 직무',
                options: JobPreferenceOptions.roles,
                selected: _roles,
                onChanged: (next) => setState(() => _roles = next),
              ),
              SizedBox(height: AppSpace.s(14)),
              _ChoiceGroup(
                label: '희망 근무지역',
                options: JobPreferenceOptions.regions,
                selected: _regions,
                onChanged: (next) => setState(() => _regions = next),
              ),
              SizedBox(height: AppSpace.s(14)),
              _ChoiceGroup(
                label: '희망 고용형태',
                options: JobPreferenceOptions.employmentTypes,
                selected: _employmentTypes,
                onChanged: (next) => setState(() => _employmentTypes = next),
              ),
              SizedBox(height: AppSpace.s(8)),
              Text(
                '비워 두면 해당 조건으로 거르지 않습니다.',
                style: TextStyle(fontSize: 11, color: AppColors.textHint),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('취소'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(
            context,
            JobPreferences(
              targetRoles: JobPreferenceOptions.roles
                  .where(_roles.contains)
                  .toList(),
              regions: JobPreferenceOptions.regions
                  .where(_regions.contains)
                  .toList(),
              employmentTypes: JobPreferenceOptions.employmentTypes
                  .where(_employmentTypes.contains)
                  .toList(),
            ),
          ),
          child: const Text('저장'),
        ),
      ],
    );
  }
}

class _ChoiceGroup extends StatelessWidget {
  const _ChoiceGroup({
    required this.label,
    required this.options,
    required this.selected,
    required this.onChanged,
  });

  final String label;
  final List<String> options;
  final Set<String> selected;
  final ValueChanged<Set<String>> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
        ),
        SizedBox(height: AppSpace.s(6)),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final option in options)
              FilterChip(
                label: Text(option),
                selected: selected.contains(option),
                showCheckmark: false,
                onSelected: (on) {
                  final next = {...selected};
                  if (on) {
                    next.add(option);
                  } else {
                    next.remove(option);
                  }
                  onChanged(next);
                },
              ),
          ],
        ),
      ],
    );
  }
}
