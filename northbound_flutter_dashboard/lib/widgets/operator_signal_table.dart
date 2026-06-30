import 'package:flutter/material.dart';

import '../models/telemetry_signal.dart';
import '../utils/value_formatters.dart';

class OperatorSignalTable extends StatelessWidget {
  const OperatorSignalTable({
    super.key,
    required this.signals,
    this.onSelect,
    this.compact = false,
  });

  final List<TelemetrySignal> signals;
  final ValueChanged<TelemetrySignal>? onSelect;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    if (signals.isEmpty) {
      return const Card(child: ListTile(leading: Icon(Icons.search_off), title: Text('No fields to show')));
    }
    return Card(
      clipBehavior: Clip.antiAlias,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          showCheckboxColumn: false,
          columns: const [
            DataColumn(label: Text('Field')),
            DataColumn(label: Text('Value')),
            DataColumn(label: Text('Unit')),
            DataColumn(label: Text('Category')),
            DataColumn(label: Text('Quality')),
            DataColumn(label: Text('Address')),
            DataColumn(label: Text('Updated')),
            DataColumn(label: Text('Description / Enum')),
          ],
          rows: [
            for (final signal in signals)
              DataRow(
                onSelectChanged: onSelect == null ? null : (_) => onSelect!(signal),
                color: MaterialStateProperty.resolveWith((states) {
                  if (!signal.isGood) return Colors.orange.withOpacity(0.08);
                  final c = signal.category.toLowerCase();
                  if (c.contains('fault') || c.contains('alarm')) return Colors.red.withOpacity(0.035);
                  return null;
                }),
                cells: [
                  DataCell(SizedBox(
                    width: 310,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(signal.displayName, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600)),
                        Text(signal.name, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.bodySmall),
                      ],
                    ),
                  )),
                  DataCell(SizedBox(width: 150, child: Text(signal.valueText, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700)))),
                  DataCell(Text(signal.unit == null || signal.unit!.isEmpty ? '-' : signal.unit!)),
                  DataCell(Chip(label: Text(signal.category), visualDensity: VisualDensity.compact)),
                  DataCell(Chip(label: Text(signal.quality), visualDensity: VisualDensity.compact)),
                  DataCell(Text(signal.address == null ? '-' : '0x${signal.address!.toRadixString(16).toUpperCase()}')),
                  DataCell(Text(ValueFormatters.compactDateTime(signal.timestampUtc))),
                  DataCell(SizedBox(width: 320, child: Text(_description(signal), overflow: TextOverflow.ellipsis))),
                ],
              ),
          ],
        ),
      ),
    );
  }

  String _description(TelemetrySignal signal) {
    final parts = <String>[];
    if (signal.description != null && signal.description!.trim().isNotEmpty) parts.add(signal.description!.trim());
    if (signal.enumText != null && signal.enumText!.trim().isNotEmpty) parts.add(signal.enumText!.trim());
    return parts.isEmpty ? '-' : parts.join(' • ');
  }
}
