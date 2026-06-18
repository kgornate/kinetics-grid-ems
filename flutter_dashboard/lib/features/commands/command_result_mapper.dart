import '../../models/gateway_response.dart';
import 'gateway_command_names.dart';

/// Maps raw gateway command responses into UI-friendly command categories.
class CommandResultMapper {
  const CommandResultMapper._();

  static String assetTypeForCommand(String command) {
    if (GatewayCommandNames.isPcsCommand(command)) return 'pcs';
    if (GatewayCommandNames.isBmsCommand(command)) return 'bms';
    if (GatewayCommandNames.isChillerCommand(command)) return 'chiller';
    if (GatewayCommandNames.isGatewayReadCommand(command) ||
        GatewayCommandNames.normalize(command) == GatewayCommandNames.status) {
      return 'gateway';
    }
    return 'unknown';
  }

  static bool shouldRefreshTelemetry(String command, GatewayResponse response) {
    if (!response.isOk) return false;
    return GatewayCommandNames.isChillerReadCommand(command) ||
        GatewayCommandNames.isPcsReadCommand(command) ||
        GatewayCommandNames.isBmsReadCommand(command) ||
        GatewayCommandNames.isGatewayReadCommand(command);
  }

  static String successMessage(String command) {
    final normalized = GatewayCommandNames.normalize(command);
    final assetType = assetTypeForCommand(normalized);
    if (assetType == 'pcs') return 'PCS command $normalized completed';
    if (assetType == 'bms') return 'BMS command $normalized completed';
    if (assetType == 'chiller') return 'Chiller command $normalized completed';
    if (assetType == 'gateway') return 'Gateway command $normalized completed';
    return 'Command $normalized completed';
  }
}
