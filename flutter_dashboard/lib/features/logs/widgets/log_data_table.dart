import 'package:flutter/material.dart';

import '../../../models/log_models.dart';
import 'log_empty_state.dart';

class LogDataTable extends StatelessWidget {
  const LogDataTable({
    super.key,
    required this.title,
    required this.response,
    required this.preferredColumns,
    required this.fallbackAssetId,
  });

  final String title;
  final LogApiResponse? response;
  final List<String> preferredColumns;
  final String fallbackAssetId;

  String _value(dynamic value) {
    if (value == null) return '--';
    return value.toString();
  }

  @override
  Widget build(BuildContext context) {
    final response = this.response;
    if (response == null) {
      return LogEmptyState(
        title: title,
        message: 'Press Refresh Logs to load data from i.MX93.',
      );
    }

    if (!response.isOk) {
      return LogEmptyState(
        title: title,
        message: response.message ?? 'API returned status: ${response.status}',
      );
    }

    final rows = response.rows;
    if (rows.isEmpty) {
      return LogEmptyState(
        title: title,
        message: 'No rows found in ${response.fileName ?? 'log file'}.',
      );
    }

    final availableColumns = preferredColumns.where((column) {
      return rows.any((row) => row.containsKey(column));
    }).toList();

    final columns = availableColumns.isNotEmpty
        ? availableColumns
        : rows.first.keys.map((key) => key.toString()).toList();

    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
      child: Card(
        elevation: 1,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _TableHeader(
              title: title,
              response: response,
              fallbackAssetId: fallbackAssetId,
            ),
            const Divider(height: 1),
            Expanded(
              child: Scrollbar(
                thumbVisibility: true,
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: SingleChildScrollView(
                    child: DataTable(
                      headingRowColor: WidgetStateProperty.all(
                        Colors.blueGrey.withValues(alpha: 0.08),
                      ),
                      columns: columns.map((column) {
                        return DataColumn(
                          label: Text(
                            column,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                        );
                      }).toList(),
                      rows: rows.map((row) {
                        return DataRow(
                          cells: columns.map((column) {
                            final text = _value(row[column]);
                            final isLong = text.length > 45;
                            return DataCell(
                              SizedBox(
                                width: isLong ? 380 : null,
                                child: SelectableText(
                                  text,
                                  maxLines: isLong ? 3 : 1,
                                ),
                              ),
                            );
                          }).toList(),
                        );
                      }).toList(),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TableHeader extends StatelessWidget {
  const _TableHeader({
    required this.title,
    required this.response,
    required this.fallbackAssetId,
  });

  final String title;
  final LogApiResponse response;
  final String fallbackAssetId;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(14),
      child: Wrap(
        spacing: 18,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w700,
            ),
          ),
          Text('Asset: ${response.assetId.isNotEmpty ? response.assetId : fallbackAssetId}'),
          Text('File: ${response.fileName ?? '--'}'),
          Text('Total rows: ${response.totalRows}'),
          Text('Filtered: ${response.filteredRows}'),
          Text('Showing: ${response.rowsCount}'),
          Text('Limit: ${response.limit}'),
        ],
      ),
    );
  }
}
