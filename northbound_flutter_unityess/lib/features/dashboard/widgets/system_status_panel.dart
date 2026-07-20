
import 'package:flutter/material.dart';

import '../models/source_home_summary.dart';

class SystemStatusPanel extends StatelessWidget {
  const SystemStatusPanel({
    super.key,
    required this.sources,
  });

  final List<SourceHomeSummary> sources;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'System Status',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
            ),
            const SizedBox(height: 14),
            ...sources.map(
              (source) => Padding(
                padding: const EdgeInsets.only(bottom: 14),
                child: _SourceStatusGroup(source: source),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SourceStatusGroup extends StatelessWidget {
  const _SourceStatusGroup({required this.source});

  final SourceHomeSummary source;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFD),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE6EBF2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            source.shortTitle,
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 10),
          _statusRow('BESS', source.bessOn != false, overrideText: source.bessStatusLabel),
          _statusRow('Mode', true, overrideText: source.bessModeLabel),
          _statusRow('PCS', source.pcsOnline),
          _statusRow('BMS', source.bmsOnline),
          _statusRow('Liquid Cooling', source.liquidCoolingOnline),
          _statusRow('Fire', source.fireOnline),
          _statusRow('Dehumidifier', source.dehumidifierOnline),
        ],
      ),
    );
  }

  Widget _statusRow(String label, bool online, {String? overrideText}) {
    final positive = online;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Icon(
            positive ? Icons.wifi : Icons.wifi_off,
            size: 18,
            color: positive ? const Color(0xFF36B37E) : const Color(0xFFC53939),
          ),
          const SizedBox(width: 10),
          Expanded(child: Text(label)),
          Text(
            overrideText ?? (positive ? 'Online' : 'Offline'),
            style: TextStyle(
              fontWeight: FontWeight.w700,
              color: positive
                  ? const Color(0xFF228B5A)
                  : const Color(0xFFC53939),
            ),
          ),
        ],
      ),
    );
  }
}
