import 'package:flutter/material.dart';

class MetricCard extends StatelessWidget {
  const MetricCard({
    super.key,
    required this.title,
    required this.value,
    this.subtitle,
    this.icon,
    this.good,
  });

  final String title;
  final String value;
  final String? subtitle;
  final IconData? icon;
  final bool? good;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final color = good == null
        ? colorScheme.primary
        : good == true
            ? Colors.green
            : Colors.orange;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            CircleAvatar(
              backgroundColor: color.withOpacity(0.14),
              foregroundColor: color,
              child: Icon(icon ?? Icons.analytics_outlined),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: Theme.of(context).textTheme.labelMedium),
                  const SizedBox(height: 4),
                  Text(value, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    Text(subtitle!, style: Theme.of(context).textTheme.bodySmall, overflow: TextOverflow.ellipsis),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
