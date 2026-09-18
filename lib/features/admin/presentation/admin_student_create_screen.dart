import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/validators.dart';
import '../../../shared/models/student_intake_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../data/student_admin_service.dart';
import '../providers/student_admin_providers.dart';
import 'widgets/admin_page_layout.dart';
import 'widgets/credential_dialog.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 상담 정보 입력 + 계정 생성 (한 화면)
class AdminStudentCreateScreen extends ConsumerStatefulWidget {
  const AdminStudentCreateScreen({super.key});

  @override
  ConsumerState<AdminStudentCreateScreen> createState() =>
      _AdminStudentCreateScreenState();
}

class _AdminStudentCreateScreenState
    extends ConsumerState<AdminStudentCreateScreen> {
  final _formKey = GlobalKey<FormState>();

  final _displayName = TextEditingController();
  final _personalEmail = TextEditingController();
  final _seatNumber = TextEditingController();
  final _educationMajor = TextEditingController();
  final _currentStatus = TextEditingController();
  final _weeklyStudyHours = TextEditingController();
  final _programmingLevel = TextEditingController();
  final _collaborationTools = TextEditingController();
  final _aiLlmExperience = TextEditingController();
  final _motivation = TextEditingController();
  final _desiredRole = TextEditingController();
  final _postCompletionGoal = TextEditingController();
  final _awards = TextEditingController();
  final _projectLinks = TextEditingController();
  final _teamRole = TextEditingController();
  final _selfLearningStyle = TextEditingController();
  final _slumpOvercome = TextEditingController();

  bool _isSubmitting = false;

  @override
  void dispose() {
    _displayName.dispose();
    _personalEmail.dispose();
    _seatNumber.dispose();
    _educationMajor.dispose();
    _currentStatus.dispose();
    _weeklyStudyHours.dispose();
    _programmingLevel.dispose();
    _collaborationTools.dispose();
    _aiLlmExperience.dispose();
    _motivation.dispose();
    _desiredRole.dispose();
    _postCompletionGoal.dispose();
    _awards.dispose();
    _projectLinks.dispose();
    _teamRole.dispose();
    _selfLearningStyle.dispose();
    _slumpOvercome.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;

    final cohortId = ref.read(effectiveCohortIdProvider);
    final cohortName = ref.read(effectiveCohortNameProvider);
    if (cohortId == null || cohortName == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('기수를 선택해주세요.')),
      );
      return;
    }

    setState(() => _isSubmitting = true);

    final seat = int.tryParse(_seatNumber.text.trim());

    final form = StudentIntakeFormData(
      displayName: _displayName.text.trim(),
      personalEmail: _personalEmail.text.trim(),
      cohortId: cohortId,
      cohortName: cohortName,
      seatNumber: seat,
      educationMajor: _educationMajor.text.trim(),
      currentStatus: _currentStatus.text.trim(),
      weeklyStudyHours: _weeklyStudyHours.text.trim(),
      programmingLevel: _programmingLevel.text.trim(),
      collaborationTools: _collaborationTools.text.trim(),
      aiLlmExperience: _aiLlmExperience.text.trim(),
      motivation: _motivation.text.trim(),
      desiredRole: _desiredRole.text.trim(),
      postCompletionGoal: _postCompletionGoal.text.trim(),
      awards: _awards.text.trim(),
      projectLinks: _projectLinks.text.trim(),
      teamRole: _teamRole.text.trim(),
      selfLearningStyle: _selfLearningStyle.text.trim(),
      slumpOvercomeExperience: _slumpOvercome.text.trim(),
    );

    try {
      final result = await ref
          .read(studentAdminServiceProvider)
          .createStudentWithIntake(form);

      ref.invalidate(cohortStudentIntakesProvider);
      ref.invalidate(cohortStudentsProvider);

      if (!mounted) return;

      await showCredentialDialog(
        context,
        displayName: result.displayName,
        email: result.email,
        password: result.password,
      );

      if (mounted) {
        context.go(RoutePaths.adminStudentDetailPath(result.uid));
      }
    } on FirebaseFunctionsException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message ?? '계정 생성 실패 (${e.code})')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('계정 생성 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cohortName = ref.watch(effectiveCohortNameProvider);

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go(RoutePaths.adminStudents),
        ),
        title: const Text('학생 상담 등록'),
      ),
      body: SingleChildScrollView(
        child: adminPageWrapper(
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  '학생 상담 등록',
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: AppColors.textPrimary,
                  ),
                ),
                SizedBox(height: AppSpace.s(6)),
                Text(
                  cohortName != null
                      ? '기수: $cohortName · 상담 내용 입력 후 계정을 생성합니다.'
                      : '상단에서 기수를 선택해주세요.',
                  style: TextStyle(
                    fontSize: 13,
                    color: AppColors.textSecondary,
                  ),
                ),
                SizedBox(height: AppSpace.s(20)),
                AdminFormSection(
                  title: '기본 정보',
                  children: [
                    TextFormField(
                      controller: _displayName,
                      decoration: const InputDecoration(
                        labelText: '이름 *',
                        hintText: '홍길동',
                      ),
                      validator: (v) =>
                          v == null || v.trim().isEmpty ? '이름을 입력하세요' : null,
                    ),
                    SizedBox(height: AppSpace.s(12)),
                    TextFormField(
                      controller: _personalEmail,
                      keyboardType: TextInputType.emailAddress,
                      decoration: const InputDecoration(
                        labelText: '개인 이메일 (Gmail) *',
                        hintText: 'student@gmail.com',
                        helperText: '구글폼 제출 시 이 이메일로 자동 매칭됩니다',
                      ),
                      validator: Validators.email,
                    ),
                    SizedBox(height: AppSpace.s(12)),
                    TextFormField(
                      controller: _seatNumber,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: '좌석 번호 (선택)',
                      ),
                    ),
                  ],
                ),
                AdminFormSection(
                  title: '1. 기본 인적 사항',
                  children: [
                    _field(_educationMajor, '학력 / 전공 *', maxLines: 2),
                    _field(_currentStatus, '현재 상태 *',
                        hint: '재학, 휴학, 직장인, 구직 등'),
                    _field(_weeklyStudyHours, '주당 학습 가능 시간 *',
                        hint: '예: 평일 3시간, 주말 6시간'),
                  ],
                ),
                AdminFormSection(
                  title: '2. 기술 역량 및 사전 준비도',
                  children: [
                    _field(_programmingLevel, '프로그래밍 언어 숙련도 *',
                        maxLines: 3),
                    _field(_collaborationTools, 'Git 등 협업 툴 *', maxLines: 2),
                    _field(_aiLlmExperience, 'AI/LLM 활용 경험 *',
                        maxLines: 3),
                  ],
                ),
                AdminFormSection(
                  title: '3. 지원 동기 및 수료 후 목표',
                  children: [
                    _field(_motivation, '지원 동기 *', maxLines: 3),
                    _field(_desiredRole, '희망 직무 *'),
                    _field(_postCompletionGoal, '수료 후 목표 *',
                        hint: '취업, 창업, 역량 강화 등', maxLines: 2),
                  ],
                ),
                AdminFormSection(
                  title: '4. 수상 경력 및 프로젝트 경험',
                  children: [
                    _field(_awards, '수상 경력 *', maxLines: 3,
                        hint: '해커톤, 경진대회 등'),
                    _field(_projectLinks, '주요 프로젝트 링크 *', maxLines: 2,
                        hint: 'GitHub, Notion 등'),
                  ],
                ),
                AdminFormSection(
                  title: '5. 협업 성향',
                  children: [
                    _field(_teamRole, '팀 프로젝트 역할 *', maxLines: 2),
                    _field(_selfLearningStyle, '자기주도 학습 방식 *',
                        maxLines: 3),
                    _field(_slumpOvercome, '슬럼프 극복 경험 *', maxLines: 3),
                  ],
                ),
                SizedBox(height: AppSpace.s(8)),
                if (_isSubmitting)
                  const Center(child: CircularProgressIndicator())
                else
                  FilledButton.icon(
                    onPressed: _submit,
                    icon: const Icon(Icons.vpn_key_outlined),
                    label: const Text('아이디 · 비밀번호 생성하기'),
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(48),
                    ),
                  ),
                SizedBox(height: AppSpace.s(24)),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _field(
    TextEditingController controller,
    String label, {
    String? hint,
    int maxLines = 1,
  }) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(12)),
      child: TextFormField(
        controller: controller,
        maxLines: maxLines,
        decoration: InputDecoration(
          labelText: label,
          hintText: hint,
          alignLabelWithHint: maxLines > 1,
        ),
        validator: (v) =>
            v == null || v.trim().isEmpty ? '${label.replaceAll(' *', '')}을(를) 입력하세요' : null,
      ),
    );
  }
}
