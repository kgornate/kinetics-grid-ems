class PcsFaultItem {
  const PcsFaultItem({
    required this.signalName,
    required this.displayName,
    required this.category,
    required this.stateLabel,
    required this.active,
    this.quality,
    this.rawValue,
  });

  final String signalName;
  final String displayName;
  final String category; // fault or alarm
  final String stateLabel;
  final bool active;
  final String? quality;
  final double? rawValue;
}
