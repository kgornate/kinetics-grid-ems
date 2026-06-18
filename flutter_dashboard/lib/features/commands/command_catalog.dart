import 'command_definition.dart';
import 'gateway_command_names.dart';

/// Central catalog of commands supported by the current gateway backend.
class CommandCatalog {
  const CommandCatalog._();

  static const gatewayCommands = <CommandDefinition>[
    CommandDefinition(
      command: GatewayCommandNames.status,
      label: 'Gateway Status',
      assetType: 'gateway',
      category: 'read',
    ),
    CommandDefinition(
      command: GatewayCommandNames.readAllAssets,
      label: 'Read All Assets',
      assetType: 'gateway',
      category: 'read',
    ),
  ];

  static const chillerCommands = <CommandDefinition>[
    CommandDefinition(command: GatewayCommandNames.readChillerAll, label: 'Read Chiller', assetType: 'chiller', category: 'read'),
    CommandDefinition(command: GatewayCommandNames.readChillerSettings, label: 'Read Settings', assetType: 'chiller', category: 'read'),
    CommandDefinition(command: GatewayCommandNames.readChillerMode, label: 'Read Mode', assetType: 'chiller', category: 'read'),
    CommandDefinition(command: GatewayCommandNames.readChillerTemperature, label: 'Read Temp', assetType: 'chiller', category: 'read'),
    CommandDefinition(command: GatewayCommandNames.readChillerOnOff, label: 'Read ON/OFF', assetType: 'chiller', category: 'read'),
    CommandDefinition(
      command: GatewayCommandNames.setChillerTemperature,
      label: 'Set Temperature',
      assetType: 'chiller',
      category: 'write',
      requiresValue: true,
      unit: 'C',
      minValue: -20,
      maxValue: 80,
    ),
    CommandDefinition(
      command: GatewayCommandNames.setChillerMode,
      label: 'Set Mode',
      assetType: 'chiller',
      category: 'write',
      requiresValue: true,
    ),
    CommandDefinition(
      command: GatewayCommandNames.chillerOn,
      label: 'Chiller ON',
      assetType: 'chiller',
      category: 'control',
      requiresConfirmation: true,
    ),
    CommandDefinition(
      command: GatewayCommandNames.chillerOff,
      label: 'Chiller OFF',
      assetType: 'chiller',
      category: 'control',
      requiresConfirmation: true,
    ),
  ];

  static const pcsCommands = <CommandDefinition>[
    CommandDefinition(command: GatewayCommandNames.readPcs, label: 'Read PCS', assetType: 'pcs', category: 'read'),
    CommandDefinition(
      command: GatewayCommandNames.setPcsActivePower,
      label: 'Set Active Power',
      assetType: 'pcs',
      category: 'write',
      requiresValue: true,
      unit: 'kW',
      description: '+ve discharge, -ve charge. Use 0 for safe test.',
      requiresConfirmation: true,
    ),
    CommandDefinition(
      command: GatewayCommandNames.setPcsReactivePower,
      label: 'Set Reactive Power',
      assetType: 'pcs',
      category: 'write',
      requiresValue: true,
      unit: 'kvar',
      description: 'Use 0 for safe test.',
      requiresConfirmation: true,
    ),
    CommandDefinition(
      command: GatewayCommandNames.pcsHeartbeat,
      label: 'Heartbeat',
      assetType: 'pcs',
      category: 'write',
      requiresValue: true,
      minValue: 0,
      maxValue: 255,
    ),
    CommandDefinition(
      command: GatewayCommandNames.pcsPowerOn,
      label: 'PCS Power ON',
      assetType: 'pcs',
      category: 'control',
      requiresConfirmation: true,
    ),
    CommandDefinition(
      command: GatewayCommandNames.pcsPowerOff,
      label: 'PCS Power OFF',
      assetType: 'pcs',
      category: 'control',
      requiresConfirmation: true,
    ),
    CommandDefinition(
      command: GatewayCommandNames.pcsResetFault,
      label: 'PCS Reset Fault',
      assetType: 'pcs',
      category: 'control',
      requiresConfirmation: true,
    ),
  ];

  static const bmsCommands = <CommandDefinition>[
    CommandDefinition(command: GatewayCommandNames.readBmsAll, label: 'Read BMS', assetType: 'bms', category: 'read'),
    CommandDefinition(command: GatewayCommandNames.readBmsAlarms, label: 'Read Alarms', assetType: 'bms', category: 'read'),
    CommandDefinition(command: GatewayCommandNames.bmsFanAuto, label: 'Fan Auto', assetType: 'bms', category: 'control'),
    CommandDefinition(command: GatewayCommandNames.bmsFanOn, label: 'Fan ON', assetType: 'bms', category: 'control'),
    CommandDefinition(command: GatewayCommandNames.bmsFanOff, label: 'Fan OFF', assetType: 'bms', category: 'control'),
  ];

  static const all = <CommandDefinition>[
    ...gatewayCommands,
    ...chillerCommands,
    ...pcsCommands,
    ...bmsCommands,
  ];

  static CommandDefinition? find(String command) {
    final normalized = GatewayCommandNames.normalize(command);
    for (final definition in all) {
      if (definition.command == normalized) return definition;
    }
    return null;
  }

  static List<CommandDefinition> forAssetType(String assetType) {
    final normalized = assetType.trim().toLowerCase();
    return all.where((definition) => definition.assetType == normalized).toList(growable: false);
  }
}
