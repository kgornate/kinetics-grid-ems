import 'package:flutter/material.dart';

import '../core/presentation/telemetry_presentation.dart';
import '../core/state/gateway_controller.dart';
import '../models/gateway_models.dart';
import '../widgets/common_widgets.dart';
import 'rack_detail_screen.dart';

class RacksScreen extends StatelessWidget {
  const RacksScreen({super.key, required this.controller});

  final GatewayController controller;

  @override
  Widget build(BuildContext context) {
    final racks = controller.plant.racks;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          SectionHeader(
            'Battery racks / BCUs',
            subtitle: '${racks.length} configured rack assets. Open a rack for electrical, thermal, cell-channel, sensor and alarm views.',
            trailing: FilledButton.tonalIcon(
              onPressed: controller.busy ? null : () => controller.forceCompleteExtraction(),
              icon: const Icon(Icons.download_for_offline),
              label: const Text('Extract all BMS data'),
            ),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final count = constraints.maxWidth > 1050 ? 2 : 1;
                return GridView.builder(
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: count,
                    crossAxisSpacing: 12,
                    mainAxisSpacing: 12,
                    childAspectRatio: 2.2,
                  ),
                  itemCount: racks.length,
                  itemBuilder: (context, index) {
                    final rack = racks[index];
                    return RichAssetCard(
                      asset: rack,
                      metrics: _metrics(rack),
                      warningCount: controller.activeAlarms.where((alarm) => alarm['asset_id']?.toString() == rack.assetId).length,
                      onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                        builder: (_) => RackDetailScreen(controller: controller, rack: rack),
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

  List<String> _metrics(AssetSnapshot rack) {
    String shown(String key, String label) {
      final point = rack.telemetry[key];
      return point == null ? '' : '$label ${presentPoint(rack.assetType, key, point).text}';
    }
    return [
      shown('vrack', 'Voltage'),
      shown('irack', 'Current'),
      shown('soc', 'SOC'),
      shown('soh', 'SOH'),
      shown('vcell_min', 'Min cell'),
      shown('vcell_max', 'Max cell'),
      shown('tcell_max', 'Max temp'),
      shown('ir', 'Insulation'),
    ];
  }
}
