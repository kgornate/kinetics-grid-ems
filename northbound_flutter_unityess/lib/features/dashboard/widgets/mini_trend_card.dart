import 'dart:math' as math;

import 'package:flutter/material.dart';

class TrendPoint {
  const TrendPoint({
    required this.timestamp,
    required this.value,
  });

  final DateTime timestamp;
  final double value;
}

class MiniTrendCard extends StatelessWidget {
  const MiniTrendCard({
    super.key,
    required this.title,
    required this.points,
    this.unit,
    this.lineColor = const Color(0xFF4B74D6),
    this.subtitle,
    this.valueFormatter,
    this.minY,
    this.maxY,
  });

  final String title;
  final List<TrendPoint> points;
  final String? unit;
  final Color lineColor;
  final String? subtitle;
  final String Function(double value)? valueFormatter;
  final double? minY;
  final double? maxY;

  @override
  Widget build(BuildContext context) {
    final latest = points.isNotEmpty ? points.last.value : null;

    String _formatLatest() {
      if (latest == null) return '--';
      if (valueFormatter != null) return valueFormatter!(latest!);
      if (unit != null && unit!.trim().isNotEmpty) {
        return '${latest!.toStringAsFixed(1)} $unit';
      }
      return latest!.toStringAsFixed(1);
    }

    return Card(
      child: SizedBox(
        height: 220,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      title,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                    ),
                  ),
                  Text(
                    _formatLatest(),
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w800,
                          color: lineColor,
                        ),
                  ),
                ],
              ),
              if (subtitle != null) ...[
                const SizedBox(height: 6),
                Text(
                  subtitle!,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: const Color(0xFF6C7B8A),
                      ),
                ),
              ],
              const SizedBox(height: 14),
              Expanded(
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFFF8FAFD),
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(color: const Color(0xFFE6EBF2)),
                  ),
                  child: points.isEmpty
                      ? const Center(
                          child: Text(
                            'Waiting for live samples',
                            style: TextStyle(
                              color: Color(0xFF6C7B8A),
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        )
                      : CustomPaint(
                          painter: _MiniTrendPainter(
                            points: points,
                            lineColor: lineColor,
                            minY: minY,
                            maxY: maxY,
                          ),
                          child: const SizedBox.expand(),
                        ),
                ),
              ),
              const SizedBox(height: 10),
              Text(
                points.length == 1
                    ? 'Live trend started'
                    : 'Last ${points.length} live samples',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: const Color(0xFF6C7B8A),
                    ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MiniTrendPainter extends CustomPainter {
  const _MiniTrendPainter({
    required this.points,
    required this.lineColor,
    this.minY,
    this.maxY,
  });

  final List<TrendPoint> points;
  final Color lineColor;
  final double? minY;
  final double? maxY;

  @override
  void paint(Canvas canvas, Size size) {
    const padding = 16.0;
    final chartRect = Rect.fromLTWH(
      padding,
      padding,
      math.max(0, size.width - padding * 2),
      math.max(0, size.height - padding * 2),
    );

    final gridPaint = Paint()
      ..color = const Color(0xFFE8EDF5)
      ..strokeWidth = 1;

    for (int i = 0; i < 4; i++) {
      final y = chartRect.top + (chartRect.height / 3) * i;
      canvas.drawLine(
        Offset(chartRect.left, y),
        Offset(chartRect.right, y),
        gridPaint,
      );
    }

    if (points.isEmpty) return;

    final values = points.map((e) => e.value).toList();
    double localMinValue = minY ?? values.reduce(math.min);
    double localMaxValue = maxY ?? values.reduce(math.max);

    if ((localMaxValue - localMinValue).abs() < 0.001) {
      localMaxValue += 1;
      localMinValue -= 1;
    }

    final path = Path();
    final strokePaint = Paint()
      ..color = lineColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    final fillPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          lineColor.withOpacity(0.18),
          lineColor.withOpacity(0.02),
        ],
      ).createShader(chartRect);

    Offset pointAt(int index) {
      final x = points.length == 1
          ? chartRect.center.dx
          : chartRect.left + (chartRect.width * index / (points.length - 1));
      final normalized =
          (points[index].value - localMinValue) / (localMaxValue - localMinValue);
      final y = chartRect.bottom - normalized * chartRect.height;
      return Offset(x, y);
    }

    final first = pointAt(0);
    path.moveTo(first.dx, first.dy);
    for (int i = 1; i < points.length; i++) {
      final p = pointAt(i);
      path.lineTo(p.dx, p.dy);
    }

    final fillPath = Path.from(path)
      ..lineTo(chartRect.right, chartRect.bottom)
      ..lineTo(chartRect.left, chartRect.bottom)
      ..close();

    canvas.drawPath(fillPath, fillPaint);
    canvas.drawPath(path, strokePaint);

    final lastPoint = pointAt(points.length - 1);
    canvas.drawCircle(lastPoint, 4, Paint()..color = lineColor);
    canvas.drawCircle(
      lastPoint,
      8,
      Paint()..color = lineColor.withOpacity(0.15),
    );
  }

  @override
  bool shouldRepaint(covariant _MiniTrendPainter oldDelegate) {
    return oldDelegate.points != points ||
        oldDelegate.lineColor != lineColor ||
        oldDelegate.minY != minY ||
        oldDelegate.maxY != maxY;
  }
}
