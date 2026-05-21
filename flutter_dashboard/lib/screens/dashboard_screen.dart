import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../models/chiller_telemetry.dart';
import '../models/gateway_response.dart';
import '../services/tcp_command_service.dart';
import '../services/udp_telemetry_service.dart';
import '../widgets/command_panel.dart';
import '../widgets/status_indicator.dart';
import '../widgets/telemetry_card.dart';

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
  StreamSubscription<Map<String, dynamic>>? _rawPacketSubscription;

  ChillerTelemetry? _latestTelemetry;
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
            'Telemetry received at ${_formatTime(telemetry.receivedAt)}';
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

      // If READ_ALL gives complete telemetry over TCP, update cards also.
      if (response.isOk && command.toUpperCase() == 'READ_ALL') {
        final data = _extractDataOrMockState(response.data);
        if (data.isNotEmpty) {
          _latestTelemetry = ChillerTelemetry.fromJson(data);
        }
      }
    });
  }

  @override
  void dispose() {
    _gatewayIpController.dispose();
    _telemetrySubscription?.cancel();
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

  @override
  Widget build(BuildContext context) {
    final telemetry = _latestTelemetry;

    return Scaffold(
      appBar: AppBar(
        title: const Text('EMS Chiller Dashboard'),
        actions: [
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
                  _buildStatusRow(telemetry),
                  const SizedBox(height: 16),
                  _buildTelemetryGrid(telemetry),
                  const SizedBox(height: 16),
                  _buildRawPacketCard(),
                ],
              ),
            ),
          ),
          Container(width: 1, color: Colors.black12),
          SizedBox(
            width: 430,
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

  Widget _buildStatusRow(ChillerTelemetry? telemetry) {
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
          label: 'Chiller Comm',
          status: telemetry?.communicationStatus,
          active: telemetry?.isOnline ?? false,
        ),
        StatusIndicator(
          label: 'Water Pump',
          status: telemetry?.waterPump,
          active: telemetry?.waterPump == 'RUNNING',
        ),
        StatusIndicator(
          label: 'Compressor 1',
          status: telemetry?.compressor1,
          active: telemetry?.compressor1 == 'RUNNING',
        ),
        StatusIndicator(
          label: 'Fault',
          status: _value(telemetry?.faultCode),
          active: telemetry?.faultCode == 0 || telemetry?.faultCode == '0',
        ),
      ],
    );
  }

  Widget _buildTelemetryGrid(ChillerTelemetry? t) {
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
              title: 'Last Received',
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