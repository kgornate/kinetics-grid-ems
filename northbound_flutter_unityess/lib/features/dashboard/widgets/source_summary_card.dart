
import 'package:flutter/material.dart';

import '../models/source_home_summary.dart';

class SourceSummaryCard extends StatelessWidget {
  const SourceSummaryCard({
    super.key,
    required this.source,
  });

  final SourceHomeSummary source;

  @override
  Widget build(BuildContext context) {
    final badgeColor = source.healthy
        ? const Color(0xFF36B37E)
        : const Color(0xFFF59E0B);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundColor: const Color(0xFFEAF2FF),
                  child: Icon(
                    Icons.storage_rounded,
                    color: badgeColor,
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        source.shortTitle,
                        style: Theme.of(context).textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${source.sourceId} • ${source.host}:${source.port}',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: const Color(0xFF6C7B8A),
                            ),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: source.online
                        ? const Color(0xFFEAF8F1)
                        : const Color(0xFFFFF2F2),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Text(
                    source.online ? 'ONLINE' : 'OFFLINE',
                    style: TextStyle(
                      color: source.online
                          ? const Color(0xFF228B5A)
                          : const Color(0xFFC53939),
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                _metricChip(
                  context,
                  label: 'BESS Status',
                  value: source.bessStatusLabel,
                  icon: Icons.power_settings_new_rounded,
                  valueColor: _bessStatusColor(source.bessOn),
                ),
                _metricChip(
                  context,
                  label: 'Mode',
                  value: source.bessModeLabel,
                  icon: Icons.settings_input_component_rounded,
                ),
                _metricChip(
                  context,
                  label: 'SOC',
                  value: source.soc != null
                      ? '${source.soc!.toStringAsFixed(1)} %'
                      : '--',
                  icon: Icons.battery_full_rounded,
                ),
                _metricChip(
                  context,
                  label: 'Active Power',
                  value: source.activePowerKw != null
                      ? '${source.activePowerKw!.toStringAsFixed(1)} kW'
                      : '--',
                  icon: Icons.electric_bolt_rounded,
                ),
                _metricChip(
                  context,
                  label: 'Assets Online',
                  value: '${source.onlineAssetCount}/${source.assetCount}',
                  icon: Icons.wifi_tethering_rounded,
                ),
                _metricChip(
                  context,
                  label: 'Fire',
                  value: source.fireAlarmActive ? 'Alarm' : 'Normal',
                  icon: Icons.local_fire_department_rounded,
                  valueColor: source.fireAlarmActive
                      ? const Color(0xFFC53939)
                      : const Color(0xFF228B5A),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              source.controlAuthorityLabel,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: const Color(0xFF6C7B8A),
                    fontWeight: FontWeight.w600,
                  ),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _statusPill('BESS ${source.bessStatusLabel}', source.bessOn != false),
                _statusPill('PCS', source.pcsOnline),
                _statusPill('BMS', source.bmsOnline),
                _statusPill('Liquid Cooling', source.liquidCoolingOnline),
                _statusPill('Fire', source.fireOnline),
                _statusPill('Dehumidifier', source.dehumidifierOnline),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Color _bessStatusColor(bool? on) {
    if (on == null) return const Color(0xFF6C7B8A);
    return on ? const Color(0xFF228B5A) : const Color(0xFFC53939);
  }

  Widget _metricChip(
    BuildContext context, {
    required String label,
    required String value,
    required IconData icon,
    Color? valueColor,
  }) {
    return Container(
      width: 180,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFD),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE6EBF2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 16, color: const Color(0xFF5A6E90)),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  label,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: const Color(0xFF6C7B8A),
                      ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            value,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                  color: valueColor,
                ),
          ),
        ],
      ),
    );
  }

  Widget _statusPill(String label, bool online) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: online ? const Color(0xFFEAF8F1) : const Color(0xFFFFF2F2),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: online ? const Color(0xFFCFECDC) : const Color(0xFFF5D3D3),
        ),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w700,
          color: online ? const Color(0xFF228B5A) : const Color(0xFFC53939),
        ),
      ),
    );
  }
}
