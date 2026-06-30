import 'package:flutter/material.dart';

import 'api/northbound_api_client.dart';
import 'api/telemetry_ws_client.dart';
import 'config/app_config.dart';
import 'screens/dashboard_screen.dart';

void main() {
  runApp(const NorthboundDashboardApp());
}

class NorthboundDashboardApp extends StatefulWidget {
  const NorthboundDashboardApp({super.key});

  @override
  State<NorthboundDashboardApp> createState() => _NorthboundDashboardAppState();
}

class _NorthboundDashboardAppState extends State<NorthboundDashboardApp> {
  AppConfig config = AppConfig.localEth0;
  late NorthboundApiClient apiClient;
  late TelemetryWsClient wsClient;

  @override
  void initState() {
    super.initState();
    _buildClients();
  }

  void _buildClients() {
    apiClient = NorthboundApiClient(baseUrl: config.apiBaseUrl);
    wsClient = TelemetryWsClient(wsUrl: config.wsUrl);
  }

  void updateConfig(String apiBaseUrl, String wsUrl) {
    final oldWsClient = wsClient;
    setState(() {
      config = config.copyWith(apiBaseUrl: apiBaseUrl, wsUrl: wsUrl);
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
      home: DashboardScreen(
        apiClient: apiClient,
        wsClient: wsClient,
        apiBaseUrl: config.apiBaseUrl,
        wsUrl: config.wsUrl,
        onConfigChanged: updateConfig,
      ),
    );
  }
}
