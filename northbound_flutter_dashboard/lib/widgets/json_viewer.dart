import 'dart:convert';

import 'package:flutter/material.dart';

class JsonViewer extends StatelessWidget {
  const JsonViewer({super.key, required this.data});

  final dynamic data;

  @override
  Widget build(BuildContext context) {
    const encoder = JsonEncoder.withIndent('  ');
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SelectableText(
        encoder.convert(data),
        style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
      ),
    );
  }
}
