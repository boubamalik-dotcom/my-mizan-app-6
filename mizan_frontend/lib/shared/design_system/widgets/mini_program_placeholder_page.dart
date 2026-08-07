import 'package:flutter/material.dart';

/// Reusable "feature under construction" scaffold shared by
/// mini-program entry points while their real presentation pages are
/// being built out.
///
/// Deliberately takes primitive parameters (title, description, icon,
/// accent color) instead of a mini-program object: the shared layer
/// must never depend on `core/` or `mini_programs/` — only the other
/// way around. This keeps [MiniProgramPlaceholderPage] usable by any
/// mini-program (or the host shell itself) without introducing a
/// dependency cycle.
class MiniProgramPlaceholderPage extends StatelessWidget {
  const MiniProgramPlaceholderPage({
    super.key,
    required this.title,
    required this.description,
    required this.icon,
    required this.accentColor,
  });

  /// Title shown in the app bar and as the headline.
  final String title;

  /// Short description of the mini-program's purpose.
  final String description;

  /// Icon representing the mini-program.
  final IconData icon;

  /// Accent color used for the app bar and icon, matching the
  /// mini-program's identity on the host dashboard.
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        backgroundColor: accentColor,
        foregroundColor: Colors.white,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(icon, size: 72, color: accentColor),
              const SizedBox(height: 20),
              Text(
                title,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 8),
              Text(
                description,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 24),
              Text(
                'Feature pages coming soon.',
                textAlign: TextAlign.center,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(fontStyle: FontStyle.italic),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
