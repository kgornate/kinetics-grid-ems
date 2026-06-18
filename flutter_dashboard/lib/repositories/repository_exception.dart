/// Repository-level exception used by feature/UI layers.
class RepositoryException implements Exception {
  final String message;
  final Object? cause;

  const RepositoryException(this.message, {this.cause});

  @override
  String toString() => 'RepositoryException: $message';
}
