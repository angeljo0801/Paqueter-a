from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# Register the page.
main = Path('app/lib/main.dart')
s = main.read_text()
if "part 'gmail_accounts.dart';" not in s:
    s = replace_once(
        s,
        "part 'extras.dart';\n",
        "part 'extras.dart';\npart 'gmail_accounts.dart';\n",
        'gmail_accounts part',
    )
main.write_text(s)


# Multi-account Gmail UI. Uses the same WhatsBot backend URL and APP_API_KEY
# already configured in Paquetería.
gmail_page = r'''part of 'main.dart';

class GmailAccountsPage extends StatefulWidget {
  const GmailAccountsPage({super.key});
  @override
  State<GmailAccountsPage> createState() => _GmailAccountsPageState();
}

class _GmailAccountsPageState extends State<GmailAccountsPage>
    with WidgetsBindingObserver {
  List<Map<String, dynamic>> accounts = [];
  bool loading = true;
  bool busy = false;
  bool configured = false;
  String error = '';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    load();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && !busy) {
      unawaited(load(silent: true));
    }
  }

  Future<(String, String)> _connection() async {
    final base = (await WhatsBotPurchaseSyncService.backendUrl())
        .trim()
        .replaceAll(RegExp(r'/$'), '');
    final key = (await WhatsBotPurchaseSyncService.apiKey()).trim();
    if (key.isEmpty) {
      throw Exception('Falta la APP_API_KEY de WhatsBot en Configuración.');
    }
    return (base, key);
  }

  Map<String, dynamic> _json(http.Response response) {
    dynamic body;
    try {
      body = jsonDecode(response.body);
    } catch (_) {
      body = null;
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = body is Map && body['detail'] != null
          ? '${body['detail']}'
          : response.body;
      throw Exception(detail.isEmpty
          ? 'Servidor respondió ${response.statusCode}'
          : detail);
    }
    return body is Map
        ? Map<String, dynamic>.from(body)
        : <String, dynamic>{};
  }

  Future<void> load({bool silent = false}) async {
    if (!silent && mounted) setState(() => loading = true);
    try {
      final (base, key) = await _connection();
      final response = await http.get(
        Uri.parse('$base/api/gmail/accounts'),
        headers: {'x-api-key': key},
      ).timeout(const Duration(seconds: 30));
      final data = _json(response);
      final rows = dynList(data['accounts'])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      if (!mounted) return;
      setState(() {
        accounts = rows;
        configured = data['configured'] == true;
        error = '';
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        error = '$e'.replaceFirst('Exception: ', '');
        loading = false;
      });
    }
  }

  Future<void> connect([int? accountId]) async {
    if (busy) return;
    setState(() => busy = true);
    try {
      final (base, key) = await _connection();
      final uri = Uri.parse('$base/api/gmail/auth-url').replace(
        queryParameters: accountId == null ? null : {'account_id': '$accountId'},
      );
      final response = await http.get(
        uri,
        headers: {'x-api-key': key},
      ).timeout(const Duration(seconds: 30));
      final data = _json(response);
      final url = '${data['url'] ?? ''}'.trim();
      if (url.isEmpty) throw Exception('Google OAuth no devolvió una URL.');
      if (!await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication)) {
        throw Exception('No pude abrir Google.');
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            duration: Duration(seconds: 7),
            content: Text('Autoriza la cuenta en Google y vuelve a Paquetería.'),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$e'.replaceFirst('Exception: ', ''))),
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _post(String path, [Map<String, String>? query]) async {
    final (base, key) = await _connection();
    final uri = Uri.parse('$base$path').replace(queryParameters: query);
    final response = await http.post(uri, headers: {'x-api-key': key})
        .timeout(const Duration(seconds: 30));
    _json(response);
  }

  Future<void> setEnabled(Map<String, dynamic> account, bool value) async {
    if (busy) return;
    setState(() => busy = true);
    try {
      final id = int.tryParse('${account['id']}');
      if (id == null) throw Exception('Cuenta inválida.');
      await _post('/api/gmail/accounts/$id/enabled', {'enabled': '$value'});
      await load(silent: true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$e'.replaceFirst('Exception: ', ''))),
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> setPrimary(Map<String, dynamic> account) async {
    if (busy || account['primary'] == true) return;
    setState(() => busy = true);
    try {
      final id = int.tryParse('${account['id']}');
      if (id == null) throw Exception('Cuenta inválida.');
      await _post('/api/gmail/accounts/$id/primary');
      await load(silent: true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$e'.replaceFirst('Exception: ', ''))),
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> removeAccount(Map<String, dynamic> account) async {
    final email = '${account['email'] ?? ''}'.trim();
    final ok = await showDialog<bool>(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('Desconectar correo'),
            content: Text(
              '¿Quitar ${email.isEmpty ? 'esta cuenta' : email}? No se borrará ningún correo de Gmail.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Cancelar'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Desconectar'),
              ),
            ],
          ),
        ) ??
        false;
    if (!ok || busy) return;
    setState(() => busy = true);
    try {
      final id = int.tryParse('${account['id']}');
      if (id == null) throw Exception('Cuenta inválida.');
      final (base, key) = await _connection();
      final response = await http.delete(
        Uri.parse('$base/api/gmail/accounts/$id'),
        headers: {'x-api-key': key},
      ).timeout(const Duration(seconds: 30));
      _json(response);
      await load(silent: true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$e'.replaceFirst('Exception: ', ''))),
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final activeCount = accounts.where((e) => e['enabled'] == true).length;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Gmail · Correos conectados'),
        actions: [
          IconButton(
            onPressed: busy ? null : () => load(),
            tooltip: 'Actualizar',
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: () => load(),
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Al reconstruir una compra, Paquetería busca en todas las cuentas activas en paralelo y combina los correos encontrados.',
                          ),
                          const SizedBox(height: 8),
                          Text(
                            '${accounts.length} conectada(s) · $activeCount activa(s)',
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                        ],
                      ),
                    ),
                  ),
                  if (error.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    Card(child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Text(error),
                    )),
                  ],
                  if (!configured) ...[
                    const SizedBox(height: 10),
                    const Card(child: Padding(
                      padding: EdgeInsets.all(12),
                      child: Text('Google OAuth no está configurado en el servidor.'),
                    )),
                  ],
                  const SizedBox(height: 10),
                  for (final account in accounts) ...[
                    Card(
                      child: ListTile(
                        leading: Icon(
                          account['primary'] == true ? Icons.star : Icons.mail_outline,
                        ),
                        title: Text('${account['email'] ?? 'Cuenta Gmail'}'),
                        subtitle: Text(
                          account['primary'] == true
                              ? 'Principal · ${account['enabled'] == true ? 'Activa' : 'Desactivada'}'
                              : (account['enabled'] == true
                                  ? 'Activa para búsquedas'
                                  : 'No se usa en búsquedas'),
                        ),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Switch(
                              value: account['enabled'] == true,
                              onChanged: busy ? null : (v) => setEnabled(account, v),
                            ),
                            PopupMenuButton<String>(
                              enabled: !busy,
                              onSelected: (value) {
                                if (value == 'primary') setPrimary(account);
                                if (value == 'reconnect') {
                                  connect(int.tryParse('${account['id']}'));
                                }
                                if (value == 'delete') removeAccount(account);
                              },
                              itemBuilder: (_) => [
                                if (account['primary'] != true)
                                  const PopupMenuItem(
                                    value: 'primary',
                                    child: Text('Hacer principal'),
                                  ),
                                const PopupMenuItem(
                                  value: 'reconnect',
                                  child: Text('Volver a autorizar'),
                                ),
                                const PopupMenuItem(
                                  value: 'delete',
                                  child: Text('Desconectar'),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                  ],
                  if (accounts.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 20),
                      child: Center(child: Text('No hay cuentas Gmail conectadas.')),
                    ),
                  FilledButton.icon(
                    onPressed: busy || !configured ? null : () => connect(),
                    icon: const Icon(Icons.add),
                    label: const Text('Conectar otra cuenta Gmail'),
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: busy ? null : () => load(),
                    icon: const Icon(Icons.refresh),
                    label: const Text('Actualizar estado'),
                  ),
                ],
              ),
            ),
    );
  }
}
'''
Path('app/lib/gmail_accounts.dart').write_text(gmail_page)


# Add the page to Más.
extras = Path('app/lib/extras.dart')
s = extras.read_text()
if "'Correos conectados'" not in s:
    marker = "_more(context,Icons.settings,'Configuración','Tarifa por libra, comisión y reglas',const SettingsPage()),"
    s = replace_once(
        s,
        marker,
        "_more(context,Icons.email_outlined,'Correos conectados','Gmail usados para reconstruir compras y tracking',const GmailAccountsPage()),\n" + marker,
        'Correos conectados en Más',
    )
extras.write_text(s)


# Store and display which Gmail accounts contributed to a reconstruction.
packages = Path('app/lib/packages.dart')
s = packages.read_text()
if 'List<String> gmailSourceEmails = [];' not in s:
    s = replace_once(
        s,
        "  List<Map<String, dynamic>> emailAttachmentImages = [];\n",
        "  List<Map<String, dynamic>> emailAttachmentImages = [];\n  List<String> gmailSourceEmails = [];\n",
        'gmailSourceEmails state',
    )
if "widget.existing?['gmailSourceEmails']" not in s:
    s = replace_once(
        s,
        "    hiddenEmailPhotoUrls.addAll(dynList(widget.existing?['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n",
        "    hiddenEmailPhotoUrls.addAll(dynList(widget.existing?['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n    gmailSourceEmails = dynList(widget.existing?['gmailSourceEmails']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();\n",
        'load gmailSourceEmails',
    )
if "dynList(data['sourceEmails'])" not in s:
    s = replace_once(
        s,
        "        gmailEta.text = '${data['estimatedDelivery'] ?? ''}'.trim();\n",
        "        gmailEta.text = '${data['estimatedDelivery'] ?? ''}'.trim();\n        gmailSourceEmails = dynList(data['sourceEmails']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();\n",
        'set sourceEmails',
    )
if "'gmailSourceEmails': gmailSourceEmails," not in s:
    s = replace_once(
        s,
        "      'gmailEstimatedDelivery': gmailEta.text.trim(),\n",
        "      'gmailEstimatedDelivery': gmailEta.text.trim(),\n      'gmailSourceEmails': gmailSourceEmails,\n",
        'save gmailSourceEmails',
    )
if 'Encontrado en:' not in s:
    old = """        TextField(controller: gmailEta, decoration: const InputDecoration(labelText: 'Entrega estimada obtenida del correo')),
        const SizedBox(height: 12),
        _drop('Courier / agencia'"""
    new = """        TextField(controller: gmailEta, decoration: const InputDecoration(labelText: 'Entrega estimada obtenida del correo')),
        if (gmailSourceEmails.isNotEmpty) ...[
          const SizedBox(height: 10),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(10),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.mark_email_read_outlined, size: 20),
                  const SizedBox(width: 8),
                  Expanded(child: Text('Encontrado en: ${gmailSourceEmails.join(', ')}')),
                ],
              ),
            ),
          ),
        ],
        const SizedBox(height: 12),
        _drop('Courier / agencia'"""
    s = replace_once(s, old, new, 'mostrar correos fuente')
packages.write_text(s)

print('Multi-account Gmail support applied.')
