class DownloadResult {
  const DownloadResult({
    required this.fileName,
    this.path,
  });

  final String fileName;
  final String? path;

  String get userMessage {
    if (path == null || path!.isEmpty) {
      return 'Download started: $fileName';
    }
    return 'Saved: $path';
  }
}
