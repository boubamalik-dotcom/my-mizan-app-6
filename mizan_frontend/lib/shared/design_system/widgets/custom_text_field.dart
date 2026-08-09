import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// The Mizan design system's standard form field.
///
/// A thin wrapper around [TextFormField] that layers on:
///
///  * a show/hide toggle for [obscureText] fields (e.g. passwords),
///    instead of every screen re-implementing that bit of state;
///  * an explicit [textDirection] override, since Arabic-locale RTL
///    layouts (see `main.dart`) still need inherently-LTR content —
///    email addresses, in particular — pinned left-to-right so they
///    read correctly instead of being bidi-reordered.
///
/// Visual styling itself (fill color, 16px rounded border, focus/error
/// border colors) comes entirely from `AppTheme.light
/// .inputDecorationTheme` — this widget never repeats it locally.
class MizanTextField extends StatefulWidget {
  const MizanTextField({
    super.key,
    required this.controller,
    required this.label,
    this.hint,
    this.keyboardType,
    this.obscureText = false,
    this.prefixIcon,
    this.validator,
    this.textInputAction,
    this.textDirection,
    this.autofillHints,
    this.enabled = true,
    this.inputFormatters,
  });

  final TextEditingController controller;
  final String label;
  final String? hint;
  final TextInputType? keyboardType;

  /// Whether this field's content should be masked, with a
  /// show/hide-password toggle rendered as its suffix icon.
  final bool obscureText;

  final IconData? prefixIcon;
  final FormFieldValidator<String>? validator;
  final TextInputAction? textInputAction;

  /// Forces this field's text direction regardless of the ambient
  /// (Arabic/RTL) locale — set to [TextDirection.ltr] for fields whose
  /// content is inherently left-to-right, such as an email address.
  final TextDirection? textDirection;

  final Iterable<String>? autofillHints;
  final bool enabled;

  /// Restricts what can be typed — e.g. digits and a decimal separator
  /// for a money amount, so an invalid character never reaches the
  /// validator in the first place.
  final List<TextInputFormatter>? inputFormatters;

  @override
  State<MizanTextField> createState() => _MizanTextFieldState();
}

class _MizanTextFieldState extends State<MizanTextField> {
  late bool _obscured = widget.obscureText;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: widget.controller,
      enabled: widget.enabled,
      obscureText: widget.obscureText && _obscured,
      keyboardType: widget.keyboardType,
      textInputAction: widget.textInputAction,
      textDirection: widget.textDirection,
      autofillHints: widget.autofillHints,
      inputFormatters: widget.inputFormatters,
      autovalidateMode: AutovalidateMode.onUserInteraction,
      validator: widget.validator,
      decoration: InputDecoration(
        labelText: widget.label,
        hintText: widget.hint,
        prefixIcon: widget.prefixIcon != null ? Icon(widget.prefixIcon) : null,
        suffixIcon: widget.obscureText
            ? IconButton(
                icon: Icon(
                  _obscured
                      ? Icons.visibility_off_outlined
                      : Icons.visibility_outlined,
                ),
                tooltip: _obscured ? 'إظهار كلمة المرور' : 'إخفاء كلمة المرور',
                onPressed: () => setState(() => _obscured = !_obscured),
              )
            : null,
      ),
    );
  }
}
