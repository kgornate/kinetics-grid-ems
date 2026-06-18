String dashboardValue(dynamic value) {
  if (value == null) return '--';
  return value.toString();
}

String dashboardDoubleValue(double? value, {int digits = 1}) {
  if (value == null) return '--';
  return value.toStringAsFixed(digits);
}

String dashboardFormatTime(DateTime? time) {
  if (time == null) return '--';
  return '${time.hour.toString().padLeft(2, '0')}:'
      '${time.minute.toString().padLeft(2, '0')}:'
      '${time.second.toString().padLeft(2, '0')}';
}
