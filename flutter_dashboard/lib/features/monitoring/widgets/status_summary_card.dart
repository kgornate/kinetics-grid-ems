import 'package:flutter/material.dart';

import '../../assets/widgets/asset_status_helpers.dart';

class StatusSummaryCard extends StatelessWidget {
  final String title;
  final String status;
  final IconData icon;
  final String? subtitle;
  final String? actionText;
  final VoidCallback? onTap;
  final List<Widget> children;

  const StatusSummaryCard({
    super.key,
    required this.title,
    required this.status,
    required this.icon,
    this.subtitle,
    this.actionText,
    this.onTap,
    this.children = const [],
  });

  @override
  Widget build(BuildContext context) {
    final color = AssetStatusHelpers.statusColor(status);
    return Card(
      elevation: 1,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(icon, color: color),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                        if (subtitle != null && subtitle!.isNotEmpty)
                          Text(subtitle!, style: Theme.of(context).textTheme.bodySmall),
                      ],
                    ),
                  ),
                  Chip(
                    visualDensity: VisualDensity.compact,
                    avatar: Icon(Icons.circle, size: 10, color: color),
                    label: Text(AssetStatusHelpers.titleCase(status)),
                  ),
                ],
              ),
              if (children.isNotEmpty) ...[
                const SizedBox(height: 12),
                ...children,
              ],
              if (actionText != null && onTap != null) ...[
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerRight,
                  child: Text(actionText!, style: TextStyle(color: Theme.of(context).colorScheme.primary)),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
