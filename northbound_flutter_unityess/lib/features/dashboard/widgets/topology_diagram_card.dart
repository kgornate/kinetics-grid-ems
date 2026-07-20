import 'package:flutter/material.dart';

import '../models/site_dashboard_summary.dart';
import '../models/source_home_summary.dart';

class TopologyDiagramCard extends StatelessWidget {
  const TopologyDiagramCard({
    super.key,
    required this.summary,
  });

  final SiteDashboardSummary summary;

  @override
  Widget build(BuildContext context) {
    final sourceA = summary.sources.isNotEmpty ? summary.sources[0] : null;
    final sourceB = summary.sources.length > 1 ? summary.sources[1] : null;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Site Topology',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
            ),
            const SizedBox(height: 8),
            Text(
              'Combined two-EMS site topology overview using live gateway summary values.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: const Color(0xFF6C7B8A),
                  ),
            ),
            const SizedBox(height: 14),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final size = Size(constraints.maxWidth, constraints.maxHeight);
                  return Stack(
                    children: [
                      CustomPaint(
                        size: size,
                        painter: _TopologyLinesPainter(),
                      ),
                      Positioned(
                        left: size.width * 0.37,
                        top: 12,
                        width: size.width * 0.22,
                        child: _NodeTile(
                          title: 'Grid / Mains',
                          subtitle: 'Site exchange',
                          value: _formatPower(summary.siteActivePowerKw),
                          icon: Icons.power,
                          accent: const Color(0xFF4A76D1),
                        ),
                      ),
                      Positioned(
                        left: size.width * 0.40,
                        top: size.height * 0.28,
                        width: size.width * 0.20,
                        child: _BusTile(
                          soc: summary.overallSoc,
                          assetsOnline: '${summary.onlineAssetCount}/${summary.assetCount}',
                          bessFleetLabel: summary.bessFleetLabel,
                        ),
                      ),
                      Positioned(
                        right: 12,
                        top: size.height * 0.34,
                        width: size.width * 0.22,
                        child: _NodeTile(
                          title: 'User Load',
                          subtitle: 'Site load summary',
                          value: summary.fireAlarmActive ? 'Fire alarm active' : 'Normal operation',
                          icon: Icons.apartment_rounded,
                          accent: summary.fireAlarmActive
                              ? const Color(0xFFC53939)
                              : const Color(0xFF36B37E),
                        ),
                      ),
                      if (sourceA != null)
                        Positioned(
                          left: 12,
                          bottom: 12,
                          width: size.width * 0.30,
                          child: _SourceNodeTile(source: sourceA),
                        ),
                      if (sourceB != null)
                        Positioned(
                          right: 12,
                          bottom: 12,
                          width: size.width * 0.30,
                          child: _SourceNodeTile(source: sourceB),
                        ),
                    ],
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatPower(double? value) {
    if (value == null) return '--';
    final sign = value > 0 ? '+' : '';
    return '$sign${value.toStringAsFixed(1)} kW';
  }
}

class _NodeTile extends StatelessWidget {
  const _NodeTile({
    required this.title,
    required this.subtitle,
    required this.value,
    required this.icon,
    required this.accent,
  });

  final String title;
  final String subtitle;
  final String value;
  final IconData icon;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE6EBF2)),
        boxShadow: const [
          BoxShadow(
            color: Color(0x14000000),
            blurRadius: 12,
            offset: Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircleAvatar(
            radius: 18,
            backgroundColor: accent.withOpacity(0.12),
            child: Icon(icon, color: accent, size: 20),
          ),
          const SizedBox(height: 8),
          Text(
            title,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 2),
          Text(
            subtitle,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: const Color(0xFF6C7B8A),
                ),
          ),
          const SizedBox(height: 8),
          Text(
            value,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                  color: accent,
                ),
          ),
        ],
      ),
    );
  }
}

class _BusTile extends StatelessWidget {
  const _BusTile({
    required this.soc,
    required this.assetsOnline,
    required this.bessFleetLabel,
  });

  final double? soc;
  final String assetsOnline;
  final String bessFleetLabel;

  @override
  Widget build(BuildContext context) {
    return FittedBox(
      fit: BoxFit.scaleDown,
      child: Container(
        width: 126,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: const Color(0xFF4A76D1),
          borderRadius: BorderRadius.circular(18),
          boxShadow: const [
            BoxShadow(
              color: Color(0x224A76D1),
              blurRadius: 14,
              offset: Offset(0, 6),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.hub_rounded, color: Colors.white, size: 22),
            const SizedBox(height: 6),
            const Text(
              'Site Bus',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              soc != null ? '${soc!.toStringAsFixed(1)} % SOC' : '--',
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              '$assetsOnline online',
              style: const TextStyle(
                color: Color(0xFFEAF2FF),
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              'BESS $bessFleetLabel',
              style: const TextStyle(
                color: Color(0xFFEAF2FF),
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SourceNodeTile extends StatelessWidget {
  const _SourceNodeTile({
    required this.source,
  });

  final SourceHomeSummary source;

  @override
  Widget build(BuildContext context) {
    final accent = source.online ? const Color(0xFF36B37E) : const Color(0xFFC53939);

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE6EBF2)),
        boxShadow: const [
          BoxShadow(
            color: Color(0x14000000),
            blurRadius: 12,
            offset: Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircleAvatar(
            radius: 18,
            backgroundColor: accent.withOpacity(0.12),
            child: Icon(Icons.battery_charging_full_rounded, color: accent, size: 20),
          ),
          const SizedBox(height: 8),
          Text(
            source.shortTitle,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 8),
          _metricRow(
            label: 'BESS',
            value: '${source.bessStatusLabel} / ${source.bessModeLabel}',
          ),
          _metricRow(
            label: 'SOC',
            value: source.soc != null ? '${source.soc!.toStringAsFixed(1)} %' : '--',
          ),
          _metricRow(
            label: 'P',
            value: source.activePowerKw != null
                ? '${source.activePowerKw!.toStringAsFixed(1)} kW'
                : '--',
          ),
          _metricRow(
            label: 'Assets',
            value: '${source.onlineAssetCount}/${source.assetCount}',
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
            decoration: BoxDecoration(
              color: source.online ? const Color(0xFFEAF8F1) : const Color(0xFFFFF2F2),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              source.online ? 'ONLINE' : 'OFFLINE',
              style: TextStyle(
                color: source.online ? const Color(0xFF228B5A) : const Color(0xFFC53939),
                fontWeight: FontWeight.w700,
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _metricRow({required String label, required String value}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 5),
      child: Row(
        children: [
          SizedBox(
            width: 42,
            child: Text(
              label,
              style: const TextStyle(
                color: Color(0xFF6C7B8A),
                fontWeight: FontWeight.w600,
                fontSize: 12,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
          ),
        ],
      ),
    );
  }
}

class _TopologyLinesPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final busPaint = Paint()
      ..color = const Color(0xFF65A3FF)
      ..strokeWidth = 5
      ..strokeCap = StrokeCap.round;

    final linePaint = Paint()
      ..color = const Color(0xFF8FD3FF)
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;

    final glowPaint = Paint()
      ..color = const Color(0x2265A3FF)
      ..strokeWidth = 16
      ..strokeCap = StrokeCap.round;

    final grid = Offset(size.width * 0.48, 86);
    final busTop = Offset(size.width * 0.48, size.height * 0.25);
    final busCenter = Offset(size.width * 0.48, size.height * 0.48);
    final leftSource = Offset(size.width * 0.22, size.height * 0.80);
    final rightSource = Offset(size.width * 0.74, size.height * 0.80);
    final load = Offset(size.width * 0.83, size.height * 0.48);

    canvas.drawLine(grid, busTop, glowPaint);
    canvas.drawLine(busTop, busCenter, glowPaint);
    canvas.drawLine(busCenter, leftSource, glowPaint);
    canvas.drawLine(busCenter, rightSource, glowPaint);
    canvas.drawLine(busCenter, load, glowPaint);

    canvas.drawLine(grid, busTop, busPaint);
    canvas.drawLine(busTop, busCenter, busPaint);
    canvas.drawLine(busCenter, leftSource, linePaint);
    canvas.drawLine(busCenter, rightSource, linePaint);
    canvas.drawLine(busCenter, load, linePaint);

    canvas.drawCircle(busCenter, 10, Paint()..color = const Color(0xFF4A76D1));
    canvas.drawCircle(busCenter, 20, Paint()..color = const Color(0x224A76D1));
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
