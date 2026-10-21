import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';

void main() => runApp(const SetupApp());

class SetupApp extends StatelessWidget {
  const SetupApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'Kalpa Gateway Setup',
    theme: ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff087f75)),
      scaffoldBackgroundColor: const Color(0xfff2f5f7),
      inputDecorationTheme: const InputDecorationTheme(border: OutlineInputBorder()),
    ),
    home: const SetupPage(),
  );
}

class SetupPage extends StatefulWidget {
  const SetupPage({super.key});
  @override
  State<SetupPage> createState() => _SetupPageState();
}

class _SetupPageState extends State<SetupPage> {
  final host = TextEditingController(text: '192.168.10.2');
  final token = TextEditingController();
  final password = TextEditingController();
  final manualSsid = TextEditingController();
  final publicUrl = TextEditingController(text: 'https://gw3-api.unityess.cloud/hmi/');
  final sshHostname = TextEditingController();
  String sshResult = 'Not checked - enter the actual public SSH hostname to test WebSocket transport';
  Map<String, dynamic>? connectivity;
  String publicResult = 'Not checked';
  DateTime? publicCheckedAt;
  List<Map<String, dynamic>> networks = [];
  Map<String, dynamic>? wifi;
  Map<String, dynamic>? operation;
  Map<String, dynamic>? selected;
  String message = 'Connect your laptop to the gateway PC Ethernet port to begin.';
  bool busy = false;
  bool hidePassword = true;

  Future<Map<String, dynamic>> api(String path, [Map<String, dynamic>? data]) async {
    final address = InternetAddress.tryParse(host.text.trim());
    if (address == null || address.type != InternetAddressType.IPv4) {
      throw Exception('Enter the gateway Ethernet IPv4 address.');
    }
    if (token.text.trim().length < 32) throw Exception('Enter this gateway’s setup token.');
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 5);
    // Direct cable connection: never route credentials through an HTTP proxy.
    client.findProxy = (_) => 'DIRECT';
    try {
      final request = await client.openUrl(data == null ? 'GET' : 'POST',
        Uri(scheme: 'http', host: address.address, port: 8765, path: path));
      request.followRedirects = false;
      request.headers.set('Authorization', 'Bearer ${token.text.trim()}');
      if (data != null) {
        request.headers.contentType = ContentType.json;
        final payload = utf8.encode(jsonEncode(data));
        request.contentLength = payload.length;
        request.add(payload);
      }
      final response = await request.close().timeout(const Duration(seconds: 30));
      final text = await utf8.decoder.bind(response).join().timeout(const Duration(seconds: 30));
      final value = jsonDecode(text) as Map<String, dynamic>;
      if (response.statusCode != 200) throw Exception(value['error'] ?? 'Request failed');
      return value;
    } finally {
      client.close(force: true);
    }
  }

  Future<void> refresh() async {
    final result = await api('/v1/status');
    if (!mounted) return;
    setState(() {
      wifi = Map<String, dynamic>.from(result['wifi'] as Map);
      operation = result['operation'] == null ? null : Map<String, dynamic>.from(result['operation'] as Map);
    });
  }

  Future<void> perform(Future<void> Function() task) async {
    setState(() => busy = true);
    try { await task(); }
    catch (error) {
      if (mounted) setState(() => message = error.toString().replaceFirst('Exception: ', ''));
    }
    finally { if (mounted) setState(() => busy = false); }
  }

  Future<void> verifySshWebSocket() async {
    final name = sshHostname.text.trim();
    if (name.isEmpty) {
      if (mounted) setState(() => sshResult = 'Not checked - enter the actual public SSH hostname, not a local alias.');
      return;
    }
    if (!RegExp(r'^[a-zA-Z0-9.-]+$').hasMatch(name) || !name.contains('.')) {
      if (mounted) setState(() => sshResult = 'Enter a hostname only, without https:// or a path.');
      return;
    }
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 5);
    client.findProxy = (_) => 'DIRECT';
    WebSocket? ws;
    try {
      ws = await WebSocket.connect('wss://$name/', customClient: client)
          .timeout(const Duration(seconds: 9));
      final frame = await ws.first.timeout(const Duration(seconds: 5));
      final banner = frame is String ? frame : utf8.decode(frame as List<int>, allowMalformed: true);
      if (mounted) setState(() => sshResult = banner.startsWith('SSH-')
        ? 'PASS - WebSocket upgrade and SSH server banner received. User SSH login is not tested.'
        : 'WebSocket upgraded, but an SSH banner was not verified.');
    } catch (error) {
      if (mounted) setState(() => sshResult = 'NOT VERIFIED - $error. Check the SSH hostname, Cloudflare Access and tunnel ingress. No Access login credentials are sent by this probe.');
    } finally {
      if (ws != null) { unawaited(ws.close()); }
      client.close(force: true);
    }
  }

  Future<void> verifyConnectivity() async {
    final result = await api('/v1/connectivity');
    if (!mounted) return;
    setState(() {
      connectivity = result;
      publicResult = 'Checking from this laptop...';
    });
    final uri = Uri.tryParse(publicUrl.text.trim());
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty || uri.userInfo.isNotEmpty) {
      setState(() => publicResult = 'Enter a valid HTTPS public HMI URL without credentials.');
      return;
    }
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 5);
    client.findProxy = (_) => 'DIRECT';
    try {
      final request = await client.getUrl(uri).timeout(const Duration(seconds: 7));
      request.followRedirects = false;
      request.headers.set('Cache-Control', 'no-cache');
      final response = await request.close().timeout(const Duration(seconds: 8));
      final code = response.statusCode;
      // Read only headers; do not download or retain the HMI or any login content.
      String label;
      if (code >= 200 && code < 300) {
        label = 'HTTP $code from public URL. Application identity/login not verified.';
      } else if (code >= 300 && code < 400 || code == 401 || code == 403) {
        label = 'HTTP $code: redirect or access restriction. Tunnel-to-origin path is not verified.';
      } else {
        label = 'HTTP $code: public route failed. Check tunnel, Access and origin routing.';
      }
      if (mounted) setState(() { publicResult = label; publicCheckedAt = DateTime.now(); });
    } catch (error) {
      if (mounted) setState(() { publicResult = 'Public HTTPS request failed: $error'; publicCheckedAt = DateTime.now(); });
    } finally {
      client.close(force: true);
    }
    await verifySshWebSocket();
    if (mounted) setState(() => message = 'Connectivity checks finished. Read each result below; user SSH login is not tested.');
  }

  Widget checkRow(String label, String key) {
    final checks = connectivity?['checks'] as Map?;
    final value = checks?[key] as Map?;
    if (value == null) return fact(label, 'Not checked');
    return fact(label, '${value['state'].toString().toUpperCase()} - ${value['detail']}');
  }

  Future<void> scan() async {
    final result = await api('/v1/wifi/scan');
    if (!mounted) return;
    setState(() {
      networks = (result['networks'] as List).map((e) => Map<String, dynamic>.from(e as Map)).toList();
      selected = null;
      message = 'Select a WPA/WPA2 Personal network. SSID spaces are preserved.';
    });
  }

  Future<void> apply() async {
    final ssidHex = selected?['ssid_hex'] ?? utf8.encode(manualSsid.text).map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    if (ssidHex.isEmpty) throw Exception('Choose a network or enter an exact SSID.');
    final bytes = utf8.encode(password.text).length;
    if (bytes < 8 || bytes > 63) throw Exception('Password must be 8–63 bytes.');
    final accepted = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Change gateway Wi-Fi?'),
      content: const Text('The previous Wi-Fi configuration will be restored unless this app confirms the new connection within 90 seconds. Keep the Ethernet cable connected and this app open.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Apply Wi-Fi'))],
    ));
    if (accepted != true) return;
    final result = await api('/v1/wifi/apply', {'ssid_hex': ssidHex, 'password': password.text});
    password.clear();
    final op = result['operation'] as Map;
    final deadline = DateTime.now().add(const Duration(seconds: 100));
    String lastError = '';
    while (mounted && DateTime.now().isBefore(deadline)) {
      setState(() => message = 'Reconnecting Wi-Fi… checking association and IP address.');
      await Future<void>.delayed(const Duration(seconds: 2));
      try {
        await refresh();
        if (operation?['id'] != op['id']) throw Exception('Operation changed. Refresh gateway status.');
        final state = operation?['state'];
        if (state == 'rolled_back' || state == 'rollback_failed') {
          throw StateError(state == 'rolled_back' ? 'Connection was not confirmed. Previous Wi-Fi configuration restored.' : 'Rollback failed. Check the gateway over wired Ethernet.');
        }
        if (state == 'confirmed') {
          setState(() => message = 'Wi-Fi configuration saved. Use Verify internet and Cloudflare for fresh results.');
          return;
        }
        if (state == 'awaiting_confirmation' && wifi?['connected'] == true &&
            wifi?['ssid_hex'] == ssidHex && (wifi?['ipv4'] as List).isNotEmpty) {
          await api('/v1/wifi/confirm', {'operation_id': op['id']});
          await refresh();
          if (!mounted) return;
          setState(() => connectivity = null);
          await verifyConnectivity();
          if (!mounted) return;
          setState(() => message = 'Wi-Fi saved. Internet and Cloudflare check results are shown above.');
          return;
        }
      } on StateError { rethrow; }
      catch (error) { lastError = error.toString(); }
    }
    throw Exception('Verification timed out. Refresh status to check rollback. $lastError');
  }

  Widget panel(String title, Widget child) => Card(
    margin: const EdgeInsets.only(bottom: 20),
    child: Padding(padding: const EdgeInsets.all(24), child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [Text(title, style: Theme.of(context).textTheme.titleLarge), const SizedBox(height: 18), child],
    )),
  );

  Widget fact(String label, String value) => Padding(padding: const EdgeInsets.symmetric(vertical: 7),
    child: Row(children: [SizedBox(width: 180, child: Text(label)), Expanded(child: SelectableText(value))]));

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('ORNATE  /  Kalpa Gateway Setup')),
    body: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 1040), child: ListView(
      padding: const EdgeInsets.all(28), children: [
        Text('Connect. Configure. Verify.', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        const Text('Local commissioning over wired Ethernet • No SSH required by this app'),
        const SizedBox(height: 24),
        panel('1  Gateway connection', Column(children: [
          TextField(controller: host, enabled: !busy, decoration: const InputDecoration(labelText: 'Gateway Ethernet IP', helperText: 'Laptop: 192.168.10.1 / 255.255.255.0  •  Gateway: 192.168.10.2')),
          const SizedBox(height: 18),
          TextField(controller: token, enabled: !busy, obscureText: true, decoration: const InputDecoration(labelText: 'Gateway setup token', helperText: 'Unique per gateway. Kept in memory only.')),
          const SizedBox(height: 18),
          Align(alignment: Alignment.centerLeft, child: FilledButton.icon(
            onPressed: busy ? null : () => perform(() async { await refresh(); if (mounted) setState(() => message = 'Connected to gateway over Ethernet.'); }),
            icon: const Icon(Icons.cable), label: const Text('Connect / refresh status'))),
        ])),
        if (wifi != null) panel('Current gateway Wi-Fi', Column(children: [
          fact('Connection', wifi!['connected'] == true ? 'Connected' : 'Disconnected'),
          fact('SSID (quoted)', jsonEncode(wifi!['ssid'])),
          fact('Signal', '${wifi!['signal_dbm'] ?? 'Unknown'} dBm'),
          fact('Wi-Fi IP', (wifi!['ipv4'] as List).join(', ')),
          fact('Cloudflared service', '${wifi!['cloudflared_service']} (service state only)'),
          fact('Internet / tunnel checks', connectivity == null ? 'Use Verify internet and Cloudflare below' : 'See timestamped results below'),
          if (operation != null) fact('Latest Wi-Fi change', '${operation!['state']}'),
        ])),
        panel('Internet and Cloudflare verification', Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Gateway internet checks use mlan0. Public URL check runs from this laptop. Results are snapshots, not continuous monitoring.'),
          const SizedBox(height: 16),
          TextField(controller: publicUrl, enabled: !busy,
            decoration: const InputDecoration(labelText: 'Public HMI HTTPS URL', helperText: 'Default is gateway 3. Change this for other gateways.')),
          const SizedBox(height: 16),
          TextField(controller: sshHostname, enabled: !busy,
            decoration: const InputDecoration(labelText: 'Public SSH hostname (optional)', helperText: 'Use the actual Cloudflare hostname, not the local gw3-ssh.unityess alias.')),
          const SizedBox(height: 16),
          FilledButton.icon(onPressed: busy || wifi == null ? null : () => perform(verifyConnectivity),
            icon: const Icon(Icons.network_check), label: const Text('Verify internet and Cloudflare')),
          const SizedBox(height: 12),
          if (connectivity != null) fact('Gateway checked at', '${connectivity!['checked_at'] ?? 'Not available'}'),
          checkRow('Internet via Wi-Fi', 'internet'),
          checkRow('System DNS', 'dns'),
          checkRow('Default route', 'route'),
          checkRow('HTTPS / Cloudflare', 'https_cloudflare'),
          checkRow('HTTPS / second host', 'https_independent'),
          checkRow('Tunnel readiness', 'tunnel'),
          checkRow('Local HMI', 'local_hmi'),
          fact('Public HMI (laptop)', publicResult),
          if (publicCheckedAt != null) fact('Laptop checked at', '$publicCheckedAt'),
          fact('SSH / WebSocket', sshResult),
        ])),
        panel('2  Choose Wi-Fi network', Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          OutlinedButton.icon(onPressed: busy || wifi == null ? null : () => perform(scan), icon: const Icon(Icons.wifi_find), label: const Text('Scan nearby networks')),
          const SizedBox(height: 12),
          ...networks.map((network) => ListTile(
            title: Text(jsonEncode(network['ssid'])),
            subtitle: Text('${network['signal_dbm']} dBm  •  ${network['supported'] == true ? 'WPA/WPA2 Personal' : 'Unsupported network'}'),
            selected: identical(selected, network),
            leading: Icon(identical(selected, network) ? Icons.radio_button_checked : Icons.radio_button_off),
            enabled: !busy && network['supported'] == true,
            onTap: busy || network['supported'] != true ? null : () => setState(() { selected = network; manualSsid.text = network['ssid'] as String; }),
          )),
          const SizedBox(height: 12),
          TextField(controller: manualSsid, enabled: !busy, onChanged: (_) => setState(() => selected = null), decoration: const InputDecoration(labelText: 'Or enter exact WPA/WPA2 Personal SSID', helperText: 'Leading/trailing spaces matter. WPA3-only and enterprise networks are not supported.')),
          const SizedBox(height: 18),
          TextField(controller: password, enabled: !busy, obscureText: hidePassword,
            decoration: InputDecoration(labelText: 'Wi-Fi password', suffixIcon: IconButton(onPressed: () => setState(() => hidePassword = !hidePassword), icon: Icon(hidePassword ? Icons.visibility : Icons.visibility_off)))),
          const SizedBox(height: 18),
          FilledButton.icon(onPressed: busy || wifi == null ? null : () => perform(apply), icon: const Icon(Icons.save), label: const Text('Apply and verify Wi-Fi')),
        ])),
        if (busy) const LinearProgressIndicator(),
        const SizedBox(height: 12),
        SelectableText(message),
        const SizedBox(height: 20),
        const Text('Use the direct PC cable. The setup API uses a token over local HTTP; do not expose port 8765 through Cloudflare or an untrusted LAN.'),
      ],
    ))),
  );

  @override
  void dispose() {
    host.dispose(); token.dispose(); password.dispose(); manualSsid.dispose(); publicUrl.dispose(); sshHostname.dispose();
    super.dispose();
  }
}
