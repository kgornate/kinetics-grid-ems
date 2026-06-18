import 'command_catalog.dart';

/// UI helper utilities for command panels.
class CommandUiHelpers {
  const CommandUiHelpers._();

  static String labelFor(String command) {
    return CommandCatalog.find(command)?.label ?? command;
  }

  static String confirmationTitle(String command) {
    return 'Confirm ${labelFor(command)}';
  }

  static String confirmationMessage(String command, {Object? value, String? unit}) {
    final label = labelFor(command);
    if (value == null) return 'Are you sure you want to send $command?';
    final unitSuffix = unit == null || unit.isEmpty ? '' : ' $unit';
    return 'Send $command = $value$unitSuffix?';
  }

  static String? validateNumericValue(String command, num value) {
    final definition = CommandCatalog.find(command);
    if (definition == null) return null;
    if (!definition.isValueAllowed(value)) {
      final min = definition.minValue;
      final max = definition.maxValue;
      if (min != null && max != null) return 'Value must be between $min and $max.';
      if (min != null) return 'Value must be >= $min.';
      if (max != null) return 'Value must be <= $max.';
    }
    return null;
  }
}
