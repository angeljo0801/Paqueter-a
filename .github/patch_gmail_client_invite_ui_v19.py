from pathlib import Path

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'Missing: {label}')
    return text.replace(old, new, 1)

main = Path('app/lib/main.dart')
s = main.read_text()
if "package:flutter/services.dart" not in s:
    s = s.replace("import 'package:flutter/material.dart';\n",
                  "import 'package:flutter/material.dart';\nimport 'package:flutter/services.dart';\n", 1)
if "package:qr_flutter/qr_flutter.dart" not in s:
    s = s.replace("import 'package:path_provider/path_provider.dart';\n",
                  "import 'package:path_provider/path_provider.dart';\nimport 'package:qr_flutter/qr_flutter.dart';\nimport 'package:share_plus/share_plus.dart';\n", 1)
main.write_text(s)

pub = Path('app/pubspec.yaml')
s = pub.read_text()
if '  qr_flutter:' not in s:
    s = s.replace("  file_picker: ^10.3.3\n", "  file_picker: ^10.3.3\n  qr_flutter: ^4.1.0\n", 1)
pub.write_text(s)

p = Path('app/lib/gmail_accounts.dart')
s = p.read_text()
s = replace_once(s,
"  List<Map<String, dynamic>> accounts = [];\n",
"  List<Map<String, dynamic>> accounts = [];\n  List<Map<String, dynamic>> clients = [];\n",
'clients state')

s = replace_once(s,
"""      if (!mounted) return;
      setState(() {
        accounts = rows;
""",
"""      final localClients = active(await Store.list('clients'));
      localClients.sort((a, b) => '${a['name'] ?? ''}'.toLowerCase()
          .compareTo('${b['name'] ?? ''}'.toLowerCase()));
      if (!mounted) return;
      setState(() {
        accounts = rows;
        clients = localClients;
""",
'load clients')

marker = "  Future<void> connect([int? accountId]) async {\n"
methods = r'''  String _accountSubtitle(Map<String, dynamic> account) {
    final owner = '${account['clientName'] ?? ''}'.trim();
    final status = account['primary'] == true
        ? 'Principal · ${account['enabled'] == true ? 'Activa' : 'Desactivada'}'
        : (account['enabled'] == true ? 'Activa para búsquedas' : 'No se usa en búsquedas');
    return owner.isEmpty ? status : 'Cliente: $owner · $status';
  }

  Future<void> _inviteClient(Map<String, dynamic> client) async {
    if (busy) return;
    final id = '${client['id'] ?? ''}'.trim();
    final name = '${client['name'] ?? ''}'.trim();
    if (id.isEmpty) return;
    setState(() => busy = true);
    try {
      final (base, key) = await _connection();
      final uri = Uri.parse('$base/api/gmail/client-invite').replace(
        queryParameters: {'client_id': id, 'client_name': name},
      );
      final response = await http.post(uri, headers: {'x-api-key': key})
          .timeout(const Duration(seconds: 30));
      final data = _json(response);
      final url = '${data['url'] ?? ''}'.trim();
      if (url.isEmpty) throw Exception('El servidor no devolvió el enlace.');
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(name.isEmpty ? 'Conectar correo de cliente' : 'Correo de $name'),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Text('Envíale este enlace o QR. La clienta lo abre en su propio teléfono y autoriza su Gmail.'),
              const SizedBox(height: 16),
              Container(
                color: Colors.white,
                padding: const EdgeInsets.all(12),
                child: QrImageView(data: url, size: 230, backgroundColor: Colors.white),
              ),
              const SizedBox(height: 12),
              SelectableText(url),
              const SizedBox(height: 8),
              const Text('El enlace vence en 7 días.', style: TextStyle(fontWeight: FontWeight.w600)),
            ]),
          ),
          actions: [
            TextButton.icon(
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: url));
                if (dialogContext.mounted) {
                  ScaffoldMessenger.of(dialogContext).showSnackBar(
                    const SnackBar(content: Text('Enlace copiado.')),
                  );
                }
              },
              icon: const Icon(Icons.copy),
              label: const Text('Copiar'),
            ),
            TextButton.icon(
              onPressed: () => Share.share('Autoriza tu Gmail para Paquetería:\n$url'),
              icon: const Icon(Icons.share),
              label: const Text('Compartir'),
            ),
            FilledButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Listo')),
          ],
        ),
      );
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

  Future<void> connectClientEmail() async {
    if (busy) return;
    if (clients.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Primero crea el cliente en Paquetería.')),
      );
      return;
    }
    final selected = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: SizedBox(
          height: MediaQuery.of(ctx).size.height * .65,
          child: Column(children: [
            const ListTile(
              leading: Icon(Icons.person_add_alt_1),
              title: Text('¿De qué cliente es el correo?'),
              subtitle: Text('Selecciona el cliente para generar su enlace privado.'),
            ),
            const Divider(height: 1),
            Expanded(
              child: ListView.builder(
                itemCount: clients.length,
                itemBuilder: (_, i) {
                  final client = clients[i];
                  return ListTile(
                    leading: const CircleAvatar(child: Icon(Icons.person)),
                    title: Text('${client['name'] ?? 'Cliente'}'),
                    onTap: () => Navigator.pop(ctx, client),
                  );
                },
              ),
            ),
          ]),
        ),
      ),
    );
    if (selected != null && mounted) await _inviteClient(selected);
  }

'''
s = replace_once(s, marker, methods + marker, 'invite methods')

s = replace_once(s,
"""                        subtitle: Text(
                          account['primary'] == true
                              ? 'Principal · ${account['enabled'] == true ? 'Activa' : 'Desactivada'}'
                              : (account['enabled'] == true
                                  ? 'Activa para búsquedas'
                                  : 'No se usa en búsquedas'),
                        ),
""",
"""                        subtitle: Text(_accountSubtitle(account)),
""",
'account owner subtitle')

s = replace_once(s,
"""                  FilledButton.icon(
                    onPressed: busy || !configured ? null : () => connect(),
                    icon: const Icon(Icons.add),
                    label: const Text('Conectar otra cuenta Gmail'),
                  ),
""",
"""                  FilledButton.icon(
                    onPressed: busy || !configured ? null : connectClientEmail,
                    icon: const Icon(Icons.person_add_alt_1),
                    label: const Text('Conectar correo de cliente'),
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: busy || !configured ? null : () => connect(),
                    icon: const Icon(Icons.add),
                    label: const Text('Conectar otra cuenta Gmail en este dispositivo'),
                  ),
""",
'client invite button')
p.write_text(s)
print('Client Gmail invite UI applied.')
