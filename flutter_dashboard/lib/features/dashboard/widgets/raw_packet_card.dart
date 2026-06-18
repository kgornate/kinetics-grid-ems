import 'dart:convert';

import 'package:flutter/material.dart';

class RawPacketCard extends StatelessWidget {
  const RawPacketCard({
    super.key,
    required this.statusMessage,
    required this.rawPacket,
  });

  final String statusMessage;
  final Map<String, dynamic>? rawPacket;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 1,
      child: ExpansionTile(
        title: const Text('Latest Raw UDP Packet'),
        subtitle: Text(statusMessage),
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            color: Colors.black87,
            child: Text(
              rawPacket == null
                  ? 'No UDP packet received yet'
                  : const JsonEncoder.withIndent('  ').convert(rawPacket),
              style: const TextStyle(
                color: Colors.white,
                fontFamily: 'Consolas',
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
