import 'package:flutter/material.dart';

import '../../../../core/core_navigator.dart';
import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/theme/color_scheme.dart';
import '../../../../shared/design_system/widgets/custom_button.dart';
import '../../../../shared/design_system/widgets/custom_text_field.dart';
import '../../../../shared/exceptions/app_exception.dart';
import '../../../../shared/network/interceptors.dart' show LoginRedirectReason;
import '../../../../shared/utils/validators.dart';
import '../../data/auth_repository.dart';
import '../widgets/auth_scaffold.dart';

/// "تسجيل الدخول" — the Host Shell's entry point for an
/// unauthenticated user.
///
/// On success, replaces the entire navigation stack with the
/// dashboard ([CoreRoutes.dashboard]) so the back button can never
/// return the user to the login form once signed in. Also doubles as
/// a lightweight session gate: if a token is already stored on this
/// device (a returning user reopening the app), it skips straight to
/// the dashboard instead of showing the form at all.
class LoginPage extends StatefulWidget {
  const LoginPage({super.key, AuthRepository? authRepository})
      : _authRepositoryOverride = authRepository;

  /// Injectable for tests; defaults to [AuthRepository.instance] in
  /// production, mirroring `MiniProgramHostPage`'s `loader` override.
  final AuthRepository? _authRepositoryOverride;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  late final AuthRepository _authRepository =
      widget._authRepositoryOverride ?? AuthRepository.instance;

  bool _isCheckingSession = true;
  bool _isSubmitting = false;
  bool _sessionExpiredNoticeShown = false;

  @override
  void initState() {
    super.initState();
    _restoreExistingSession();
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  /// Skips the login form entirely if a session token is already
  /// stored — e.g. the user closed and reopened the app. Fails open
  /// to the form (rather than hanging on a spinner) if the local
  /// secure-storage check itself errors out.
  Future<void> _restoreExistingSession() async {
    bool alreadyLoggedIn = false;
    try {
      alreadyLoggedIn = await _authRepository.isLoggedIn();
    } catch (_) {
      alreadyLoggedIn = false;
    }
    if (!mounted) return;
    if (alreadyLoggedIn) {
      _goToDashboard();
      return;
    }
    setState(() => _isCheckingSession = false);
  }

  void _goToDashboard() {
    Navigator.of(context).pushNamedAndRemoveUntil(
      CoreRoutes.dashboard,
      (Route<dynamic> route) => false,
    );
  }

  Future<void> _submit() async {
    final FormState? form = _formKey.currentState;
    if (form == null || !form.validate()) return;

    setState(() => _isSubmitting = true);
    try {
      await _authRepository.login(
        email: _emailController.text,
        password: _passwordController.text,
      );
      if (!mounted) return;
      _goToDashboard();
    } on AppException catch (error) {
      if (!mounted) return;
      _showMessage(error.message);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  /// Shows a one-time notice when this screen was reached via
  /// `AuthInterceptor`'s forced logout redirect (an expired/invalid
  /// session), instead of silently dropping the user back on a bare
  /// login form with no explanation.
  void _maybeShowSessionExpiredNotice(BuildContext context) {
    if (_sessionExpiredNoticeShown) return;
    final Object? reason = ModalRoute.of(context)?.settings.arguments;
    if (reason != LoginRedirectReason.sessionExpired) return;

    _sessionExpiredNoticeShown = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _showMessage('انتهت صلاحية الجلسة. يرجى تسجيل الدخول مرة أخرى.');
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_isCheckingSession) {
      return const Scaffold(
        backgroundColor: MizanColors.navy,
        body: Center(
          child: CircularProgressIndicator(color: MizanColors.gold),
        ),
      );
    }

    _maybeShowSessionExpiredNotice(context);

    return AuthScaffold(
      title: 'تسجيل الدخول',
      subtitle: 'مرحبًا بعودتك، سجّل الدخول لمتابعة استخدام ميزان.',
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            MizanTextField(
              controller: _emailController,
              label: 'البريد الإلكتروني',
              hint: 'name@example.com',
              keyboardType: TextInputType.emailAddress,
              textDirection: TextDirection.ltr,
              textInputAction: TextInputAction.next,
              autofillHints: const <String>[AutofillHints.email],
              prefixIcon: Icons.mail_outline,
              enabled: !_isSubmitting,
              validator: Validators.email,
            ),
            const SizedBox(height: AppSpacing.md),
            MizanTextField(
              controller: _passwordController,
              label: 'كلمة المرور',
              obscureText: true,
              textDirection: TextDirection.ltr,
              textInputAction: TextInputAction.done,
              autofillHints: const <String>[AutofillHints.password],
              prefixIcon: Icons.lock_outline,
              enabled: !_isSubmitting,
              validator: Validators.loginPassword,
            ),
            const SizedBox(height: AppSpacing.lg),
            PrimaryButton(
              label: 'دخول',
              isLoading: _isSubmitting,
              onPressed: _submit,
            ),
            const SizedBox(height: AppSpacing.md),
            Wrap(
              alignment: WrapAlignment.center,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: <Widget>[
                const Text('ليس لديك حساب؟'),
                TextButton(
                  onPressed: _isSubmitting
                      ? null
                      : () =>
                          Navigator.of(context).pushNamed(CoreRoutes.register),
                  child: const Text('إنشاء حساب'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
