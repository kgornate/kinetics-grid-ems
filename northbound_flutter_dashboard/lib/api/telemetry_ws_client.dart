import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

class WsStatusSnapshot {
  const WsStatusSnapshot({
    required this.state,
    required this.url,
    this.lastError,
    this.retryCount = 0,
    this.nextRetryInSec,
  });

  final String state;
  final String url;
  final String? lastError;
  final int retryCount;
  final int? nextRetryInSec;

  bool get connected => state == 'connected';
  bool get connecting => state == 'connecting' || state == 'reconnecting';
  bool get hasError => state == 'error';
}

class TelemetryWsClient {
  TelemetryWsClient({required this.wsUrl, this.authToken});

  final String wsUrl;
  final String? authToken;
  WebSocketChannel? _channel;
  StreamSubscription? _socketSubscription;
  Timer? _reconnectTimer;
  bool _disposed = false;
  bool _manualDisconnect = false;
  int _retryCount = 0;

  final StreamController<Map<String, dynamic>> _messageController = StreamController.broadcast();
  final StreamController<WsStatusSnapshot> _statusController = StreamController.broadcast();

  Stream<Map<String, dynamic>> get stream => _messageController.stream;
  Stream<WsStatusSnapshot> get statusStream => _statusController.stream;

  void connect({bool resetRetry = true}) {
    if (_disposed) return;
    _manualDisconnect = false;
    if (resetRetry) _retryCount = 0;
    _reconnectTimer?.cancel();
    _closeSocketOnly();

    _emitStatus('connecting');

    try {
      _channel = WebSocketChannel.connect(_effectiveUri());
      _emitStatus('connected');
      _socketSubscription = _channel!.stream.listen(
        _handleMessage,
        onError: (error) {
          _emitStatus('error', lastError: error.toString());
          _scheduleReconnect();
        },
        onDone: () {
          if (_manualDisconnect || _disposed) {
            _emitStatus('disconnected');
          } else {
            _emitStatus('disconnected', lastError: 'WebSocket closed by peer');
            _scheduleReconnect();
          }
        },
        cancelOnError: false,
      );
    } catch (error) {
      _emitStatus('error', lastError: error.toString());
      _scheduleReconnect();
    }
  }

  void reconnect() {
    connect(resetRetry: true);
  }

  void disconnect() {
    _manualDisconnect = true;
    _reconnectTimer?.cancel();
    _closeSocketOnly();
    _emitStatus('disconnected');
  }

  void dispose() {
    _disposed = true;
    _manualDisconnect = true;
    _reconnectTimer?.cancel();
    _closeSocketOnly();
    _messageController.close();
    _statusController.close();
  }

  void _handleMessage(dynamic message) {
    try {
      final decoded = jsonDecode(message.toString());
      if (decoded is Map && !_messageController.isClosed) {
        _messageController.add(Map<String, dynamic>.from(decoded));
      }
      _retryCount = 0;
      _emitStatus('connected');
    } catch (error) {
      _emitStatus('error', lastError: 'Failed to decode WebSocket frame: $error');
    }
  }

  void _scheduleReconnect() {
    if (_disposed || _manualDisconnect) return;
    _reconnectTimer?.cancel();
    _retryCount += 1;
    final delaySec = _retryCount < 6 ? _retryCount + 1 : 10;
    _emitStatus('reconnecting', nextRetryInSec: delaySec);
    _reconnectTimer = Timer(Duration(seconds: delaySec), () {
      if (!_disposed && !_manualDisconnect) {
        connect(resetRetry: false);
      }
    });
  }

  void _closeSocketOnly() {
    _socketSubscription?.cancel();
    _socketSubscription = null;
    try {
      _channel?.sink.close();
    } catch (_) {}
    _channel = null;
  }

  Uri _effectiveUri() {
    final uri = Uri.parse(wsUrl);
    final token = authToken?.trim();
    if (token == null || token.isEmpty) return uri;
    return uri.replace(queryParameters: {...uri.queryParameters, 'token': token});
  }

  void _emitStatus(String state, {String? lastError, int? nextRetryInSec}) {
    if (_statusController.isClosed) return;
    _statusController.add(
      WsStatusSnapshot(
        state: state,
        url: _effectiveUri().toString(),
        lastError: lastError,
        retryCount: _retryCount,
        nextRetryInSec: nextRetryInSec,
      ),
    );
  }
}
