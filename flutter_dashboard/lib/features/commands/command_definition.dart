/// UI and repository metadata for a gateway command.
class CommandDefinition {
  final String command;
  final String label;
  final String assetType;
  final String category;
  final bool requiresValue;
  final String? unit;
  final String? description;
  final bool requiresConfirmation;
  final double? minValue;
  final double? maxValue;

  const CommandDefinition({
    required this.command,
    required this.label,
    required this.assetType,
    required this.category,
    this.requiresValue = false,
    this.unit,
    this.description,
    this.requiresConfirmation = false,
    this.minValue,
    this.maxValue,
  });

  bool isValueAllowed(num value) {
    if (minValue != null && value < minValue!) return false;
    if (maxValue != null && value > maxValue!) return false;
    return true;
  }
}
