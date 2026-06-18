import 'package:flutter/material.dart';

import '../../../models/log_models.dart';
import 'log_info_row.dart';

class StorageStatusCard extends StatelessWidget {
  const StorageStatusCard({
    super.key,
    required this.status,
  });

  final StorageStatus? status;

  @override
  Widget build(BuildContext context) {
    final status = this.status;
    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: status == null
            ? const Text('Storage status not loaded yet.')
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Storage Status',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 12),
                  LogInfoRow(label: 'API Status', value: status.status),
                  LogInfoRow(label: 'Base Path', value: status.basePath),
                  LogInfoRow(label: 'Asset ID', value: status.assetId),
                  LogInfoRow(label: 'Base Path Exists', value: status.exists.toString()),
                  LogInfoRow(
                    label: 'Telemetry Directory Exists',
                    value: status.telemetryDirExists.toString(),
                  ),
                  LogInfoRow(label: 'Events File Exists', value: status.eventsFileExists.toString()),
                  LogInfoRow(label: 'Errors File Exists', value: status.errorsFileExists.toString()),
                  LogInfoRow(
                    label: 'Metadata File Exists',
                    value: status.metadataFileExists.toString(),
                  ),
                  LogInfoRow(label: 'Telemetry Files', value: status.telemetryFilesCount.toString()),
                  LogInfoRow(label: 'Latest Telemetry File', value: status.latestTelemetryFile ?? '--'),
                  const Divider(height: 22),
                  LogInfoRow(label: 'Disk Total', value: formatBytes(status.diskTotalBytes)),
                  LogInfoRow(label: 'Disk Used', value: formatBytes(status.diskUsedBytes)),
                  LogInfoRow(label: 'Disk Free', value: formatBytes(status.diskFreeBytes)),
                  const Divider(height: 22),
                  LogInfoRow(label: 'EMS Logs Total Size', value: formatBytes(status.logTotalBytes)),
                  LogInfoRow(label: 'Telemetry Logs Size', value: formatBytes(status.telemetryLogBytes)),
                  LogInfoRow(label: 'Event Log Size', value: formatBytes(status.eventLogBytes)),
                  LogInfoRow(label: 'Error Log Size', value: formatBytes(status.errorLogBytes)),
                  LogInfoRow(label: 'Metadata Size', value: formatBytes(status.metadataBytes)),
                ],
              ),
      ),
    );
  }
}

class LogFilesCard extends StatelessWidget {
  const LogFilesCard({
    super.key,
    required this.files,
    required this.assetId,
    required this.onDateSelected,
  });

  final LogFilesResponse? files;
  final String assetId;
  final ValueChanged<String> onDateSelected;

  @override
  Widget build(BuildContext context) {
    final files = this.files;
    return Card(
      elevation: 1,
      child: ExpansionTile(
        initiallyExpanded: true,
        title: Text('Available Telemetry Log Files - $assetId'),
        subtitle: Text(
          files == null ? 'Not loaded' : '${files.filesCount} file(s) available',
        ),
        children: [
          if (files == null || files.files.isEmpty)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('No log files available.'),
            )
          else
            ...files.files.map(
              (file) => ListTile(
                dense: true,
                leading: const Icon(Icons.description),
                title: Text(file),
                subtitle: Text(assetId),
                onTap: () => onDateSelected(file.replaceAll('.csv', '')),
              ),
            ),
        ],
      ),
    );
  }
}

class MetadataCard extends StatelessWidget {
  const MetadataCard({
    super.key,
    required this.metadata,
  });

  final MetadataResponse? metadata;

  @override
  Widget build(BuildContext context) {
    final metadata = this.metadata;
    return Card(
      elevation: 1,
      child: ExpansionTile(
        initiallyExpanded: true,
        title: const Text('Gateway Metadata'),
        subtitle: Text(metadata == null ? 'Not loaded' : metadata.status),
        children: [
          if (metadata == null || metadata.metadata.isEmpty)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('No metadata loaded.'),
            )
          else
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: metadata.metadata.entries.map((entry) {
                  return LogInfoRow(label: entry.key, value: entry.value.toString());
                }).toList(),
              ),
            ),
        ],
      ),
    );
  }
}
