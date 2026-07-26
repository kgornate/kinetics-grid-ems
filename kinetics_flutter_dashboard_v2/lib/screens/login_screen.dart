import 'package:flutter/material.dart';

import '../core/state/gateway_controller.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.controller});

  final GatewayController controller;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _baseUrl = TextEditingController(text: 'http://192.168.10.2:8000');
  final _username = TextEditingController(text: 'internal');
  final _password = TextEditingController(text: 'Internal@123');
  bool _obscure = true;

  @override
  void dispose() {
    _baseUrl.dispose();
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    try {
      await widget.controller.login(
        baseUrl: _baseUrl.text,
        username: _username.text.trim(),
        password: _password.text,
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(widget.controller.errorMessage ?? 'Login failed')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: Card(
              elevation: 4,
              child: Padding(
                padding: const EdgeInsets.all(28),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Icon(Icons.energy_savings_leaf, size: 60),
                      const SizedBox(height: 12),
                      Text(
                        'Kinetics Gateway',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'BMS, rack, environment and PCS telemetry',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                      const SizedBox(height: 28),
                      TextFormField(
                        controller: _baseUrl,
                        decoration: const InputDecoration(
                          labelText: 'Gateway API base URL',
                          hintText: 'http://192.168.10.2:8000',
                          prefixIcon: Icon(Icons.lan),
                          border: OutlineInputBorder(),
                        ),
                        validator: (value) => value == null || value.trim().isEmpty ? 'Enter the gateway URL' : null,
                      ),
                      const SizedBox(height: 10),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          ActionChip(
                            avatar: const Icon(Icons.cable, size: 17),
                            label: const Text('Local LAN'),
                            onPressed: () => _baseUrl.text = 'http://192.168.10.2:8000',
                          ),
                          ActionChip(
                            avatar: const Icon(Icons.wifi, size: 17),
                            label: const Text('Wi-Fi IP'),
                            onPressed: () {
                              _baseUrl.selection = TextSelection(baseOffset: 0, extentOffset: _baseUrl.text.length);
                            },
                          ),
                          ActionChip(
                            avatar: const Icon(Icons.cloud, size: 17),
                            label: const Text('Cloudflare URL'),
                            onPressed: () {
                              _baseUrl.text = 'https://';
                              _baseUrl.selection = TextSelection.collapsed(offset: _baseUrl.text.length);
                            },
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      TextFormField(
                        controller: _username,
                        decoration: const InputDecoration(
                          labelText: 'Username',
                          prefixIcon: Icon(Icons.person),
                          border: OutlineInputBorder(),
                        ),
                        validator: (value) => value == null || value.trim().isEmpty ? 'Enter a username' : null,
                      ),
                      const SizedBox(height: 16),
                      TextFormField(
                        controller: _password,
                        obscureText: _obscure,
                        decoration: InputDecoration(
                          labelText: 'Password',
                          prefixIcon: const Icon(Icons.lock),
                          border: const OutlineInputBorder(),
                          suffixIcon: IconButton(
                            onPressed: () => setState(() => _obscure = !_obscure),
                            icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                          ),
                        ),
                        onFieldSubmitted: (_) => _submit(),
                        validator: (value) => value == null || value.isEmpty ? 'Enter a password' : null,
                      ),
                      const SizedBox(height: 20),
                      FilledButton.icon(
                        onPressed: widget.controller.busy ? null : _submit,
                        icon: widget.controller.busy
                            ? const SizedBox.square(
                                dimension: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.login),
                        label: Text(widget.controller.busy ? 'Connecting...' : 'Connect and sign in'),
                      ),
                      if (widget.controller.errorMessage != null) ...[
                        const SizedBox(height: 14),
                        Text(
                          widget.controller.errorMessage!,
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Theme.of(context).colorScheme.error),
                        ),
                      ],
                      const SizedBox(height: 18),
                      const Text(
                        'The same app works over direct Ethernet, gateway Wi-Fi IP, or the Cloudflare URL. Only this base URL changes.',
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
