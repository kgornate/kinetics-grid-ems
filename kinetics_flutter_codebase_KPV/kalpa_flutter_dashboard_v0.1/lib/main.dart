import 'package:flutter/material.dart';

import 'core/state/gateway_controller.dart';
import 'screens/home_shell.dart';
import 'screens/login_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const KalpaGatewayApp());
}

class KalpaGatewayApp extends StatefulWidget {
  const KalpaGatewayApp({super.key});

  @override
  State<KalpaGatewayApp> createState() => _KalpaGatewayAppState();
}

class _KalpaGatewayAppState extends State<KalpaGatewayApp> {
  late final GatewayController _controller = GatewayController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Kalpa Gateway',
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
