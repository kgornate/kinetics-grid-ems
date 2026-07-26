import 'package:flutter/material.dart';

import 'core/state/gateway_controller.dart';
import 'screens/home_shell.dart';
import 'screens/login_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const KineticsGatewayApp());
}

class KineticsGatewayApp extends StatefulWidget {
  const KineticsGatewayApp({super.key});

  @override
  State<KineticsGatewayApp> createState() => _KineticsGatewayAppState();
}

class _KineticsGatewayAppState extends State<KineticsGatewayApp> {
  late final GatewayController _controller = GatewayController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Kinetics Gateway',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF006A60)),
        useMaterial3: true,
        inputDecorationTheme: const InputDecorationTheme(filled: true),
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF4FD8C7),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
        inputDecorationTheme: const InputDecorationTheme(filled: true),
      ),
      themeMode: ThemeMode.system,
      home: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          return _controller.authenticated
              ? HomeShell(controller: _controller)
              : LoginScreen(controller: _controller);
        },
      ),
    );
  }
}
