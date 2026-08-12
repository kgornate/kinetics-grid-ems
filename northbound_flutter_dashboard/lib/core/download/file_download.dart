import 'dart:typed_data';

import 'download_result.dart';
import 'file_download_stub.dart'
    if (dart.library.io) 'file_download_io.dart'
    if (dart.library.html) 'file_download_web.dart';

Future<DownloadResult> saveBytes({
  required Uint8List bytes,
  required String fileName,
  required String mimeType,
}) {
  return saveBytesImpl(
    bytes: bytes,
    fileName: fileName,
    mimeType: mimeType,
  );
}
