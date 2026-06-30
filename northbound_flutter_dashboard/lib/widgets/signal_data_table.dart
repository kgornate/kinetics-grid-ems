import 'package:flutter/material.dart';

import '../models/telemetry_signal.dart';
import '../utils/value_formatters.dart';

class SignalDataTable extends StatelessWidget {
  const SignalDataTable({super.key, required this.signals, this.onSelect});

  final List<TelemetrySignal> signals;
  final ValueChanged<TelemetrySignal>? onSelect;

  @override
  Widget build(BuildContext context) {
    if (signals.isEmpty) {
      return const Card(child: ListTile(leading: Icon(Icons.search_off), title: Text('No signals to show')));
    }
    return Card(
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
          ],
          rows: [
            for (final signal in signals)
              DataRow(
                onSelectChanged: onSelect == null ? null : (_) => onSelect!(signal),
                cells: [
                  DataCell(SizedBox(width: 260, child: Text(signal.displayName, overflow: TextOverflow.ellipsis))),
                  DataCell(Text(signal.value?.toString() ?? '-')),
                  DataCell(Text(signal.unit ?? '-')),
                  DataCell(Text(signal.category)),
                  DataCell(Text(signal.quality)),
                  DataCell(Text(signal.address == null ? '-' : '0x${signal.address!.toRadixString(16).toUpperCase()}')),
                  DataCell(Text(ValueFormatters.compactDateTime(signal.timestampUtc))),
                ],
              ),
          ],
        ),
      ),
    );
  }
}
