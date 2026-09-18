import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/errors/app_exception.dart';
import '../../../core/utils/validators.dart';
import '../../../shared/demo/demo_accounts.dart';
import '../providers/auth_providers.dart';
import '../providers/login_exit_hold_provider.dart';
import 'widgets/login_brand_stage.dart';
import 'widgets/login_fixed_frame.dart';

/// 폐쇄형 로그인 화면 — 시네마틱 다크 스테이지
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen>
    with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _obscurePassword = true;
  bool _isLoading = false;
  bool _showQuickLogin = false;
  bool _loginSucceeded = false;

  late final AnimationController _exitCtrl;
  late final Animation<double> _fadeOut;
  late final Animation<double> _scaleDown;

  @override
  void initState() {
    super.initState();
    _exitCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 820),
    );
    _fadeOut = CurvedAnimation(
      parent: _exitCtrl,
      curve: const Interval(0, 0.45, curve: Curves.easeInCubic),
    );
    _scaleDown = Tween<double>(begin: 1, end: 0.94).animate(
      CurvedAnimation(
        parent: _exitCtrl,
        curve: const Interval(0, 0.4, curve: Curves.easeInOutCubic),
      ),
    );
  }

  @override
  void dispose() {
    _exitCtrl.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _quickLogin(String email, String password) async {
    _emailController.text = email;
    _passwordController.text = password;
    await _handleLogin();
  }

  Future<void> _handleLogin() async {
    if (!_formKey.currentState!.validate()) return;
    if (_isLoading || _loginSucceeded) return;

    setState(() => _isLoading = true);
    ref.read(loginExitHoldProvider.notifier).hold();

    try {
      final user = await ref
          .read(signInProvider.notifier)
          .signIn(_emailController.text, _passwordController.text);
      if (!mounted) return;

      // 비밀번호 변경 강제면 연출 생략하고 바로 이동
      if (user.mustChangePassword) {
        ref.read(loginExitHoldProvider.notifier).release();
        return;
      }

      setState(() {
        _isLoading = false;
        _loginSucceeded = true;
      });
      await _exitCtrl.forward();
      if (!mounted) return;
      ref.read(loginExitHoldProvider.notifier).release();
    } on AuthException catch (e) {
      ref.read(loginExitHoldProvider.notifier).release();
      if (mounted) {
        setState(() => _isLoading = false);
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (e) {
      ref.read(loginExitHoldProvider.notifier).release();
      if (mounted) {
        setState(() => _isLoading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('로그인 중 오류: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF05070F),
      resizeToAvoidBottomInset: false,
      body: LoginFixedFrame(
        child: Stack(
          children: [
            Positioned.fill(
              child: LoginBrandStage(
                exiting: _loginSucceeded,
                exitProgress: _exitCtrl,
              ),
            ),
            Positioned.fill(
              child: AnimatedBuilder(
                animation: _exitCtrl,
                builder: (context, child) {
                  return Opacity(
                    opacity: 1 - _fadeOut.value,
                    child: Transform.scale(
                      scale: _scaleDown.value,
                      alignment: Alignment.centerLeft,
                      child: child,
                    ),
                  );
                },
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final minHeight = (constraints.maxHeight - 48)
                        .clamp(0.0, double.infinity);
                    return SingleChildScrollView(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 48,
                        vertical: 24,
                      ),
                      child: ConstrainedBox(
                        constraints: BoxConstraints(minHeight: minHeight),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: SizedBox(
                            width: 400,
                            child: _LoginCard(
                              formKey: _formKey,
                              emailController: _emailController,
                              passwordController: _passwordController,
                              obscurePassword: _obscurePassword,
                              isLoading: _isLoading,
                              loginSucceeded: _loginSucceeded,
                              showQuickLogin: _showQuickLogin,
                              onToggleObscure: () => setState(
                                () => _obscurePassword = !_obscurePassword,
                              ),
                              onToggleQuickLogin: () => setState(
                                () => _showQuickLogin = !_showQuickLogin,
                              ),
                              onLogin: _handleLogin,
                              onQuickLogin: _quickLogin,
                            ),
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoginCard extends StatelessWidget {
  const _LoginCard({
    required this.formKey,
    required this.emailController,
    required this.passwordController,
    required this.obscurePassword,
    required this.isLoading,
    required this.loginSucceeded,
    required this.showQuickLogin,
    required this.onToggleObscure,
    required this.onToggleQuickLogin,
    required this.onLogin,
    required this.onQuickLogin,
  });

  final GlobalKey<FormState> formKey;
  final TextEditingController emailController;
  final TextEditingController passwordController;
  final bool obscurePassword;
  final bool isLoading;
  final bool loginSucceeded;
  final bool showQuickLogin;
  final VoidCallback onToggleObscure;
  final VoidCallback onToggleQuickLogin;
  final VoidCallback onLogin;
  final Future<void> Function(String email, String password) onQuickLogin;

  @override
  Widget build(BuildContext context) {
    const titleColor = Colors.white;
    final muted = Colors.white.withValues(alpha: 0.6);
    final hint = Colors.white.withValues(alpha: 0.38);
    final fieldFill = Colors.white.withValues(alpha: 0.06);

    final fieldTheme = Theme.of(context).copyWith(
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: fieldFill,
        hintStyle: TextStyle(color: hint, fontSize: 14),
        labelStyle: TextStyle(color: muted),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Colors.white24),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Colors.white24),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(
            color: Color(0xFF00C2D4),
            width: 1.5,
          ),
        ),
      ),
    );

    return Container(
      padding: const EdgeInsets.fromLTRB(28, 32, 28, 28),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.35),
            blurRadius: 40,
            offset: const Offset(0, 16),
          ),
        ],
      ),
      child: Theme(
        data: fieldTheme,
        child: Form(
          key: formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Log in',
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.w800,
                  color: titleColor,
                  height: 1.2,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Welcome to ${AppConstants.appName}',
                style: TextStyle(fontSize: 14, color: muted),
              ),
              const SizedBox(height: 32),
              Text(
                '사용자 아이디',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                  color: muted,
                ),
              ),
              const SizedBox(height: 8),
              TextFormField(
                controller: emailController,
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
                style: const TextStyle(color: titleColor),
                decoration: const InputDecoration(
                  hintText: '이메일을 입력하세요',
                ),
                validator: Validators.email,
              ),
              const SizedBox(height: 18),
              Text(
                '비밀번호',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                  color: muted,
                ),
              ),
              const SizedBox(height: 8),
              TextFormField(
                controller: passwordController,
                obscureText: obscurePassword,
                style: const TextStyle(color: titleColor),
                decoration: InputDecoration(
                  hintText: '비밀번호를 입력하세요',
                  suffixIcon: IconButton(
                    icon: Icon(
                      obscurePassword
                          ? Icons.visibility_off_outlined
                          : Icons.visibility_outlined,
                      color: hint,
                    ),
                    onPressed: onToggleObscure,
                  ),
                ),
                validator: Validators.password,
                onFieldSubmitted: (_) => onLogin(),
              ),
              const SizedBox(height: 10),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('계정은 관리자가 발급·재설정합니다.'),
                      ),
                    );
                  },
                  style: TextButton.styleFrom(
                    foregroundColor: hint,
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: const Text(
                    '아이디/비밀번호 찾기',
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
                  ),
                ),
              ),
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: (isLoading || loginSucceeded) ? null : onLogin,
                style: ElevatedButton.styleFrom(
                  backgroundColor: loginSucceeded
                      ? const Color(0xFF16A34A)
                      : const Color(0xFF00C2D4),
                  foregroundColor: Colors.white,
                  disabledBackgroundColor: loginSucceeded
                      ? const Color(0xFF16A34A)
                      : const Color(0xFF00C2D4).withValues(alpha: 0.55),
                  disabledForegroundColor: Colors.white,
                ),
                child: isLoading
                    ? const SizedBox(
                        width: 24,
                        height: 24,
                        child: CircularProgressIndicator(
                          color: Colors.white,
                          strokeWidth: 2,
                        ),
                      )
                    : loginSucceeded
                        ? const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.check_rounded, size: 20),
                              SizedBox(width: 8),
                              Text('로그인 성공'),
                            ],
                          )
                        : const Text('로그인'),
              ),
              const SizedBox(height: 16),
              TextButton(
                onPressed: (isLoading || loginSucceeded)
                    ? null
                    : onToggleQuickLogin,
                style: TextButton.styleFrom(
                  foregroundColor: const Color(0xFF00C2D4),
                ),
                child: Text(
                  showQuickLogin ? '빠른 로그인 숨기기' : '빠른 로그인 (데모)',
                  style: const TextStyle(fontSize: 13),
                ),
              ),
              if (showQuickLogin) ...[
                const SizedBox(height: 8),
                _QuickLoginRow(
                  label: '관리자',
                  email: DemoAccounts.adminEmail,
                  onTap: () => onQuickLogin(
                    DemoAccounts.adminEmail,
                    DemoAccounts.adminPassword,
                  ),
                ),
                const SizedBox(height: 6),
                _QuickLoginRow(
                  label: '강사',
                  email: DemoAccounts.instructorEmail,
                  onTap: () => onQuickLogin(
                    DemoAccounts.instructorEmail,
                    DemoAccounts.instructorPassword,
                  ),
                ),
                const SizedBox(height: 6),
                _QuickLoginRow(
                  label: '학생',
                  email: DemoAccounts.studentEmail,
                  onTap: () => onQuickLogin(
                    DemoAccounts.studentEmail,
                    DemoAccounts.studentPassword,
                  ),
                ),
              ],
              const SizedBox(height: 12),
              Text(
                '계정은 관리자가 발급합니다.',
                textAlign: TextAlign.center,
                style: TextStyle(color: hint, fontSize: 12),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _QuickLoginRow extends StatelessWidget {
  const _QuickLoginRow({
    required this.label,
    required this.email,
    required this.onTap,
  });

  final String label;
  final String email;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white.withValues(alpha: 0.06),
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: Colors.white24),
          ),
          child: Row(
            children: [
              SizedBox(
                width: 52,
                child: Text(
                  label,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF00C2D4),
                  ),
                ),
              ),
              Expanded(
                child: Text(
                  email,
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.white.withValues(alpha: 0.6),
                  ),
                ),
              ),
              const Icon(
                Icons.login,
                size: 18,
                color: Color(0xFF00C2D4),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

