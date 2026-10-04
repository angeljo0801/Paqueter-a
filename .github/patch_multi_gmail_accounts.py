from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# 1) Register the Gmail account management page as part of the Flutter library.
main = Path('app/lib/main.dart')
s = main.read_text()
if "part 'gmail_accounts.dart';" not in s:
    s = replace_once(
        s,
        "part 'extras.dart';\n",
        "part 'extras.dart';\npart 'gmail_accounts.dart';\n",
        'part gmail_accounts.dart',
    )
main.write_text(s)


# 2) Create the multi-account Gmail management UI.
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
  bool actionBusy = false;
  String error = '';
  String redirectUri = '';
  bool configured = false;

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
    if (state == AppLifecycleState.resumed && !actionBusy) {
      unawaited(load(silent: true));
    }
  }

  Future<Map<String, String>> _connection() async {
    final base = (await WhatsBotPurchaseSyncService.backendUrl())
        .trim()
        .replaceAll(RegExp(r'/$'), '');
    final key = (await WhatsBotPurchaseSyncService.apiKey()).trim();
    if (key.isEmpty) {
      throw Exception(
        'Falta la APP_API_KEY. Configúrala primero en Configuración → WhatsBot.',
      );
    }
    return {'base': base, 'key': key};
  }

  Map<String, dynamic> _decodeResponse(http.Response response) {
    dynamic decoded;
    try {
      decoded = jsonDecode(response.body);
    } catch (_) {
      decoded = null;
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = decoded is Map && decoded['detail'] != null
          ? '${decoded['detail']}'
          : response.body;
      throw Exception(detail.isEmpty
          ? 'Servidor respondió ${response.statusCode}'
          : detail);
    }
    return decoded is Map
        ? Map<String, dynamic>.from(decoded)
        : <String, dynamic>{};
  }

  Future<void> load({bool silent = false}) async {
    if (!silent && mounted) setState(() => loading = true);
    try {
      final connection = await _connection();
      final uri = Uri.parse('${connection['base']}/api/gmail/accounts');
      final response = await http.get(
        uri,
        headers: {'x-api-key': connection['key']!},
      ).timeout(const Duration(seconds: 30));
      final data = _decodeResponse(response);
      final rows = dynList(data['accounts'])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      if (!mounted) return;
      setState(() {
        accounts = rows;
        configured = data['configured'] == true;
        redirectUri = '${data['redirectUri'] ?? ''}';
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
    if (actionBusy) return;
    setState(() => actionBusy = true);
    try {
      final connection = await _connection();
      final uri = Uri.parse('${connection['base']}/api/gmail/auth-url').replace(
        queryParameters:
            accountId == null ? null : {'account_id': '$accountId'},
      );
      final response = await http.get(
        uri,
        headers: {'x-api-key': connection['key']!},
      ).timeout(const Duration(seconds: 30));
      final data = _decodeResponse(response);
      final url = '${data['url'] ?? ''}'.trim();
      if (url.isEmpty) throw Exception('El servidor no devolvió la URL de Google.');
      final opened = await launchUrl(
        Uri.parse(url),
        mode: LaunchMode.externalApplication,
      );
      if (!opened) throw Exception('No pude abrir Google para autorizar Gmail.');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            duration: Duration(seconds: 8),
            content: Text(
              'Autoriza la cuenta en Google. Cuando vuelvas a Paquetería, la lista se actualizará automáticamente.',
            ),
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
      if (mounted) setState(() => actionBusy = false);
    }
  }

  Future<void> setEnabled(Map<String, dynamic> account, bool value) async {
    if (actionBusy) return;
    setState(() => actionBusy = true);
    try {
      final connection = await _connection();
      final id = int.tryParse('${account['id']}');
      if (id == null) throw Exception('Cuenta inválida.');
      final uri = Uri.parse(
        '${connection['base']}/api/gmail/accounts/$id/enabled',
      ).replace(queryParameters: {'enabled': '$value'});
      final response = await http.post(
        uri,
        headers: {'x-api-key': connection['key']!},
      ).timeout(const Duration(seconds: 30));
      _decodeResponse(response);
      await load(silent: true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$e'.replaceFirst('Exception: ', ''))),
        );
      }
    } finally {
      if (mounted) setState(() => actionBusy = false);
    }
  }

  Future<void> setPrimary(Map<String, dynamic> account) async {
    if (actionBusy || account['primary'] == true) return;
    setState(() => actionBusy = true);
    try {
      final connection = await _connection();
      final id = int.tryParse('${account['id']}');
      if (id == null) throw Exception('Cuenta inválida.');
      final response = await http.post(
        Uri.parse('${connection['base']}/api/gmail/accounts/$id/primary'),
        headers: {'x-api-key': connection['key']!},
      ).timeout(const Duration(seconds: 30));
      _decodeResponse(response);
      await load(silent: true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$e'.replaceFirst('Exception: ', ''))),
        );
      }
    } finally {
      if (mounted) setState(() => actionBusy = false);
    }
  }

  Future<void> removeAccount(Map<String, dynamic> account) async {
    final email = '${account['email'] ?? ''}'.trim();
    final confirmed = await showDialog<bool>(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('Desconectar correo'),
            content: Text(
              '¿Quieres quitar ${email.isEmpty ? 'esta cuenta' : email} de Paquetería? No se borrará ningún correo de Gmail.',
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
    if (!confirmed || actionBusy) return;
    setState(() => actionBusy = true);
    try {
      final connection = await _connection();
      final id = int.tryParse('${account['id']}');
      if (id == null) throw Exception('Cuenta inválida.');
      final response = await http.delete(
        Uri.parse('${connection['base']}/api/gmail/accounts/$id'),
        headers: {'x-api-key': connection['key']!},
      ).timeout(const Duration(seconds: 30));
      _decodeResponse(response);
      await load(silent: true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$e'.replaceFirst('Exception: ', ''))),
        );
      }
    } finally {
      if (mounted) setState(() => actionBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final enabledCount = accounts.where((a) => a['enabled'] == true).length;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Gmail · Correos conectados'),
        actions: [
          IconButton(
            tooltip: 'Actualizar',
            onPressed: actionBusy ? null : () => load(),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: load,
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
                            'Paquetería busca el tracking o número de orden en todos los correos activos al mismo tiempo y combina los resultados.',
                          ),
                          const SizedBox(height: 8),
                          Text(
                            '${accounts.length} cuenta(s) conectada(s) · $enabledCount activa(s)',
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                          if (redirectUri.isNotEmpty) ...[
                            const SizedBox(height: 6),
                            Text(
                              'OAuth: $redirectUri',
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                  if (!configured) ...[
                    const SizedBox(height: 12),
                    const Card(
                      child: Padding(
                        padding: EdgeInsets.all(14),
                        child: Text(
                          'El servidor todavía no tiene configurado GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET.',
                        ),
                      ),
                    ),
                  ],
                  if (error.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Text(error),
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  if (accounts.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(
                        child: Text('Todavía no hay cuentas Gmail conectadas.'),
                      ),
                    ),
                  for (final account in accounts) ...[
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
                        child: Row(
                          children: [
                            Icon(
                              account['primary'] == true
                                  ? Icons.star
                                  : Icons.mail_outline,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    '${account['email'] ?? 'Cuenta Gmail'}',
                                    style: const TextStyle(
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                  const SizedBox(height: 3),
                                  Text(
                                    account['primary'] == true
                                        ? 'Principal · ${account['enabled'] == true ? 'Activa' : 'Desactivada'}'
                                        : (account['enabled'] == true
                                            ? 'Activa para búsquedas'
                                            : 'No se usa en búsquedas'),
                                    style: Theme.of(context).textTheme.bodySmall,
                                  ),
                                ],
                              ),
                            ),
                            Switch(
                              value: account['enabled'] == true,
                              onChanged: actionBusy
                                  ? null
                                  : (v) => setEnabled(account, v),
                            ),
                            PopupMenuButton<String>(
                              enabled: !actionBusy,
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
                  const SizedBox(height: 8),
                  FilledButton.icon(
                    onPressed: actionBusy || !configured ? null : () => connect(),
                    icon: const Icon(Icons.add),
                    label: const Text('Conectar otra cuenta Gmail'),
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: actionBusy ? null : () => load(),
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


# 3) Expose the page under Más so account management is always reachable.
extras = Path('app/lib/extras.dart')
s = extras.read_text()
if "'Correos conectados'" not in s:
    marker = "_more(context,Icons.settings,'Configuración','Tarifa por libra, comisión y reglas',const SettingsPage()),"
    replacement = (
        "_more(context,Icons.email_outlined,'Correos conectados',"
        "'Gmail usados para reconstruir compras y tracking',const GmailAccountsPage()),\n"
        + marker
    )
    s = replace_once(s, marker, replacement, 'entrada Correos conectados')
extras.write_text(s)


# 4) Remember which accounts contributed to each package reconstruction and
# show that provenance directly in Editar paquete.
packages = Path('app/lib/packages.dart')
s = packages.read_text()
if 'List<String> gmailSourceEmails = [];' not in s:
    s = replace_once(
        s,
        "  List<Map<String, dynamic>> emailAttachmentImages = [];\n",
        "  List<Map<String, dynamic>> emailAttachmentImages = [];\n  List<String> gmailSourceEmails = [];\n",
        'estado gmailSourceEmails',
    )

if "widget.existing?['gmailSourceEmails']" not in s:
    s = replace_once(
        s,
        "    hiddenEmailPhotoUrls.addAll(dynList(widget.existing?['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n",
        "    hiddenEmailPhotoUrls.addAll(dynList(widget.existing?['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n    gmailSourceEmails = dynList(widget.existing?['gmailSourceEmails']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();\n",
        'carga gmailSourceEmails',
    )

if "dynList(data['sourceEmails'])" not in s:
    s = replace_once(
        s,
        "        gmailEta.text = '${data['estimatedDelivery'] ?? ''}'.trim();\n",
        "        gmailEta.text = '${data['estimatedDelivery'] ?? ''}'.trim();\n        gmailSourceEmails = dynList(data['sourceEmails']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();\n",
        'resultado sourceEmails',
    )

if "'gmailSourceEmails': gmailSourceEmails," not in s:
    s = replace_once(
        s,
        "      'gmailEstimatedDelivery': gmailEta.text.trim(),\n",
        "      'gmailEstimatedDelivery': gmailEta.text.trim(),\n      'gmailSourceEmails': gmailSourceEmails,\n",
        'guardar gmailSourceEmails',
    )

if "Encontrado en:" not in s:
    s = replace_once(
        s,
        "        TextField(controller: gmailEta, decoration: const InputDecoration(labelText: 'Entrega estimada obtenida del correo')),\n        const SizedBox(height: 12),\n        _drop('Courier / agencia'",
        "        TextField(controller: gmailEta, decoration: const InputDecoration(labelText: 'Entrega estimada obtenida del correo')),\n        if (gmailSourceEmails.isNotEmpty) ...[\n          const SizedBox(height: 10),\n          Card(\n            child: Padding(\n              padding: const EdgeInsets.all(10),\n              child: Row(\n                crossAxisAlignment: CrossAxisAlignment.start,\n                children: [\n                  const Icon(Icons.mark_email_read_outlined, size: 20),\n                  const SizedBox(width: 8),\n                  Expanded(child: Text('Encontrado en: ${gmailSourceEmails.join(', ')}')),\n                ],\n              ),\n            ),\n          ),\n        ],\n        const SizedBox(height: 12),\n        _drop('Courier / agencia'",
        'origen Gmail en UI del paquete',
    )

s = s.replace(
    "SnackBar(content: Text('Compra reconstruida desde Gmail${gmailStore.text.isEmpty ? '' : ' · ${gmailStore.text}'}')),
",
    "SnackBar(content: Text('Compra reconstruida desde ${gmailSourceEmails.isEmpty ? 'Gmail' : '${gmailSourceEmails.length} correo(s)'}${gmailStore.text.isEmpty ? '' : ' · ${gmailStore.text}'}')),
",
    1,
)
packages.write_text(s)

print('Multi-account Gmail support applied to Paqueteria build tree.')
