import 'package:flutter/material.dart';

import '../api/northbound_api_client.dart';
import '../config/app_config.dart';
import '../models/auth_session.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    required this.activeProfile,
    required this.onProfileChanged,
    required this.onLogin,
  });

  final ApiProfile activeProfile;
  final void Function(ApiProfile profile) onProfileChanged;
  final void Function(AuthSession session) onLogin;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final usernameController = TextEditingController(text: 'customer');
  final passwordController = TextEditingController();
  bool loading = false;
  bool obscurePassword = true;
  String? error;

  @override
  void dispose() {
    usernameController.dispose();
    passwordController.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    final username = usernameController.text.trim();
    final password = passwordController.text;
    if (username.isEmpty || password.isEmpty) {
      setState(() => error = 'Enter username and password.');
      return;
    }
    setState(() {
      loading = true;
      error = null;
    });
    final apiClient = NorthboundApiClient(
      restBaseUrl: widget.activeProfile.restBaseUrl,
      logsBaseUrl: widget.activeProfile.logsBaseUrl,
      httpTimeout: widget.activeProfile.httpTimeout,
    );
    final result = await apiClient.login(username: username, password: password);
    if (!mounted) return;
    setState(() {
      loading = false;
      error = result.error;
    });
    if (result.isSuccess && result.data != null) {
      widget.onLogin(result.data!);
    }
  }

  void _useProfile(ApiProfile profile) {
    widget.onProfileChanged(profile);
  }

  @override
  Widget build(BuildContext context) {
    final profile = widget.activeProfile;
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: Card(
            margin: const EdgeInsets.all(18),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(Icons.security, size: 46, color: Theme.of(context).colorScheme.primary),
                  const SizedBox(height: 12),
                  Text('NorthBound EMS Login', style: Theme.of(context).textTheme.headlineSmall, textAlign: TextAlign.center),
                  const SizedBox(height: 8),
                  Text(
                    'Login is enforced at the gateway API level. The same login works for Flutter and IT web integration.',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 20),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    alignment: WrapAlignment.center,
                    children: [
                      ChoiceChip(
                        label: const Text('Local eth0'),
                        selected: profile.name == ApiProfile.localEth0.name,
                        onSelected: (_) => _useProfile(ApiProfile.localEth0),
                      ),
                      ChoiceChip(
                        label: const Text('Cloudflare'),
                        selected: profile.name == ApiProfile.cloudflare.name,
                        onSelected: (_) => _useProfile(ApiProfile.cloudflare),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text('API: ${profile.restBaseUrl}', textAlign: TextAlign.center),
                  Text('Timeout: ${profile.httpTimeout.inSeconds}s', textAlign: TextAlign.center),
                  const SizedBox(height: 18),
                  TextField(
                    controller: usernameController,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(labelText: 'Username', prefixIcon: Icon(Icons.person)),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: passwordController,
                    obscureText: obscurePassword,
                    onSubmitted: (_) => _login(),
                    decoration: InputDecoration(
                      labelText: 'Password',
                      prefixIcon: const Icon(Icons.lock),
                      suffixIcon: IconButton(
                        icon: Icon(obscurePassword ? Icons.visibility : Icons.visibility_off),
                        onPressed: () => setState(() => obscurePassword = !obscurePassword),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (loading) const LinearProgressIndicator(),
                  if (error != null) ...[
                    const SizedBox(height: 10),
                    Card(
                      color: Theme.of(context).colorScheme.errorContainer,
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Text(error!, style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer)),
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: loading ? null : _login,
                    icon: const Icon(Icons.login),
                    label: const Text('Login'),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Configured roles: customer_admin and internal_admin. Customer admin can access monitoring, storage diagnostics, internal diagnostics, and customer-safe runtime config APIs.',
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
