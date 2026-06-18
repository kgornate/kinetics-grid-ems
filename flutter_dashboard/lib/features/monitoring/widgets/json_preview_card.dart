import 'dart:convert';

import 'package:flutter/material.dart';

class JsonPreviewCard extends StatelessWidget {
  final String title;
  final Map<String, dynamic> data;
  final bool initiallyExpanded;

  const JsonPreviewCard({
    super.key,
    required this.title,
    required this.data,
    this.initiallyExpanded = false,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 1,
      child: ExpansionTile(
        initiallyExpanded: initiallyExpanded,
        title: Text(title),
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            color: Colors.black87,
            child: Text(
              const JsonEncoder.withIndent('  ').convert(data),
              style: const TextStyle(color: Colors.white, fontFamily: 'Consolas', fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }
}
