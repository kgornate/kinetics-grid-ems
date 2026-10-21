// Pure Dart checks: no Flutter tool, external network or physical gateway needed.
import 'dart:convert';
import 'dart:io';
import '../lib/models/gateway_models.dart';
import '../lib/core/api/gateway_api_client.dart';

void check(bool value, String message) {
  if (!value) throw StateError(message);
  stdout.writeln('PASS: $message');
}

Map<String, dynamic> fixture(String name) =>
    jsonDecode(File('test/fixtures/$name.json').readAsStringSync())
        as Map<String, dynamic>;

Future<void> main() async {
  check(
    GatewayApiClient().baseUrl == 'http://192.168.10.2:8000',
    'Default URL connects directly over wired Ethernet',
  );
  final plant = PlantSnapshot();
  plant.applyMessage(fixture('compact'));
  check(
    plant.racks.length == 4 && plant.pcsDevices.length == 4,
    'Actual backend fixture exposes four racks and four PCS',
  );
  check(
    plant.bank?.point('system_soc')?.value is num,
    'Lineage system signals retain their canonical names',
  );
  check(
    plant.assets['acrel_meter_1']?.assetType == 'energy_meter',
    'Meter collection is ingested from compact snapshot',
  );
  check(
    !plant.environment.any((asset) => asset.assetId == 'acrel_meter_1'),
    'Meter is excluded from auxiliary assets',
  );
  final normalized = fixture('normalized');
  check(
    (normalized['pairs'] as Map).length == 4,
    'Four normalized pair records available for the summary screen',
  );
  check(
    (normalized['battery_system'] as Map)['soc_percent'] is num,
    'Summary uses normalized engineering values',
  );
  final capabilities = ControlSequenceCapabilities.fromJson(
    fixture('control_capabilities'),
  );
  check(
    capabilities.pairs.length == 4,
    'Vendor-neutral capabilities expose all four control pairs',
  );
  check(
    !capabilities.enabled && !capabilities.fullAutomaticAllowed,
    'Archived disabled commissioning gates remain disabled',
  );
  final all = fixture('control_all_compact');
  for (final entry in (all['pairs'] as Map).entries) {
    final status = ControlSequenceStatus.fromJson(
      Map<String, dynamic>.from(entry.value as Map),
    );
    check(
      status.pairId == entry.key,
      'Compact status identity preserved for ${entry.key}',
    );
    check(
      !status.controlEnabled,
      'Compact status without write gates cannot enable commands',
    );
  }
  final selected = ControlSequenceStatus.fromJson(fixture('control_pair'));
  check(
    !selected.controlEnabled,
    'Full Kalpa status respects disabled hardware write gates',
  );
  plant.applyMessage({
    'type': 'telemetry_update',
    'sequence': 999999,
    'assets': [
      {
        'asset_id': 'acrel_meter_1',
        'asset_type': 'energy_meter',
        'online': false,
        'telemetry': {
          'frequency_hz': {'v': null, 'q': 'bad', 'u': 'Hz'},
        },
      },
    ],
  });
  check(
    plant.assets['acrel_meter_1']?.online == false &&
        plant.assets['acrel_meter_1']?.point('frequency_hz')?.quality == 'bad',
    'Offline meter delta is retained without converting missing values to zero',
  );
  plant.applyMessage({...fixture('compact'), 'meters': <String, dynamic>{}});
  check(
    !plant.assets.containsKey('acrel_meter_1'),
    'Removed/disabled meter is cleared by authoritative snapshot',
  );

  for (final invalid in [
    'file:///tmp/example',
    'http://name:password@localhost',
    'https://host/?token=example',
  ]) {
    var rejected = false;
    try {
      GatewayApiClient(baseUrl: invalid);
    } on ApiException {
      rejected = true;
    }
    check(rejected, 'Invalid or credential-bearing base URL rejected');
  }
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  final requests = <String>[];
  final handler = server.listen((request) async {
    requests.add('${request.method} ${request.uri.path}');
    final path = request.uri.path.replaceFirst('/gateway', '');
    if (path == '/api/auth/login') {
      final credentials =
          jsonDecode(await utf8.decoder.bind(request).join()) as Map;
      request.response.headers.contentType = ContentType.json;
      request.response.write(
        jsonEncode({
          'access_token': 'fixture-only',
          'role': 'customer',
          'username': credentials['username'],
        }),
      );
    } else if (path == '/ws/telemetry') {
      if (request.uri.queryParameters['token'] != 'fixture-only')
        throw StateError('Missing WS token');
      final socket = await WebSocketTransformer.upgrade(request);
      socket.add(jsonEncode(fixture('compact')));
      await socket.close();
      return;
    } else if (request.headers.value('Authorization') !=
        'Bearer fixture-only') {
      request.response.statusCode = 401;
      request.response.write('{"detail":"Unauthorized"}');
    } else if (path == '/api/meters') {
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode({'meters': fixture('meter')}));
    } else {
      request.response.statusCode = 530;
      request.response.write('Cloud route unavailable');
    }
    await request.response.close();
  });
  final api = GatewayApiClient(
    baseUrl: 'http://127.0.0.1:${server.port}/gateway',
  );
  try {
    final login = await api.login(
      username: 'customer',
      password: 'fixture-only',
    );
    api.token = login['access_token'] as String;
    final meters = await api.getJson('/api/meters');
    check(
      (meters['meters'] as Map).containsKey('acrel_meter_1'),
      'Authenticated REST meter transport with API path prefix',
    );
    final socket = await api.openTelemetrySocket();
    final message = jsonDecode((await socket.first).toString()) as Map;
    check(
      message['type'] == 'snapshot',
      'Authenticated WebSocket snapshot transport',
    );
    await socket.close();
    var failed = false;
    try {
      await api.getJson('/missing');
    } on ApiException catch (error) {
      failed = error.statusCode == 530;
    }
    check(failed, 'Cloud/HTTP errors remain explicit API failures');
    check(
      requests.every(
        (r) => r.startsWith('GET') || r == 'POST /gateway/api/auth/login',
      ),
      'Monitoring contract check issues no field-control writes',
    );
  } finally {
    api.close();
    await handler.cancel();
    await server.close(force: true);
  }
}
