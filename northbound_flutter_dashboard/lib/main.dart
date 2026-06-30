import 'package:flutter/material.dart';

import 'api/northbound_api_client.dart';
import 'api/telemetry_ws_client.dart';
import 'config/app_config.dart';
import 'models/auth_session.dart';
import 'screens/dashboard_screen.dart';
import 'screens/login_screen.dart';

void main() {
  runApp(const NorthboundDashboardApp());
}

class NorthboundDashboardApp extends StatefulWidget {
  const NorthboundDashboardApp({super.key});

  @override
  State<NorthboundDashboardApp> createState() => _NorthboundDashboardAppState();
}

class _NorthboundDashboardAppState extends State<NorthboundDashboardApp> {
  ApiProfile activeProfile = ApiProfile.localEth0;
  AuthSession? authSession;
  late NorthboundApiClient apiClient;
  late TelemetryWsClient wsClient;

  @override
  void initState() {
    super.initState();
    _buildClients();
  }

  void _buildClients() {
    apiClient = NorthboundApiClient(
      restBaseUrl: activeProfile.restBaseUrl,
      logsBaseUrl: activeProfile.logsBaseUrl,
      httpTimeout: activeProfile.httpTimeout,
      accessToken: authSession?.accessToken,
      onUnauthorized: logout,
    );
    wsClient = TelemetryWsClient(wsUrl: activeProfile.wsUrl, authToken: authSession?.accessToken);
  }

  void updateProfile(ApiProfile profile) {
    final oldWsClient = wsClient;
    setState(() {
      activeProfile = profile;
      _buildClients();
    });
    oldWsClient.dispose();
  }

  void login(AuthSession session) {
    final oldWsClient = wsClient;
    setState(() {
      authSession = session;
      _buildClients();
    });
    oldWsClient.dispose();
  }

  void logout() {
    final oldWsClient = wsClient;
    setState(() {
      authSession = null;
      _buildClients();
    });
    oldWsClient.dispose();
  }

  @override
  void dispose() {
    wsClient.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'NorthBound EMS Dashboard',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: Colors.indigo,
        brightness: Brightness.light,
      ),
      darkTheme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: Colors.indigo,
        brightness: Brightness.dark,
      ),
      home: authSession == null
          ? LoginScreen(
              activeProfile: activeProfile,
              onProfileChanged: updateProfile,
              onLogin: login,
            )
          : DashboardScreen(
              apiClient: apiClient,
              wsClient: wsClient,
              activeProfile: activeProfile,
              authSession: authSession!,
              onProfileChanged: updateProfile,
              onLogout: logout,
            ),
    );
  }
}
