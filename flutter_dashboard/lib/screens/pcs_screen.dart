import 'dart:async';

import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../models/gateway_response.dart';
import '../models/pcs_telemetry.dart';
import '../services/tcp_command_service.dart';
import '../widgets/pcs_command_panel.dart';
import '../widgets/telemetry_card.dart';

class PcsScreen extends StatefulWidget {
  final String gatewayIp;
  final PcsTelemetry? initialTelemetry;
  final Stream<PcsTelemetry> pcsTelemetryStream;

  const PcsScreen({
    super.key,
    required this.gatewayIp,
    required this.initialTelemetry,
    required this.pcsTelemetryStream,
  });

  @override
  State<PcsScreen> createState() => _PcsScreenState();
}

class _PcsScreenState extends State<PcsScreen> {
  StreamSubscription<PcsTelemetry>? _pcsSubscription;
  PcsTelemetry? _pcs;
  GatewayResponse? _lastResponse;
  bool _commandInProgress = false;
  String _statusMessage = 'PCS detail screen opened';

  @override
  void initState() {
    super.initState();
    _pcs = widget.initialTelemetry;
    _pcsSubscription = widget.pcsTelemetryStream.listen((pcs) {
      setState(() {
        _pcs = pcs;
        _statusMessage = 'PCS telemetry updated at ${_formatTime(pcs.receivedAt)}';
      });
    });
  }

  @override
  void dispose() {
    _pcsSubscription?.cancel();
    super.dispose();
  }

  TcpCommandService _tcpService() {
    return TcpCommandService(
      gatewayIp: widget.gatewayIp,
      gatewayPort: AppConfig.tcpCommandPort,
      timeout: AppConfig.tcpTimeout,
    );
  }

  Future<void> _sendCommand(String command, {dynamic value}) async {
    setState(() {
      _commandInProgress = true;
      _statusMessage = 'Sending PCS command: $command';
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
          ? 'PCS command successful: $command'
          : 'PCS command failed: ${response.message}';

      final upperCommand = command.toUpperCase();
      if (response.isOk &&
          (upperCommand == 'PCS_READ' || upperCommand == 'READ_PCS')) {
        if (response.data.isNotEmpty) {
          _pcs = PcsTelemetry.fromJson(response.data);
        }
      }

      if (response.isOk &&
          (upperCommand == 'READ_ALL_ASSETS' ||
              upperCommand == 'READ_GATEWAY_TELEMETRY')) {
        final pcsData = _extractPcsFromTelemetryPacket(response.data);
        if (pcsData.isNotEmpty) {
          _pcs = PcsTelemetry.fromJson(pcsData);
        }
      }
    });
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return {};
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

  String _value(dynamic value) {
    if (value == null) return '--';
    final text = value.toString();
    return text.isEmpty ? '--' : text;
  }

  String _doubleValue(double? value, {int digits = 1}) {
    if (value == null) return '--';
    return value.toStringAsFixed(digits);
  }

  String _rawValue(int? value) {
    if (value == null) return '--';
    return '0x${value.toRadixString(16).toUpperCase().padLeft(4, '0')} / $value';
  }

  String _formatTime(DateTime? time) {
    if (time == null) return '--';
    return '${time.hour.toString().padLeft(2, '0')}:'
        '${time.minute.toString().padLeft(2, '0')}:'
        '${time.second.toString().padLeft(2, '0')}';
  }

  String _yesNo(bool value) => value ? 'YES' : 'NO';

  @override
  Widget build(BuildContext context) {
    final pcs = _pcs;

    return Scaffold(
      appBar: AppBar(
        title: const Text('PCS / Inverter Detail Screen'),
        actions: [
          if (_commandInProgress)
            const Padding(
              padding: EdgeInsets.only(right: 16),
              child: Center(
                child: SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(strokeWidth: 3),
                ),
              ),
            ),
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(
              child: Text(
                pcs?.isOnline == true ? 'PCS ONLINE' : 'PCS OFFLINE',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: pcs?.isOnline == true ? Colors.green : Colors.red,
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
                  _buildStatusBanner(pcs),
                  const SizedBox(height: 16),
                  _sectionHeader('PCS Health, Faults and Operating Status'),
                  const SizedBox(height: 10),
                  _buildHealthStatusGrid(pcs),
                  const SizedBox(height: 20),
                  _sectionHeader('Detailed PCS Fault Words 0x1700 to 0x1707'),
                  const SizedBox(height: 10),
                  _buildFaultSummaryCard(pcs),
                  const SizedBox(height: 10),
                  _buildDetailedFaultGrid(pcs),
                  const SizedBox(height: 20),
                  _sectionHeader('PCS Power and Grid Readings'),
                  const SizedBox(height: 10),
                  _buildPowerGrid(pcs),
                  const SizedBox(height: 20),
                  _sectionHeader('PCS AC Voltage and Current Readings'),
                  const SizedBox(height: 10),
                  _buildAcGrid(pcs),
                  const SizedBox(height: 20),
                  _sectionHeader('PCS DC / Battery Readings'),
                  const SizedBox(height: 10),
                  _buildDcBatteryGrid(pcs),
                  const SizedBox(height: 20),
                  _sectionHeader('PCS Temperature Readings'),
                  const SizedBox(height: 10),
                  _buildTemperatureGrid(pcs),
                  const SizedBox(height: 20),
                  _sectionHeader('PCS Identification and Raw Status Values'),
                  const SizedBox(height: 10),
                  _buildMetadataGrid(pcs),
                  const SizedBox(height: 20),
                  _buildFaultNotesCard(pcs),
                ],
              ),
            ),
          ),
          Container(width: 1, color: Colors.black12),
          SizedBox(
            width: 440,
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  PcsCommandPanel(onSendCommand: _sendCommand),
                  const SizedBox(height: 16),
                  _buildLastCommandCard(),
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

  Widget _buildStatusBanner(PcsTelemetry? p) {
    final hasFault = p?.hasAnyFault ?? false;
    final online = p?.isOnline ?? false;
    final running = p?.isRunning ?? false;

    String title;
    String subtitle;
    IconData icon;
    Color color;

    if (p == null) {
      title = 'No PCS telemetry received yet';
      subtitle = 'Waiting for UDP telemetry from i.MX93 gateway.';
      icon = Icons.hourglass_empty;
      color = Colors.grey;
    } else if (!online) {
      title = 'PCS communication is not online';
      subtitle = 'Check Modbus TCP link, PCS power, eth1 network and gateway PCS service.';
      icon = Icons.link_off;
      color = Colors.orange;
    } else if (hasFault) {
      title = 'PCS fault detected';
      subtitle = 'Fault status is active. Check PCS fault words/details from backend and hardware panel.';
      icon = Icons.warning_amber;
      color = Colors.red;
    } else if (running) {
      title = 'PCS is running';
      subtitle = 'Communication is online and operating status indicates running/operation.';
      icon = Icons.check_circle;
      color = Colors.green;
    } else {
      title = 'PCS online but not running';
      subtitle = 'PCS may be shutdown, powering on, standby, commissioning or waiting for command/interlocks.';
      icon = Icons.info;
      color = Colors.blueGrey;
    }

    return Card(
      elevation: 1,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          border: Border(left: BorderSide(color: color, width: 6)),
        ),
        child: Row(
          children: [
            Icon(icon, color: color, size: 36),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(subtitle),
                  const SizedBox(height: 8),
                  Text(
                    _statusMessage,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHealthStatusGrid(PcsTelemetry? p) {
    return _responsiveGrid([
      _statusCard(
        title: 'Communication',
        value: _value(p?.commStatus),
        active: p?.isOnline ?? false,
        icon: Icons.settings_ethernet,
      ),
      _statusCard(
        title: 'Fault Status',
        value: p == null ? '--' : (p.hasAnyFault ? 'FAULT' : 'NORMAL'),
        active: p != null && !p.hasAnyFault,
        icon: Icons.health_and_safety,
      ),
      _statusCard(
        title: 'Detailed Fault Count',
        value: p == null ? '--' : p.faultCount.toString(),
        active: p != null && p.faultCount == 0,
        icon: Icons.bug_report,
      ),
      _statusCard(
        title: 'Operating Status',
        value: _value(p?.operatingStatus),
        active: p?.isRunning ?? false,
        icon: Icons.precision_manufacturing,
      ),
      _statusCard(
        title: 'Grid / Off-grid Status',
        value: _value(p?.gridOffgridStatus),
        active: _gridStatusHealthy(p),
        icon: Icons.grid_on,
      ),
      _statusCard(
        title: 'Gateway Error Field',
        value: _value(p?.error),
        active: p != null && (p.error == null || p.error!.isEmpty || p.error == 'None'),
        icon: Icons.report,
      ),
      _statusCard(
        title: 'Running Flag',
        value: p == null ? '--' : _yesNo(p.isRunning),
        active: p?.isRunning ?? false,
        icon: Icons.play_circle,
      ),
      _statusCard(
        title: 'Online Flag',
        value: p == null ? '--' : _yesNo(p.isOnline),
        active: p?.isOnline ?? false,
        icon: Icons.wifi_tethering,
      ),
      _statusCard(
        title: 'Last UDP Packet',
        value: _formatTime(p?.receivedAt),
        active: p != null,
        icon: Icons.access_time,
      ),
    ], childAspectRatio: 2.25);
  }

  bool _gridStatusHealthy(PcsTelemetry? p) {
    final status = p?.gridOffgridStatus?.toLowerCase() ?? '';
    if (status.contains('fault')) return false;
    return p != null && status.isNotEmpty;
  }

  Widget _statusCard({
    required String title,
    required String value,
    required bool active,
    required IconData icon,
  }) {
    final color = active ? Colors.green : Colors.redAccent;

    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(icon, color: color, size: 30),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(title),
                  const SizedBox(height: 6),
                  Text(
                    value,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                    overflow: TextOverflow.ellipsis,
                    maxLines: 2,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPowerGrid(PcsTelemetry? p) {
    return _responsiveGrid([
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
        title: 'Apparent Power',
        value: _doubleValue(p?.apparentPowerKva),
        unit: 'kVA',
        icon: Icons.power,
      ),
      TelemetryCard(
        title: 'Power Factor',
        value: _doubleValue(p?.powerFactor, digits: 2),
        icon: Icons.speed,
      ),
      TelemetryCard(
        title: 'Grid Frequency',
        value: _doubleValue(p?.frequencyHz, digits: 2),
        unit: 'Hz',
        icon: Icons.show_chart,
      ),
    ]);
  }

  Widget _buildAcGrid(PcsTelemetry? p) {
    return _responsiveGrid([
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
        title: 'Phase A Voltage',
        value: _doubleValue(p?.phaseAVoltageV),
        unit: 'V',
        icon: Icons.electric_bolt,
      ),
      TelemetryCard(
        title: 'Phase B Voltage',
        value: _doubleValue(p?.phaseBVoltageV),
        unit: 'V',
        icon: Icons.electric_bolt,
      ),
      TelemetryCard(
        title: 'Phase C Voltage',
        value: _doubleValue(p?.phaseCVoltageV),
        unit: 'V',
        icon: Icons.electric_bolt,
      ),
      TelemetryCard(
        title: 'Phase A Current',
        value: _doubleValue(p?.phaseACurrentA),
        unit: 'A',
        icon: Icons.electrical_services,
      ),
      TelemetryCard(
        title: 'Phase B Current',
        value: _doubleValue(p?.phaseBCurrentA),
        unit: 'A',
        icon: Icons.electrical_services,
      ),
      TelemetryCard(
        title: 'Phase C Current',
        value: _doubleValue(p?.phaseCCurrentA),
        unit: 'A',
        icon: Icons.electrical_services,
      ),
    ]);
  }

  Widget _buildDcBatteryGrid(PcsTelemetry? p) {
    return _responsiveGrid([
      TelemetryCard(
        title: 'Bus Voltage',
        value: _doubleValue(p?.busVoltageV),
        unit: 'V',
        icon: Icons.cable,
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
        title: 'DC Total Current',
        value: _doubleValue(p?.dcTotalCurrentA),
        unit: 'A',
        icon: Icons.compare_arrows,
      ),
    ]);
  }

  Widget _buildTemperatureGrid(PcsTelemetry? p) {
    return _responsiveGrid([
      TelemetryCard(
        title: 'IGBT Temperature',
        value: _doubleValue(p?.igbtTemperatureC),
        unit: '°C',
        icon: Icons.device_thermostat,
      ),
      TelemetryCard(
        title: 'Ambient Temperature',
        value: _doubleValue(p?.ambientTemperatureC),
        unit: '°C',
        icon: Icons.thermostat,
      ),
      TelemetryCard(
        title: 'Inductance Temperature',
        value: _doubleValue(p?.inductanceTemperatureC),
        unit: '°C',
        icon: Icons.thermostat_auto,
      ),
    ]);
  }

  Widget _buildMetadataGrid(PcsTelemetry? p) {
    return _responsiveGrid([
      TelemetryCard(
        title: 'Asset ID',
        value: _value(p?.assetId),
        icon: Icons.memory,
      ),
      TelemetryCard(
        title: 'Vendor',
        value: _value(p?.vendor),
        icon: Icons.factory,
      ),
      TelemetryCard(
        title: 'Gateway Last Update TS',
        value: _value(p?.lastUpdateTs),
        icon: Icons.schedule,
      ),
      TelemetryCard(
        title: 'Flutter Received At',
        value: _formatTime(p?.receivedAt),
        icon: Icons.access_time,
      ),
      TelemetryCard(
        title: 'Operating Status Raw',
        value: _rawValue(p?.operatingStatusRaw),
        icon: Icons.code,
      ),
      TelemetryCard(
        title: 'Grid Status Raw',
        value: _rawValue(p?.gridOffgridStatusRaw),
        icon: Icons.code,
      ),
    ], childAspectRatio: 2.05);
  }

  String _categoryTitle(String categoryKey) {
    switch (categoryKey) {
      case 'hardware_fault_word_1':
        return 'Hardware Fault Word 1';
      case 'hardware_fault_word_2':
        return 'Hardware Fault Word 2';
      case 'grid_fault_word':
        return 'Grid Fault Word';
      case 'bus_fault_word':
        return 'Bus Fault Word';
      case 'ac_capacitor_fault_word':
        return 'AC Capacitor Fault Word';
      case 'system_fault_word':
        return 'System Fault Word';
      case 'switch_fault_word':
        return 'Switch Fault Word';
      case 'other_fault_word':
        return 'Other Fault Word';
      default:
        return categoryKey.replaceAll('_', ' ');
    }
  }

  int? _faultRawValue(PcsTelemetry? p, String categoryKey) {
    if (p == null) return null;
    switch (categoryKey) {
      case 'hardware_fault_word_1':
        return p.hardwareFaultWord1Raw;
      case 'hardware_fault_word_2':
        return p.hardwareFaultWord2Raw;
      case 'grid_fault_word':
        return p.gridFaultWordRaw;
      case 'bus_fault_word':
        return p.busFaultWordRaw;
      case 'ac_capacitor_fault_word':
        return p.acCapacitorFaultWordRaw;
      case 'system_fault_word':
        return p.systemFaultWordRaw;
      case 'switch_fault_word':
        return p.switchFaultWordRaw;
      case 'other_fault_word':
        return p.otherFaultWordRaw;
      default:
        return null;
    }
  }

  Widget _buildFaultSummaryCard(PcsTelemetry? p) {
    final readError = p?.faultWordsReadError ?? '';
    final hasReadError = readError.isNotEmpty && readError != 'None';
    final hasFault = p?.hasAnyFault ?? false;
    final activeFaults = p?.activeFaults ?? const <String>[];

    Color color;
    IconData icon;
    String title;
    String subtitle;

    if (p == null) {
      color = Colors.grey;
      icon = Icons.hourglass_empty;
      title = 'Waiting for PCS fault telemetry';
      subtitle = 'No PCS UDP packet has been received yet.';
    } else if (hasReadError) {
      color = Colors.orange;
      icon = Icons.warning_amber;
      title = 'PCS detailed fault read issue';
      subtitle = readError;
    } else if (hasFault) {
      color = Colors.red;
      icon = Icons.report_problem;
      title = 'PCS has active fault condition';
      subtitle = '${p.faultCount} detailed fault(s) active. Check category cards below.';
    } else {
      color = Colors.green;
      icon = Icons.verified;
      title = 'No detailed PCS faults active';
      subtitle = 'All decoded fault words 0x1700 to 0x1707 are normal.';
    }

    return Card(
      elevation: 1,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          border: Border(left: BorderSide(color: color, width: 6)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color, size: 32),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: Theme.of(context).textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                      ),
                      const SizedBox(height: 4),
                      Text(subtitle),
                    ],
                  ),
                ),
              ],
            ),
            if (activeFaults.isNotEmpty) ...[
              const SizedBox(height: 12),
              const Divider(),
              Text(
                'Active Fault List',
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
              ),
              const SizedBox(height: 8),
              ...activeFaults.take(12).map(
                    (fault) => Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.circle, size: 8, color: Colors.red),
                          const SizedBox(width: 8),
                          Expanded(child: Text(fault)),
                        ],
                      ),
                    ),
                  ),
              if (activeFaults.length > 12)
                Text('+ ${activeFaults.length - 12} more fault(s)'),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildDetailedFaultGrid(PcsTelemetry? p) {
    const categories = <String>[
      'hardware_fault_word_1',
      'hardware_fault_word_2',
      'grid_fault_word',
      'bus_fault_word',
      'ac_capacitor_fault_word',
      'system_fault_word',
      'switch_fault_word',
      'other_fault_word',
    ];

    return _responsiveGrid(
      categories.map((categoryKey) {
        final rawValue = _faultRawValue(p, categoryKey);
        final faults = p?.faultCategories[categoryKey] ?? const <String>[];
        return _faultCategoryCard(
          title: _categoryTitle(categoryKey),
          rawValue: rawValue,
          faults: faults,
          hasTelemetry: p != null,
        );
      }).toList(),
      childAspectRatio: 1.55,
    );
  }

  Widget _faultCategoryCard({
    required String title,
    required int? rawValue,
    required List<String> faults,
    required bool hasTelemetry,
  }) {
    final hasFault = faults.isNotEmpty || ((rawValue ?? 0) != 0);
    final color = !hasTelemetry
        ? Colors.grey
        : hasFault
            ? Colors.red
            : Colors.green;
    final rawText = rawValue == null ? '--' : _rawValue(rawValue);

    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  hasFault ? Icons.warning_amber : Icons.check_circle,
                  color: color,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text('Raw: $rawText'),
            const Divider(height: 18),
            Expanded(
              child: faults.isEmpty
                  ? Text(
                      hasTelemetry ? 'No active faults' : 'Waiting for data',
                      style: TextStyle(color: color, fontWeight: FontWeight.w600),
                    )
                  : SingleChildScrollView(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: faults
                            .map(
                              (fault) => Padding(
                                padding: const EdgeInsets.only(bottom: 5),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const Icon(Icons.circle, size: 7, color: Colors.red),
                                    const SizedBox(width: 7),
                                    Expanded(child: Text(fault)),
                                  ],
                                ),
                              ),
                            )
                            .toList(),
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFaultNotesCard(PcsTelemetry? p) {
    return Card(
      elevation: 1,
      child: ExpansionTile(
        initiallyExpanded: p?.hasAnyFault == true,
        leading: Icon(
          p?.hasAnyFault == true ? Icons.warning_amber : Icons.info_outline,
          color: p?.hasAnyFault == true ? Colors.red : Colors.blueGrey,
        ),
        title: const Text('Fault and Status Notes'),
        subtitle: Text(
          p?.hasAnyFault == true
              ? 'PCS reports fault/status issue. Check detailed fault categories above.'
              : 'PCS status and detailed fault words are normal or waiting for telemetry.',
        ),
        children: const [
          Padding(
            padding: EdgeInsets.all(16),
            child: Text(
              'This screen displays the PCS operating status, grid/off-grid status, general fault status, and detailed NJOY fault words 0x1700 to 0x1707 when exposed by the i.MX93 backend. Fault categories include hardware, grid, bus, AC capacitor, system, switch and other inverter faults.',
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLastCommandCard() {
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
                    'Last PCS Command Result',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                  ),
                  SizedBox(height: 12),
                  Text('No PCS command sent from this screen yet'),
                ],
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Last PCS Command Result',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 12),
                  _resultRow('Command', _value(response.command)),
                  _resultRow('Status', _value(response.status)),
                  _resultRow('Message', _value(response.message)),
                  const Divider(height: 24),
                  _resultRow('PCS Command', _value(response.data['command'])),
                  _resultRow('Old Value', _value(response.data['old_value'])),
                  _resultRow('New Value', _value(response.data['new_value'])),
                  _resultRow('Readback', _value(response.data['readback_value'])),
                  _resultRow('Description', _value(response.data['description'])),
                  if (_value(response.data['error']) != '--')
                    _resultRow('Error', _value(response.data['error'])),
                ],
              ),
      ),
    );
  }

  Widget _resultRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }

  Widget _responsiveGrid(List<Widget> children, {double childAspectRatio = 2.35}) {
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
          childAspectRatio: childAspectRatio,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          children: children,
        );
      },
    );
  }
}
