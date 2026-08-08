import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'core/core_navigator.dart';
import 'shared/design_system/theme/app_theme.dart';
import 'shared/network/interceptors.dart' show rootNavigatorKey;

void main() {
  runApp(const MizanApp());
}

/// Root widget of the Mizan Super App.
///
/// Wires the Host Shell's routing table ([CoreNavigator]) into
/// [MaterialApp]. All navigation — to login/registration, the
/// dashboard, and any dynamically-loaded mini-program — flows through
/// [CoreNavigator.onGenerateRoute].
///
/// Two cross-cutting concerns are configured once, here, for the
/// entire app:
///
///  * **Theming**: [AppTheme.light] applies the Mizan navy/gold brand
///    identity (see `shared/design_system/theme/`) globally, so no
///    screen needs to re-declare its own colors or corner radii.
///  * **RTL Arabic**: setting `locale` to Arabic (with the standard
///    Flutter localization delegates) makes [Directionality] resolve
///    to [TextDirection.rtl] app-wide — required for the Arabic auth
///    screens (and every Arabic screen after them) to lay out
///    correctly, mirror icons, and align text without each screen
///    wrapping itself in a manual `Directionality` override.
class MizanApp extends StatelessWidget {
  const MizanApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Mizan',
      debugShowCheckedModeBanner: false,
      navigatorKey: rootNavigatorKey,
      theme: AppTheme.light,
      locale: const Locale('ar'),
      supportedLocales: const <Locale>[Locale('ar'), Locale('en')],
      localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      initialRoute: CoreRoutes.login,
      onGenerateInitialRoutes: CoreNavigator.onGenerateInitialRoutes,
      onGenerateRoute: CoreNavigator.onGenerateRoute,
    );
  }
}
