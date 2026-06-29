import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

class TelemetryWsClient {
  TelemetryWsClient({required this.wsUrl});

  final String wsUrl;
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;

  final StreamController<Map<String, dynamic>> _controller = StreamController.broadcast();
  Stream<Map<String, dynamic>> get stream => _controller.stream;

  void connect() {
    disconnect();
    try {
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));
      _subscription = _channel!.stream.listen(
        (message) {
          try {
            final decoded = jsonDecode(message.toString());
            if (decoded is Map) {
              _controller.add(Map<String, dynamic>.from(decoded));
            }
          } catch (e) {
            _controller.addError(e);
          }
        },
        onError: _controller.addError,
        onDone: () {},
        cancelOnError: false,
      );
    } catch (e) {
      _controller.addError(e);
    }
  }

  void disconnect() {
    _subscription?.cancel();
    _subscription = null;
    _channel?.sink.close();
    _channel = null;
  }

  void dispose() {
    disconnect();
    _controller.close();
  }
}
