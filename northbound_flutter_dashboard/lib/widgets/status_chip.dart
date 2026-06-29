import 'package:flutter/material.dart';

class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.label, required this.good});

  final String label;
  final bool good;

  @override
  Widget build(BuildContext context) {
    return Chip(
      avatar: Icon(good ? Icons.check_circle : Icons.warning, size: 18),
      label: Text(label),
    );
  }
}
