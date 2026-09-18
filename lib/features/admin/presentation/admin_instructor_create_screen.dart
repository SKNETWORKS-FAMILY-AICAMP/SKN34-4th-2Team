import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/validators.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../data/instructor_admin_service.dart';
import 'widgets/admin_page_layout.dart';
import 'widgets/credential_dialog.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 강사 계정 생성 + 담당 기수 배정
class AdminInstructorCreateScreen extends ConsumerStatefulWidget {
  const AdminInstructorCreateScreen({super.key});

  @override
  ConsumerState<AdminInstructorCreateScreen> createState() =>
      _AdminInstructorCreateScreenState();
}

class _AdminInstructorCreateScreenState
    extends ConsumerState<AdminInstructorCreateScreen> {
  final _formKey = GlobalKey<FormState>();
  final _displayName = TextEditingController();
  final _email = TextEditingController();
  bool _isSubmitting = false;

  @override
  void dispose() {
    _displayName.dispose();
    _email.dispose();
    super.dispose();
  }

  String _errorMessage(Object e) {
    if (e is FirebaseFunctionsException) {
      return e.message ?? e.code;
    }
    return e.toString();
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
    try {
      final result = await ref
          .read(instructorAdminServiceProvider)
          .createInstructor(
            displayName: _displayName.text.trim(),
            cohortId: cohortId,
            cohortName: cohortName,
            email: _email.text.trim(),
          );
      if (!mounted) return;
      await showCredentialDialog(
        context,
        displayName: result.displayName,
        email: result.email,
        password: result.password,
        personLabel: '강사',
      );
      if (!mounted) return;
      context.go(RoutePaths.adminInstructors);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('생성 실패: ${_errorMessage(e)}')),
        );
      }
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cohortName = ref.watch(effectiveCohortNameProvider) ?? '';

    return Scaffold(
      appBar: AppBar(title: const Text('강사 등록')),
      body: adminPageWrapper(
        child: Form(
          key: _formKey,
          child: ListView(
            children: [
              AdminFormSection(
                title: '기본 정보',
                children: [
                  Text(
                    '담당 기수: ${cohortName.isEmpty ? '-' : cohortName}',
                    style: TextStyle(color: AppColors.textSecondary),
                  ),
                  SizedBox(height: AppSpace.s(12)),
                  TextFormField(
                    controller: _displayName,
                    decoration: const InputDecoration(labelText: '이름'),
                    textInputAction: TextInputAction.next,
                    validator: (v) =>
                        (v == null || v.trim().isEmpty) ? '이름을 입력하세요' : null,
                  ),
                  SizedBox(height: AppSpace.s(12)),
                  TextFormField(
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: '로그인 이메일 (선택)',
                      hintText: '비우면 playdata.co.kr 주소가 자동 생성됩니다',
                    ),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return null;
                      return Validators.email(v);
                    },
                  ),
                ],
              ),
              SizedBox(height: AppSpace.s(8)),
              FilledButton(
                onPressed: _isSubmitting ? null : _submit,
                child: _isSubmitting
                    ? SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Text('계정 생성'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
