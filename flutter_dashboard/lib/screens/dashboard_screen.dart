import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../models/bms_telemetry.dart';
import '../models/chiller_telemetry.dart';
import '../models/gateway_response.dart';
import '../models/pcs_telemetry.dart';
import '../services/tcp_command_service.dart';
import '../services/udp_telemetry_service.dart';
import '../widgets/command_panel.dart';
import '../widgets/status_indicator.dart';
import '../widgets/telemetry_card.dart';
import 'bms_screen.dart';
import 'logs_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final UdpTelemetryService _udpService = UdpTelemetryService();

  final TextEditingController _gatewayIpController =
      TextEditingController(text: AppConfig.defaultGatewayIp);

  StreamSubscription<ChillerTelemetry>? _telemetrySubscription;
  StreamSubscription<PcsTelemetry>? _pcsTelemetrySubscription;
  StreamSubscription<BmsTelemetry>? _bmsTelemetrySubscription;
  StreamSubscription<Map<String, dynamic>>? _rawPacketSubscription;

  ChillerTelemetry? _latestTelemetry;
  PcsTelemetry? _latestPcsTelemetry;
  BmsTelemetry? _latestBmsTelemetry;
  Map<String, dynamic>? _latestRawPacket;
  GatewayResponse? _lastResponse;

  bool _udpRunning = false;
  bool _commandInProgress = false;
  String _statusMessage = 'Dashboard initialized';

  @override
  void initState() {
    super.initState();
    _setupStreams();
    _startUdpListener();
  }

  void _setupStreams() {
    _telemetrySubscription = _udpService.telemetryStream.listen((telemetry) {
      setState(() {
        _latestTelemetry = telemetry;
        _statusMessage =
            'Chiller telemetry received at ${_formatTime(telemetry.receivedAt)}';
      });
    });

    _pcsTelemetrySubscription =
        _udpService.pcsTelemetryStream.listen((pcsTelemetry) {
      setState(() {
        _latestPcsTelemetry = pcsTelemetry;
        _statusMessage =
            'PCS telemetry received at ${_formatTime(pcsTelemetry.receivedAt)}';
      });
    });

    _bmsTelemetrySubscription =
        _udpService.bmsTelemetryStream.listen((bmsTelemetry) {
      setState(() {
        _latestBmsTelemetry = bmsTelemetry;
        _statusMessage =
            'BMS telemetry received at ${_formatTime(bmsTelemetry.receivedAt)}';
      });
    });

    _rawPacketSubscription = _udpService.rawPacketStream.listen((packet) {
      setState(() {
        _latestRawPacket = packet;
      });
    });
  }

  Future<void> _startUdpListener() async {
    try {
      await _udpService.start(port: AppConfig.udpTelemetryPort);

      setState(() {
        _udpRunning = true;
        _statusMessage =
            'UDP listener running on port ${AppConfig.udpTelemetryPort}';
      });
    } catch (e) {
      setState(() {
        _udpRunning = false;
        _statusMessage = 'UDP listener error: $e';
      });
    }
  }

  Future<void> _stopUdpListener() async {
    await _udpService.stop();

    setState(() {
      _udpRunning = false;
      _statusMessage = 'UDP listener stopped';
    });
  }

  TcpCommandService _tcpService() {
    return TcpCommandService(
      gatewayIp: _gatewayIpController.text.trim(),
      gatewayPort: AppConfig.tcpCommandPort,
      timeout: AppConfig.tcpTimeout,
    );
  }

  Future<void> _sendCommand(String command, {dynamic value}) async {
    setState(() {
      _commandInProgress = true;
      _statusMessage = 'Sending command: $command';
    });

    final response = await _tcpService().sendCommand(
      command: command,
      value: value,
      verify: true,
    );

    setState(() {
      _lastResponse = response;
      _commandInProgress = false;

      _statusMessage = response.isOk
          ? 'Command successful: $command'
          : 'Command failed: ${response.message}';

      final upperCommand = command.toUpperCase();

      if (response.isOk && upperCommand == 'READ_ALL') {
        final data = _extractDataOrMockState(response.data);
        if (data.isNotEmpty) {
          _latestTelemetry = ChillerTelemetry.fromJson(data);
        }
      }

      if (response.isOk &&
          (upperCommand == 'PCS_READ' || upperCommand == 'READ_PCS')) {
        if (response.data.isNotEmpty) {
          _latestPcsTelemetry = PcsTelemetry.fromJson(response.data);
        }
      }

      if (response.isOk &&
          (upperCommand == 'READ_BMS' ||
              upperCommand == 'READ_BMS_ALL' ||
              upperCommand == 'BMS_READ_ALL' ||
              upperCommand == 'READ_BMS_ALARMS' ||
              upperCommand == 'BMS_READ_ALARMS')) {
        if (response.data.isNotEmpty) {
          _latestBmsTelemetry = BmsTelemetry.fromJson(response.data);
        }
      }

      if (response.isOk &&
          (upperCommand == 'READ_ALL_ASSETS' ||
              upperCommand == 'READ_GATEWAY_TELEMETRY')) {
        final pcs = _extractPcsFromTelemetryPacket(response.data);
        if (pcs.isNotEmpty) {
          _latestPcsTelemetry = PcsTelemetry.fromJson(pcs);
        }
        final bms = _extractBmsFromTelemetryPacket(response.data);
        if (bms.isNotEmpty) {
          _latestBmsTelemetry = BmsTelemetry.fromJson(bms);
        }
      }
    });
  }

  void _openLogsScreen() {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => LogsScreen(
          initialGatewayIp: _gatewayIpController.text.trim(),
        ),
      ),
    );
  }

  void _openBmsScreen(BmsTelemetry? bms) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => BmsScreen(
          gatewayIp: _gatewayIpController.text.trim(),
          initialTelemetry: bms,
        ),
      ),
    );
  }

  @override
  void dispose() {
    _gatewayIpController.dispose();
    _telemetrySubscription?.cancel();
    _pcsTelemetrySubscription?.cancel();
    _bmsTelemetrySubscription?.cancel();
    _rawPacketSubscription?.cancel();
    _udpService.dispose();
    super.dispose();
  }

  String _value(dynamic value) {
    if (value == null) return '--';
    return value.toString();
  }

  String _doubleValue(double? value, {int digits = 1}) {
    if (value == null) return '--';
    return value.toStringAsFixed(digits);
  }

  String _formatTime(DateTime? time) {
    if (time == null) return '--';

    return '${time.hour.toString().padLeft(2, '0')}:'
        '${time.minute.toString().padLeft(2, '0')}:'
        '${time.second.toString().padLeft(2, '0')}';
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return {};
  }

  Map<String, dynamic> _extractDataOrMockState(Map<String, dynamic> data) {
    final mockState = _asMap(data['mock_state']);

    if (mockState.isNotEmpty) {
      return mockState;
    }

    return data;
  }

  Map<String, dynamic> _extractPcsFromTelemetryPacket(Map<String, dynamic> packet) {
    final payload = _asMap(packet['payload']).isNotEmpty
        ? _asMap(packet['payload'])
        : packet;

    final directPcs = _asMap(payload['pcs']);
    if (directPcs.isNotEmpty) return directPcs;

    final assets = _asMap(payload['assets']);
    final assetsPcs = _asMap(assets['pcs']);
    if (assetsPcs.isNotEmpty) return assetsPcs;

    final data = _asMap(packet['data']);
    final dataPcs = _asMap(data['pcs']);
    if (dataPcs.isNotEmpty) return dataPcs;

    return {};
  }


  Map<String, dynamic> _extractBmsFromTelemetryPacket(Map<String, dynamic> packet) {
    final payload = _asMap(packet['payload']).isNotEmpty
        ? _asMap(packet['payload'])
        : packet;

    final directBms = _asMap(payload['bms']);
    if (directBms.isNotEmpty) return directBms;

    final assets = _asMap(payload['assets']);
    final assetsBms = _asMap(assets['bms']);
    if (assetsBms.isNotEmpty) return assetsBms;

    final data = _asMap(packet['data']);
    final dataBms = _asMap(data['bms']);
    if (dataBms.isNotEmpty) return dataBms;

    final hasBmsKeys = data.containsKey('soc_percent') ||
        data.containsKey('rack_voltage_v') ||
        data['asset_id']?.toString() == AppConfig.bmsAssetId;
    if (hasBmsKeys) return data;

    return {};
  }

  @override
  Widget build(BuildContext context) {
    final chiller = _latestTelemetry;
    final pcs = _latestPcsTelemetry;
    final bms = _latestBmsTelemetry;

    return Scaffold(
      appBar: AppBar(
        title: const Text('EMS Dashboard - Chiller + PCS + BMS'),
        actions: [
          TextButton.icon(
            onPressed: _openLogsScreen,
            icon: const Icon(Icons.history),
            label: const Text('Logs'),
          ),
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(
              child: Text(
                _udpRunning ? 'UDP Listening' : 'UDP Stopped',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: _udpRunning ? Colors.green : Colors.red,
                ),
              ),
            ),
          ),
        ],
      ),
      body: Row(
        children: [
          Expanded(
            flex: 3,
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildTopConfigCard(),
                  const SizedBox(height: 16),
                  _buildStatusRow(chiller, pcs, bms),
                  const SizedBox(height: 16),
                  _sectionHeader('BMS / Battery Telemetry'),
                  const SizedBox(height: 10),
                  _buildBmsTelemetryGrid(bms),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: () => _openBmsScreen(bms),
                    icon: const Icon(Icons.battery_charging_full),
                    label: const Text('Open BMS Detail Screen'),
                  ),
                  const SizedBox(height: 20),
                  _sectionHeader('PCS / Inverter Telemetry'),
                  const SizedBox(height: 10),
                  _buildPcsTelemetryGrid(pcs),
                  const SizedBox(height: 20),
                  _sectionHeader('Chiller Telemetry'),
                  const SizedBox(height: 10),
                  _buildChillerTelemetryGrid(chiller),
                  const SizedBox(height: 16),
                  _buildRawPacketCard(),
                ],
              ),
            ),
          ),
          Container(width: 1, color: Colors.black12),
          SizedBox(
            width: 450,
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(18),
              child: Column(
                children: [
                  CommandPanel(onSendCommand: _sendCommand),
                  const SizedBox(height: 16),
                  _buildReadableCommandResultCard(),
                  const SizedBox(height: 16),
                  _buildRawCommandResponseCard(),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _sectionHeader(String title) {
    return Text(
      title,
      style: Theme.of(context).textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.bold,
          ),
    );
  }

  Widget _buildTopConfigCard() {
    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _gatewayIpController,
                decoration: const InputDecoration(
                  labelText: 'i.MX93 Gateway IP',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.router),
                ),
              ),
            ),
            const SizedBox(width: 12),
            FilledButton.tonal(
              onPressed: _udpRunning ? _stopUdpListener : _startUdpListener,
              child: Text(_udpRunning ? 'Stop UDP' : 'Start UDP'),
            ),
            const SizedBox(width: 12),
            FilledButton.icon(
              onPressed: _openLogsScreen,
              icon: const Icon(Icons.history),
              label: const Text('Logs'),
            ),
            const SizedBox(width: 12),
            if (_commandInProgress)
              const SizedBox(
                width: 28,
                height: 28,
                child: CircularProgressIndicator(strokeWidth: 3),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusRow(ChillerTelemetry? chiller, PcsTelemetry? pcs, BmsTelemetry? bms) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        StatusIndicator(
          label: 'Gateway UDP',
          status: _udpRunning ? 'LISTENING' : 'STOPPED',
          active: _udpRunning,
        ),
        StatusIndicator(
          label: 'BMS Comm',
          status: bms?.effectiveCommStatus,
          active: bms?.isOnline ?? false,
        ),
        StatusIndicator(
          label: 'BMS State',
          status: bms?.bcuState,
          active: bms != null &&
              (bms.bcuState == null ||
                  bms.bcuState!.toLowerCase().contains('normal')),
        ),
        StatusIndicator(
          label: 'BMS Alarms',
          status: bms == null ? '--' : '${bms.alarmCount}',
          active: bms != null && !bms.hasAlarms,
        ),
        StatusIndicator(
          label: 'PCS Comm',
          status: pcs?.commStatus,
          active: pcs?.isOnline ?? false,
        ),
        StatusIndicator(
          label: 'PCS Status',
          status: pcs?.operatingStatus,
          active: pcs?.isRunning ?? false,
        ),
        StatusIndicator(
          label: 'PCS Fault',
          status: pcs == null ? '--' : (pcs.faultStatus ? 'FAULT' : 'NORMAL'),
          active: pcs != null && !pcs.faultStatus,
        ),
        StatusIndicator(
          label: 'Chiller Comm',
          status: chiller?.communicationStatus,
          active: chiller?.isOnline ?? false,
        ),
        StatusIndicator(
          label: 'Water Pump',
          status: chiller?.waterPump,
          active: chiller?.waterPump == 'RUNNING',
        ),
      ],
    );
  }


  Widget _buildBmsTelemetryGrid(BmsTelemetry? b) {
    return LayoutBuilder(
      builder: (context, constraints) {
        int crossAxisCount = 3;

        if (constraints.maxWidth < 900) {
          crossAxisCount = 2;
        }

        if (constraints.maxWidth < 560) {
          crossAxisCount = 1;
        }

        return GridView.count(
          crossAxisCount: crossAxisCount,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: 2.35,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          children: [
            TelemetryCard(
              title: 'SOC',
              value: _doubleValue(b?.socPercent),
              unit: '%',
              icon: Icons.battery_full,
            ),
            TelemetryCard(
              title: 'SOH',
              value: _doubleValue(b?.sohPercent),
              unit: '%',
              icon: Icons.health_and_safety,
            ),
            TelemetryCard(
              title: 'Rack Voltage',
              value: _doubleValue(b?.rackVoltageV),
              unit: 'V',
              icon: Icons.bolt,
            ),
            TelemetryCard(
              title: 'Rack Current',
              value: _doubleValue(b?.rackCurrentA),
              unit: 'A',
              icon: Icons.electric_meter,
            ),
            TelemetryCard(
              title: 'Power',
              value: _doubleValue(b?.powerKw, digits: 2),
              unit: 'kW',
              icon: Icons.power,
            ),
            TelemetryCard(
              title: 'Max Cell Voltage',
              value: _doubleValue(b?.maxCellVoltageMv, digits: 0),
              unit: 'mV',
              icon: Icons.arrow_upward,
            ),
            TelemetryCard(
              title: 'Min Cell Voltage',
              value: _doubleValue(b?.minCellVoltageMv, digits: 0),
              unit: 'mV',
              icon: Icons.arrow_downward,
            ),
            TelemetryCard(
              title: 'Voltage Diff',
              value: _doubleValue(b?.cellVoltageDiffMv, digits: 0),
              unit: 'mV',
              icon: Icons.compare_arrows,
            ),
            TelemetryCard(
              title: 'Max Temp',
              value: _doubleValue(b?.maxCellTempC),
              unit: '°C',
              icon: Icons.device_thermostat,
            ),
            TelemetryCard(
              title: 'Min Temp',
              value: _doubleValue(b?.minCellTempC),
              unit: '°C',
              icon: Icons.thermostat,
            ),
            TelemetryCard(
              title: 'Insulation',
              value: _doubleValue(b?.insulationResistanceKohm, digits: 0),
              unit: 'kΩ',
              icon: Icons.security,
            ),
            TelemetryCard(
              title: 'Alarm Count',
              value: _value(b?.alarmCount),
              icon: Icons.warning_amber,
            ),
          ],
        );
      },
    );
  }

  Widget _buildPcsTelemetryGrid(PcsTelemetry? p) {
    return LayoutBuilder(
      builder: (context, constraints) {
        int crossAxisCount = 3;

        if (constraints.maxWidth < 900) {
          crossAxisCount = 2;
        }

        if (constraints.maxWidth < 560) {
          crossAxisCount = 1;
        }

        return GridView.count(
          crossAxisCount: crossAxisCount,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: 2.35,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          children: [
            TelemetryCard(
              title: 'Active Power',
              value: _doubleValue(p?.activePowerKw),
              unit: 'kW',
              icon: Icons.bolt,
            ),
            TelemetryCard(
              title: 'Reactive Power',
              value: _doubleValue(p?.reactivePowerKvar),
              unit: 'kvar',
              icon: Icons.electrical_services,
            ),
            TelemetryCard(
              title: 'Power Factor',
              value: _doubleValue(p?.powerFactor, digits: 2),
              icon: Icons.speed,
            ),
            TelemetryCard(
              title: 'Frequency',
              value: _doubleValue(p?.frequencyHz, digits: 2),
              unit: 'Hz',
              icon: Icons.show_chart,
            ),
            TelemetryCard(
              title: 'Battery Voltage',
              value: _doubleValue(p?.batteryVoltageV),
              unit: 'V',
              icon: Icons.battery_charging_full,
            ),
            TelemetryCard(
              title: 'Battery Current',
              value: _doubleValue(p?.batteryCurrentA),
              unit: 'A',
              icon: Icons.electric_meter,
            ),
            TelemetryCard(
              title: 'DC Power',
              value: _doubleValue(p?.dcPowerKw),
              unit: 'kW',
              icon: Icons.power,
            ),
            TelemetryCard(
              title: 'Bus Voltage',
              value: _doubleValue(p?.busVoltageV),
              unit: 'V',
              icon: Icons.cable,
            ),
            TelemetryCard(
              title: 'AB Line Voltage',
              value: _doubleValue(p?.abVoltageV),
              unit: 'V',
              icon: Icons.offline_bolt,
            ),
            TelemetryCard(
              title: 'BC Line Voltage',
              value: _doubleValue(p?.bcVoltageV),
              unit: 'V',
              icon: Icons.offline_bolt,
            ),
            TelemetryCard(
              title: 'CA Line Voltage',
              value: _doubleValue(p?.caVoltageV),
              unit: 'V',
              icon: Icons.offline_bolt,
            ),
            TelemetryCard(
              title: 'Phase A Current',
              value: _doubleValue(p?.phaseACurrentA),
              unit: 'A',
              icon: Icons.electrical_services,
            ),
            TelemetryCard(
              title: 'IGBT Temp',
              value: _doubleValue(p?.igbtTemperatureC),
              unit: '°C',
              icon: Icons.device_thermostat,
            ),
            TelemetryCard(
              title: 'Ambient Temp',
              value: _doubleValue(p?.ambientTemperatureC),
              unit: '°C',
              icon: Icons.thermostat,
            ),
            TelemetryCard(
              title: 'Last PCS Update',
              value: _formatTime(p?.receivedAt),
              icon: Icons.access_time,
            ),
          ],
        );
      },
    );
  }

  Widget _buildChillerTelemetryGrid(ChillerTelemetry? t) {
    return LayoutBuilder(
      builder: (context, constraints) {
        int crossAxisCount = 3;

        if (constraints.maxWidth < 800) {
          crossAxisCount = 2;
        }

        if (constraints.maxWidth < 520) {
          crossAxisCount = 1;
        }

        return GridView.count(
          crossAxisCount: crossAxisCount,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: 2.35,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          children: [
            TelemetryCard(
              title: 'Outlet Water Temp',
              value: _doubleValue(t?.outletWaterTemp),
              unit: '°C',
              icon: Icons.thermostat,
            ),
            TelemetryCard(
              title: 'Return Water Temp',
              value: _doubleValue(t?.returnWaterTemp),
              unit: '°C',
              icon: Icons.thermostat_auto,
            ),
            TelemetryCard(
              title: 'Ambient Temp',
              value: _doubleValue(t?.ambientTemp),
              unit: '°C',
              icon: Icons.device_thermostat,
            ),
            TelemetryCard(
              title: 'Outlet Pressure',
              value: _doubleValue(t?.outletWaterPressure, digits: 2),
              unit: 'Bar',
              icon: Icons.speed,
            ),
            TelemetryCard(
              title: 'Return Pressure',
              value: _doubleValue(t?.returnWaterPressure, digits: 2),
              unit: 'Bar',
              icon: Icons.speed_outlined,
            ),
            TelemetryCard(
              title: 'Set Temperature',
              value: _value(t?.setTemperature),
              unit: '°C',
              icon: Icons.tune,
            ),
            TelemetryCard(
              title: 'Control Mode',
              value: _value(t?.controlMode),
              icon: Icons.settings,
            ),
            TelemetryCard(
              title: 'Make-up Pump',
              value: _value(t?.makeupPump),
              icon: Icons.water_drop,
            ),
            TelemetryCard(
              title: 'Last Chiller Received',
              value: _formatTime(t?.receivedAt),
              icon: Icons.access_time,
            ),
          ],
        );
      },
    );
  }

  Widget _buildRawPacketCard() {
    return Card(
      elevation: 1,
      child: ExpansionTile(
        title: const Text('Latest Raw UDP Packet'),
        subtitle: Text(_statusMessage),
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            color: Colors.black87,
            child: Text(
              _latestRawPacket == null
                  ? 'No UDP packet received yet'
                  : const JsonEncoder.withIndent('  ').convert(_latestRawPacket),
              style: const TextStyle(
                color: Colors.white,
                fontFamily: 'Consolas',
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildReadableCommandResultCard() {
    final response = _lastResponse;

    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: response == null
            ? const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Last Read / Command Result',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  SizedBox(height: 12),
                  Text('No command sent yet'),
                ],
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Last Read / Command Result',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 14),
                  _resultRow('Command', _value(response.command)),
                  _resultRow('Status', _value(response.status)),
                  _resultRow('Message', _value(response.message)),
                  const SizedBox(height: 10),
                  const Divider(),
                  const SizedBox(height: 10),
                  ..._buildCommandSpecificRows(response),
                ],
              ),
      ),
    );
  }

  List<Widget> _buildCommandSpecificRows(GatewayResponse response) {
    final command = response.command?.toUpperCase() ?? '';
    final data = response.data;
    final mockState = _asMap(data['mock_state']);

    if (mockState.isNotEmpty) {
      return [
        _resultSectionTitle('Mock State Result'),
        _resultRow('Water Pump', _value(mockState['water_pump'])),
        _resultRow('Control Mode', _value(mockState['control_mode'])),
        _resultRow('Set Temperature', '${_value(mockState['set_temperature'])} °C'),
        _resultRow('Outlet Temp', '${_value(mockState['outlet_water_temp'])} °C'),
        _resultRow('Return Temp', '${_value(mockState['return_water_temp'])} °C'),
        _resultRow('Fault Code', _value(mockState['fault_code'])),
      ];
    }

    if (command == 'READ_BMS' ||
        command == 'READ_BMS_ALL' ||
        command == 'BMS_READ_ALL' ||
        command == 'READ_BMS_ALARMS' ||
        command == 'BMS_READ_ALARMS') {
      return _buildBmsStateRows(data);
    }

    if (command.startsWith('BMS_') ||
        command == 'START_BMS_PRECHARGE' ||
        command == 'STOP_BMS_PRECHARGE' ||
        command == 'START_BMS_INSULATION_TEST' ||
        command == 'START_INSULATION_TEST' ||
        command == 'RESET_BCU' ||
        command == 'RESET_BMS') {
      return [
        _resultSectionTitle('BMS Command Result'),
        _resultRow('Command', _value(data['command'] ?? response.command)),
        _resultRow('Status', _value(data['status'] ?? response.status)),
        _resultRow('Description', _value(data['description'] ?? response.message)),
        if (data.containsKey('readback_value'))
          _resultRow('Readback', _value(data['readback_value'])),
      ];
    }

    if (command == 'PCS_READ' || command == 'READ_PCS' || command == 'PCS_STATUS') {
      return _buildPcsStateRows(data);
    }

    if (command.startsWith('PCS_')) {
      return [
        _resultSectionTitle('PCS Command Result'),
        _resultRow('PCS Command', _value(data['command'])),
        _resultRow('Status', _value(data['status'])),
        _resultRow('Old Value', _value(data['old_value'])),
        _resultRow('New Value', _value(data['new_value'])),
        _resultRow('Readback', _value(data['readback_value'])),
        _resultRow('Description', _value(data['description'])),
        if (_value(data['error']) != '--' && _value(data['error']).isNotEmpty)
          _resultRow('Error', _value(data['error'])),
      ];
    }

    if (command == 'READ_ALL_ASSETS' || command == 'READ_GATEWAY_TELEMETRY') {
      final bms = _extractBmsFromTelemetryPacket(data);
      if (bms.isNotEmpty) {
        return _buildBmsStateRows(bms);
      }

      final pcs = _extractPcsFromTelemetryPacket(data);
      if (pcs.isNotEmpty) {
        return _buildPcsStateRows(pcs);
      }
    }

    if (command == 'READ_TEMP') {
      return [
        _resultSectionTitle('Temperature Read Result'),
        _resultRow('Register', _value(data['register'])),
        _resultRow('Raw Value', _value(data['raw_value'])),
        _resultRow('Temperature', '${_value(data['temperature_celsius'])} °C'),
      ];
    }

    if (command == 'SET_TEMP') {
      final readback = _asMap(data['readback']);

      return [
        _resultSectionTitle('Temperature Set Result'),
        _resultRow('Written Temp', '${_value(data['temperature_celsius'])} °C'),
        _resultRow('Written Raw Value', _value(data['written_value'])),
        _resultRow('Verified', _value(data['verified'])),
        if (readback.isNotEmpty) ...[
          const SizedBox(height: 8),
          _resultSectionTitle('Readback'),
          _resultRow('Readback Raw', _value(readback['raw_value'])),
          _resultRow(
            'Readback Temp',
            '${_value(readback['temperature_celsius'])} °C',
          ),
        ],
      ];
    }

    if (command == 'READ_MODE') {
      return [
        _resultSectionTitle('Mode Read Result'),
        _resultRow('Register', _value(data['register'])),
        _resultRow('Raw Value', _value(data['raw_value'])),
        _resultRow('Mode', _value(data['mode'])),
      ];
    }

    if (command == 'SET_MODE') {
      final readback = _asMap(data['readback']);

      return [
        _resultSectionTitle('Mode Set Result'),
        _resultRow('Written Value', _value(data['written_value'])),
        _resultRow('Requested Mode', _value(data['requested_mode'])),
        _resultRow('Expected Readback', _value(data['expected_readback_value'])),
        _resultRow('Verified', _value(data['verified'])),
        if (readback.isNotEmpty) ...[
          const SizedBox(height: 8),
          _resultSectionTitle('Readback'),
          _resultRow('Readback Raw', _value(readback['raw_value'])),
          _resultRow('Readback Mode', _value(readback['mode'])),
        ],
      ];
    }

    if (command == 'READ_ONOFF') {
      return [
        _resultSectionTitle('ON/OFF Read Result'),
        _resultRow('Register', _value(data['register'])),
        _resultRow('Raw Value', _value(data['raw_value'])),
        _resultRow('Status', _value(data['status'])),
      ];
    }

    if (command == 'READ_SETTINGS') {
      final controlMode = _asMap(data['control_mode']);
      final onOff = _asMap(data['on_off_enable']);
      final setTemp = _asMap(data['set_temperature']);

      return [
        _resultSectionTitle('Settings Read Result'),
        _resultRow('Control Mode', _value(controlMode['mode'])),
        _resultRow('Control Raw', _value(controlMode['raw_value'])),
        _resultRow('ON/OFF Status', _value(onOff['status'])),
        _resultRow('ON/OFF Raw', _value(onOff['raw_value'])),
        _resultRow('Set Temp', '${_value(setTemp['temperature_celsius'])} °C'),
        _resultRow('Set Temp Raw', _value(setTemp['raw_value'])),
      ];
    }

    if (command == 'READ_ALL') {
      final telemetryData = _extractDataOrMockState(data);

      return [
        _resultSectionTitle('Telemetry Read Result'),
        _resultRow('Water Pump', _value(telemetryData['water_pump'])),
        _resultRow('Outlet Temp', '${_value(telemetryData['outlet_water_temp'])} °C'),
        _resultRow('Return Temp', '${_value(telemetryData['return_water_temp'])} °C'),
        _resultRow('Outlet Pressure', '${_value(telemetryData['outlet_water_pressure'])} Bar'),
        _resultRow('Return Pressure', '${_value(telemetryData['return_water_pressure'])} Bar'),
        _resultRow('Fault Code', _value(telemetryData['fault_code'])),
      ];
    }

    if (command == 'CHILLER_ON' || command == 'CHILLER_OFF') {
      final readback = _asMap(data['readback']);

      return [
        _resultSectionTitle('Power Command Result'),
        _resultRow('Register', _value(data['register'])),
        _resultRow('Written Value', _value(data['written_value'])),
        if (readback.isNotEmpty) ...[
          _resultRow('Readback Status', _value(readback['status'])),
          _resultRow('Readback Raw', _value(readback['raw_value'])),
        ],
      ];
    }

    if (data.isEmpty) {
      return [
        const Text('No detailed data available for this command.'),
      ];
    }

    return [
      _resultSectionTitle('Generic Command Data'),
      ...data.entries.map(
        (entry) => _resultRow(entry.key, _value(entry.value)),
      ),
    ];
  }


  List<Widget> _buildBmsStateRows(Map<String, dynamic> data) {
    final bms = BmsTelemetry.fromJson(data);

    return [
      _resultSectionTitle('BMS State'),
      _resultRow('Asset ID', _value(bms.assetId)),
      _resultRow('Comm Status', bms.effectiveCommStatus),
      _resultRow('SOC', '${_doubleValue(bms.socPercent)} %'),
      _resultRow('SOH', '${_doubleValue(bms.sohPercent)} %'),
      _resultRow('Rack Voltage', '${_doubleValue(bms.rackVoltageV)} V'),
      _resultRow('Rack Current', '${_doubleValue(bms.rackCurrentA)} A'),
      _resultRow('Power', '${_doubleValue(bms.powerKw, digits: 2)} kW'),
      _resultRow('BCU State', _value(bms.bcuState)),
      _resultRow('Current State', _value(bms.currentState)),
      _resultRow('Precharge Stage', _value(bms.prechargeStage)),
      _resultRow('Alarm Count', _value(bms.alarmCount)),
      if (bms.activeAlarms.isNotEmpty)
        _resultRow('Active Alarms', bms.activeAlarms.join(', ')),
    ];
  }

  List<Widget> _buildPcsStateRows(Map<String, dynamic> data) {
    return [
      _resultSectionTitle('PCS State'),
      _resultRow('Asset ID', _value(data['asset_id'])),
      _resultRow('Vendor', _value(data['vendor'])),
      _resultRow('Comm Status', _value(data['comm_status'])),
      _resultRow('Operating Status', _value(data['operating_status'])),
      _resultRow('Grid Status', _value(data['grid_offgrid_status'])),
      _resultRow('Fault Status', _value(data['fault_status'])),
      _resultRow('Active Power', '${_value(data['active_power_kw'])} kW'),
      _resultRow('Reactive Power', '${_value(data['reactive_power_kvar'])} kvar'),
      _resultRow('Frequency', '${_value(data['frequency_hz'])} Hz'),
      _resultRow('Battery Voltage', '${_value(data['battery_voltage_v'])} V'),
      _resultRow('Battery Current', '${_value(data['battery_current_a'])} A'),
      _resultRow('DC Power', '${_value(data['dc_power_kw'])} kW'),
      _resultRow('Power Factor', _value(data['power_factor'])),
      _resultRow('Last Update', _value(data['last_update_ts'])),
    ];
  }

  Widget _resultSectionTitle(String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        title,
        style: const TextStyle(
          fontWeight: FontWeight.w700,
          fontSize: 14,
        ),
      ),
    );
  }

  Widget _resultRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 135,
            child: Text(
              label,
              style: const TextStyle(
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              overflow: TextOverflow.visible,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRawCommandResponseCard() {
    return Card(
      elevation: 1,
      child: ExpansionTile(
        initiallyExpanded: false,
        title: const Text('Last Command Raw JSON'),
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            color: Colors.black87,
            child: Text(
              _lastResponse == null
                  ? 'No command sent yet'
                  : const JsonEncoder.withIndent('  ').convert({
                      'type': _lastResponse!.type,
                      'request_id': _lastResponse!.requestId,
                      'timestamp': _lastResponse!.timestamp,
                      'status': _lastResponse!.status,
                      'command': _lastResponse!.command,
                      'message': _lastResponse!.message,
                      'data': _lastResponse!.data,
                    }),
              style: const TextStyle(
                color: Colors.white,
                fontFamily: 'Consolas',
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
