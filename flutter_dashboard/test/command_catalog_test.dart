import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_dashboard/features/commands/commands.dart';

void main() {
  group('CommandCatalog', () {
    test('finds known command definitions', () {
      final pcs = CommandCatalog.find(GatewayCommandNames.setPcsActivePower);
      expect(pcs, isNotNull);
      expect(pcs!.assetType, 'pcs');
      expect(pcs.requiresValue, isTrue);
      expect(pcs.unit, 'kW');

      final bms = CommandCatalog.find(GatewayCommandNames.readBmsAll);
      expect(bms, isNotNull);
      expect(bms!.assetType, 'bms');

      final chiller = CommandCatalog.find(GatewayCommandNames.setChillerTemperature);
      expect(chiller, isNotNull);
      expect(chiller!.assetType, 'chiller');
    });

    test('groups commands by asset type', () {
      expect(CommandCatalog.forAssetType('pcs'), isNotEmpty);
      expect(CommandCatalog.forAssetType('bms'), isNotEmpty);
      expect(CommandCatalog.forAssetType('chiller'), isNotEmpty);
    });
  });

  group('GatewayCommandNames', () {
    test('classifies command families', () {
      expect(GatewayCommandNames.isPcsCommand(GatewayCommandNames.setPcsActivePower), isTrue);
      expect(GatewayCommandNames.isBmsCommand(GatewayCommandNames.startBmsPrecharge), isTrue);
      expect(GatewayCommandNames.isChillerCommand(GatewayCommandNames.setChillerMode), isTrue);
      expect(GatewayCommandNames.isGatewayReadCommand(GatewayCommandNames.readAllAssets), isTrue);
    });
  });

  group('CommandUiHelpers', () {
    test('validates configured numeric ranges', () {
      expect(CommandUiHelpers.validateNumericValue(GatewayCommandNames.pcsHeartbeat, 10), isNull);
      expect(CommandUiHelpers.validateNumericValue(GatewayCommandNames.pcsHeartbeat, 300), isNotNull);
      expect(CommandUiHelpers.labelFor(GatewayCommandNames.pcsPowerOn), 'PCS Power ON');
    });
  });
}
