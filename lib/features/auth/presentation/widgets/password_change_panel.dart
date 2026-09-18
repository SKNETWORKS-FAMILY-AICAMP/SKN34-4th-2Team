import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/errors/app_exception.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/validators.dart';
import '../../providers/auth_providers.dart';
import '../../../../core/theme/app_space.dart';

/// 비밀번호 변경 폼 — 최초 변경 / 마이페이지 공용
class PasswordChangePanel extends ConsumerStatefulWidget {
  const PasswordChangePanel({
    super.key,
    this.requireCurrentPassword = false,
    this.userEmail,
    this.showSkipButton = false,
    this.onSuccess,
    this.onSkip,
    this.compact = false,
  });

  final bool requireCurrentPassword;
  final String? userEmail;
  final bool showSkipButton;
  final VoidCallback? onSuccess;
  final VoidCallback? onSkip;
  final bool compact;

  @override
  ConsumerState<PasswordChangePanel> createState() =>
      _PasswordChangePanelState();
}

class _PasswordChangePanelState extends ConsumerState<PasswordChangePanel> {
  final _formKey = GlobalKey<FormState>();
  final _currentController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _obscureCurrent = true;
  bool _obscureNew = true;
  bool _obscureConfirm = true;
  bool _isLoading = false;

  @override
  void dispose() {
    _currentController.dispose();
    _passwordController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isLoading = true);
    try {
      final notifier = ref.read(changePasswordProvider.notifier);
      if (widget.requireCurrentPassword) {
        await notifier.changePasswordWithReauth(
          email: widget.userEmail ?? '',
          currentPassword: _currentController.text,
          newPassword: _passwordController.text,
        );
      } else {
        await notifier.changePassword(_passwordController.text);
      }
      if (mounted) {
        _currentController.clear();
        _passwordController.clear();
        _confirmController.clear();
        widget.onSuccess?.call();
      }
    } on AuthException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message)),
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _skip() async {
    setState(() => _isLoading = true);
    try {
      await ref
          .read(changePasswordProvider.notifier)
          .skipMandatoryPasswordChange();
      if (mounted) widget.onSkip?.call();
    } on AuthException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message)),
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final fieldSpacing = widget.compact ? 10.0 : 12.0;

    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.requireCurrentPassword) ...[
            _PasswordField(
              controller: _currentController,
              label: '현재 비밀번호',
              hint: '현재 비밀번호 입력',
              obscure: _obscureCurrent,
              onToggleObscure: () =>
                  setState(() => _obscureCurrent = !_obscureCurrent),
              validator: Validators.password,
            ),
            SizedBox(height: fieldSpacing),
          ],
          _PasswordField(
            controller: _passwordController,
            label: '새 비밀번호',
            hint: '새 비밀번호 입력 (6자 이상)',
            obscure: _obscureNew,
            onToggleObscure: () => setState(() => _obscureNew = !_obscureNew),
            validator: Validators.password,
          ),
          SizedBox(height: fieldSpacing),
          _PasswordField(
            controller: _confirmController,
            label: '비밀번호 확인',
            hint: '새 비밀번호 확인',
            obscure: _obscureConfirm,
            onToggleObscure: () =>
                setState(() => _obscureConfirm = !_obscureConfirm),
            validator: (v) => Validators.confirmPassword(
              v,
              _passwordController.text,
            ),
          ),
          SizedBox(height: widget.compact ? 16 : 20),
          SizedBox(
            height: AppSpace.row(40),
            child: FilledButton(
              onPressed: _isLoading ? null : _submit,
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: Colors.white,
              ),
              child: _isLoading
                  ? SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Text('비밀번호 변경'),
            ),
          ),
          if (widget.showSkipButton) ...[
            SizedBox(height: AppSpace.s(8)),
            TextButton(
              onPressed: _isLoading ? null : _skip,
              child: Text(
                '나중에 변경',
                style: TextStyle(color: AppColors.textSecondary),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _PasswordField extends StatelessWidget {
  const _PasswordField({
    required this.controller,
    required this.label,
    required this.hint,
    required this.obscure,
    required this.onToggleObscure,
    required this.validator,
  });

  final TextEditingController controller;
  final String label;
  final String hint;
  final bool obscure;
  final VoidCallback onToggleObscure;
  final String? Function(String?) validator;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
        SizedBox(height: AppSpace.s(6)),
        TextFormField(
          controller: controller,
          obscureText: obscure,
          validator: validator,
          style: const TextStyle(fontSize: 14),
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: const TextStyle(fontSize: 13),
            isDense: true,
            contentPadding: EdgeInsets.symmetric(
              horizontal: AppSpace.s(12),
              vertical: AppSpace.s(10),
            ),
            suffixIcon: IconButton(
              icon: Icon(
                obscure
                    ? Icons.visibility_off_outlined
                    : Icons.visibility_outlined,
                size: 18,
                color: AppColors.textHint,
              ),
              onPressed: onToggleObscure,
            ),
          ),
        ),
      ],
    );
  }
}

/// 마이페이지 — 접이식 비밀번호 변경 섹션
class MyPagePasswordSection extends StatelessWidget {
  const MyPagePasswordSection({
    super.key,
    required this.userEmail,
    this.initiallyExpanded = false,
  });

  final String userEmail;
  final bool initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          initiallyExpanded: initiallyExpanded,
          tilePadding: EdgeInsets.symmetric(horizontal: AppSpace.s(16), vertical: AppSpace.s(4)),
          childrenPadding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(0), AppSpace.s(16), AppSpace.s(16)),
          leading: Icon(Icons.lock_outline, color: AppColors.primary, size: 20),
          title: Text(
            '비밀번호 변경',
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w600,
              color: AppColors.primary,
            ),
          ),
          iconColor: AppColors.primary,
          collapsedIconColor: AppColors.primary,
          children: [
            PasswordChangePanel(
              requireCurrentPassword: true,
              userEmail: userEmail,
              compact: true,
              onSuccess: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('비밀번호가 변경되었습니다.')),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}
