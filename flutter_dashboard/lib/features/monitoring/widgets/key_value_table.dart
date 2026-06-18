import 'package:flutter/material.dart';

class KeyValueTable extends StatelessWidget {
  final Map<String, dynamic> values;
  final List<String>? preferredKeys;
  final int maxRows;

  const KeyValueTable({
    super.key,
    required this.values,
    this.preferredKeys,
    this.maxRows = 12,
  });

  @override
  Widget build(BuildContext context) {
    final entries = _orderedEntries().take(maxRows).toList(growable: false);
    if (entries.isEmpty) return const Text('No values available');
    return Column(
      children: entries
          .map(
            (entry) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 170,
                    child: Text(
                      _label(entry.key),
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                  Expanded(child: Text(_format(entry.value))),
                ],
              ),
            ),
          )
          .toList(growable: false),
    );
  }

  Iterable<MapEntry<String, dynamic>> _orderedEntries() sync* {
    final used = <String>{};
    for (final key in preferredKeys ?? const <String>[]) {
      if (values.containsKey(key)) {
        used.add(key);
        yield MapEntry(key, values[key]);
      }
    }
    for (final entry in values.entries) {
      if (!used.contains(entry.key) && !_isNoisy(entry.key, entry.value)) {
        yield entry;
      }
    }
  }

  bool _isNoisy(String key, dynamic value) {
    final k = key.toLowerCase();
    if (k.contains('raw') || k.contains('debug') || k.contains('internal')) return true;
    if (value is Map || value is List) return true;
    return false;
  }

  String _label(String key) => key
      .replaceAll('_', ' ')
      .split(' ')
      .where((part) => part.isNotEmpty)
      .map((part) => part[0].toUpperCase() + part.substring(1))
      .join(' ');

  String _format(dynamic value) {
    if (value == null) return '--';
    if (value is double) return value.toStringAsFixed(2);
    return value.toString();
  }
}
