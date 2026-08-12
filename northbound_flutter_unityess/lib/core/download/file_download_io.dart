import 'dart:io';
import 'dart:typed_data';

import 'download_result.dart';

Future<DownloadResult> saveBytesImpl({
  required Uint8List bytes,
  required String fileName,
  required String mimeType,
}) async {
  final dir = await _preferredDownloadDirectory();
  if (!await dir.exists()) {
    await dir.create(recursive: true);
  }

  final safeName = _safeFileName(fileName);
  final file = File('${dir.path}${Platform.pathSeparator}$safeName');
  await file.writeAsBytes(bytes, flush: true);
  return DownloadResult(fileName: safeName, path: file.path);
}

Future<Directory> _preferredDownloadDirectory() async {
  final env = Platform.environment;
  final home = env['USERPROFILE'] ?? env['HOME'];
  if (home != null && home.isNotEmpty) {
    return Directory('$home${Platform.pathSeparator}Downloads');
  }
  return Directory.current;
}

String _safeFileName(String value) {
  final cleaned = value.replaceAll(RegExp(r'[\\/:*?"<>|]+'), '_').trim();
  return cleaned.isEmpty ? 'export.csv' : cleaned;
}
