import 'dart:typed_data';

import 'download_result.dart';

Future<DownloadResult> saveBytesImpl({
  required Uint8List bytes,
  required String fileName,
  required String mimeType,
}) async {
  throw UnsupportedError('File download is not supported on this platform.');
}
