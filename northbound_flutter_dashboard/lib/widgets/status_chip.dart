import 'package:flutter/material.dart';

class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.label, required this.good, this.icon});

  final String label;
  final bool good;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Chip(
      avatar: Icon(icon ?? (good ? Icons.check_circle : Icons.warning), size: 18),
      label: Text(label),
    );
  }
}
