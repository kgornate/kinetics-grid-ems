import 'package:flutter/material.dart';

import '../core/presentation/telemetry_presentation.dart';
import '../core/state/gateway_controller.dart';
import '../widgets/common_widgets.dart';
import 'environment_asset_screen.dart';

class EnvironmentScreen extends StatelessWidget {
  const EnvironmentScreen({super.key, required this.controller});

  final GatewayController controller;

  @override
  Widget build(BuildContext context) {
    final assets = controller.plant.environment;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          SectionHeader(
            'Environment and auxiliary assets',
            subtitle: 'HVAC, liquid cooling, energy meter, dehumidifiers, fire/safety I/O and other BMS-exposed points.',
          ),
          const SizedBox(height: 16),
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final count = constraints.maxWidth > 1000 ? 3 : constraints.maxWidth > 650 ? 2 : 1;
                return GridView.builder(
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: count,
                    crossAxisSpacing: 12,
                    mainAxisSpacing: 12,
                    childAspectRatio: 1.9,
                  ),
                  itemCount: assets.length,
                  itemBuilder: (context, index) {
                    final asset = assets[index];
                    return RichAssetCard(
                      asset: asset,
                      metrics: environmentSummary(asset),
                      warningCount: controller.activeAlarms.where((alarm) => alarm['asset_id']?.toString() == asset.assetId).length,
                      onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                        builder: (_) => EnvironmentAssetScreen(asset: asset),
                      )),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
