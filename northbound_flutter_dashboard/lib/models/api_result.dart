class ApiResult<T> {
  const ApiResult.success(this.data)
      : error = null,
        isSuccess = true;

  const ApiResult.failure(this.error)
      : data = null,
        isSuccess = false;

  final T? data;
  final String? error;
  final bool isSuccess;
}
