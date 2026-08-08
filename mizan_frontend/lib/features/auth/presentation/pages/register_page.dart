import 'package:flutter/material.dart';

import '../../../../core/core_navigator.dart';
import '../../../../shared/design_system/constants/app_constants.dart';
import '../../../../shared/design_system/widgets/custom_button.dart';
import '../../../../shared/design_system/widgets/custom_text_field.dart';
import '../../../../shared/exceptions/app_exception.dart';
import '../../../../shared/utils/validators.dart';
import '../../data/auth_repository.dart';
import '../widgets/auth_scaffold.dart';

/// "إنشاء حساب" — new-account registration.
///
/// `POST /auth/register` only creates the account; it does not return
/// a session token (see `AuthRepository.register`). So that
/// registering genuinely "bridges the gap" straight into the app
/// rather than dropping the user back on the login form, this screen
/// immediately logs the freshly-created account in and lands on the
/// dashboard — falling back to the login screen, with an explanatory
/// message, only if that immediate login step itself fails.
class RegisterPage extends StatefulWidget {
  const RegisterPage({super.key, AuthRepository? authRepository})
      : _authRepositoryOverride = authRepository;

  /// Injectable for tests; defaults to [AuthRepository.instance] in
  /// production, mirroring `MiniProgramHostPage`'s `loader` override.
  final AuthRepository? _authRepositoryOverride;

  @override
  State<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends State<RegisterPage> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _fullNameController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  late final AuthRepository _authRepository =
      widget._authRepositoryOverride ?? AuthRepository.instance;

  bool _isSubmitting = false;

  @override
  void dispose() {
    _fullNameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final FormState? form = _formKey.currentState;
    if (form == null || !form.validate()) return;

    final String email = _emailController.text.trim();
    final String password = _passwordController.text;

    setState(() => _isSubmitting = true);

    try {
      await _authRepository.register(
        fullName: _fullNameController.text.trim(),
        email: email,
        password: password,
      );
    } on AppException catch (error) {
      if (mounted) {
        _showMessage(error.message);
        setState(() => _isSubmitting = false);
      }
      return;
    }

    if (!mounted) return;

    try {
      await _authRepository.login(email: email, password: password);
      if (!mounted) return;
      Navigator.of(context).pushNamedAndRemoveUntil(
        CoreRoutes.dashboard,
        (Route<dynamic> route) => false,
      );
    } on AppException catch (_) {
      // The account was created successfully; only the automatic
      // sign-in afterwards failed (e.g. a dropped connection at the
      // worst possible moment). Send the user to a normal login
      // rather than reporting the registration itself as failed.
      if (!mounted) return;
      Navigator.of(context).pushNamedAndRemoveUntil(
        CoreRoutes.login,
        (Route<dynamic> route) => false,
      );
      _showMessage('تم إنشاء حسابك بنجاح. يرجى تسجيل الدخول.');
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  void _goBackToLogin() {
    final NavigatorState navigator = Navigator.of(context);
    if (navigator.canPop()) {
      navigator.pop();
    } else {
      navigator.pushReplacementNamed(CoreRoutes.login);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AuthScaffold(
      title: 'إنشاء حساب',
      subtitle: 'أنشئ حسابك للبدء في استخدام تطبيق ميزان.',
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            MizanTextField(
              controller: _fullNameController,
              label: 'الاسم الكامل',
              textInputAction: TextInputAction.next,
              autofillHints: const <String>[AutofillHints.name],
              prefixIcon: Icons.person_outline,
              enabled: !_isSubmitting,
              validator: Validators.fullName,
            ),
            const SizedBox(height: AppSpacing.md),
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
              hint: '٨ أحرف على الأقل',
              obscureText: true,
              textDirection: TextDirection.ltr,
              textInputAction: TextInputAction.done,
              autofillHints: const <String>[AutofillHints.newPassword],
              prefixIcon: Icons.lock_outline,
              enabled: !_isSubmitting,
              validator: Validators.newPassword,
            ),
            const SizedBox(height: AppSpacing.lg),
            PrimaryButton(
              label: 'إنشاء حساب',
              isLoading: _isSubmitting,
              onPressed: _submit,
            ),
            const SizedBox(height: AppSpacing.md),
            Wrap(
              alignment: WrapAlignment.center,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: <Widget>[
                const Text('لديك حساب بالفعل؟'),
                TextButton(
                  onPressed: _isSubmitting ? null : _goBackToLogin,
                  child: const Text('تسجيل الدخول'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
