from pathlib import Path

p = Path('app/lib/gmail_accounts.dart')
s = p.read_text()

def change(old, new, label):
    global s
    if s.count(old) != 1:
        raise SystemExit('Gmail permission diagnostic: missing/duplicate ' + label)
    s = s.replace(old, new, 1)

change("  bool configured = false;\n  String error = '';\n",
"""  bool configured = false;
  String error = '';
  bool checkingPermissions = false;
  String permissionCheckError = '';
  DateTime? permissionsCheckedAt;
  Map<int, Map<String, dynamic>> permissionResults = {};
""", 'state')

change("""        accounts = rows;
        configured = data['configured'] == true;
        error = '';
""",
"""        accounts = rows;
        configured = data['configured'] == true;
        permissionResults = {};
        permissionsCheckedAt = null;
        permissionCheckError = '';
        error = '';
""", 'clear stale diagnostics')

methods = r'''  Future<void> checkGmailPermissions() async {
    if (busy || checkingPermissions) return;
    setState(() {
      checkingPermissions = true;
      permissionCheckError = '';
      permissionResults = {};
      permissionsCheckedAt = null;
    });
    try {
      final (base, key) = await _connection();
      final response = await http.post(
        Uri.parse('$base/api/gmail/accounts/diagnostics'),
        headers: {'x-api-key': key},
      ).timeout(const Duration(seconds: 115));
      final data = _json(response);
      final rows = dynList(data['accounts'])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      final checked = (data['checkedAt'] as num?)?.toInt() ?? 0;
      if (!mounted) return;
      setState(() {
        permissionResults = {
          for (final item in rows)
            if (int.tryParse('${item['id']}') != null)
              int.parse('${item['id']}'): item,
        };
        permissionsCheckedAt = checked > 0
            ? DateTime.fromMillisecondsSinceEpoch(checked * 1000, isUtc: true).toLocal()
            : DateTime.now();
      });
    } catch (e) {
      if (!mounted) return;
      final raw = '$e'.replaceFirst('Exception: ', '');
      setState(() {
        permissionCheckError = raw.contains('TimeoutException')
            ? 'El servidor tardó demasiado en verificar las cuentas. Reintenta cuando haya conexión.'
            : raw;
      });
    } finally {
      if (mounted) setState(() => checkingPermissions = false);
    }
  }

  String permissionLabel(String status) {
    switch (status) {
      case 'authorized': return 'Autorizada';
      case 'expired': return 'Permiso caducado / revocado';
      case 'missing_permissions': return 'Falta permiso de Gmail';
      case 'permission_error': return 'Acceso rechazado';
      case 'not_connected': return 'Sin autorización';
      case 'configuration_error': return 'Error de configuración';
      case 'temporary_error': return 'No se pudo verificar';
      case 'disabled': return 'Desactivada';
      default: return 'Sin comprobar';
    }
  }

  IconData permissionIcon(String status) {
    switch (status) {
      case 'authorized': return Icons.verified_outlined;
      case 'expired':
      case 'missing_permissions':
      case 'permission_error':
      case 'not_connected': return Icons.gpp_bad_outlined;
      case 'disabled': return Icons.pause_circle_outline;
      default: return Icons.warning_amber_outlined;
    }
  }

  Color permissionColor(BuildContext context, String status) {
    final palette = Theme.of(context).colorScheme;
    if (status == 'authorized') return Colors.green;
    if (status == 'disabled') return palette.onSurfaceVariant;
    if (status == 'temporary_error' || status == 'configuration_error') {
      return palette.tertiary;
    }
    return palette.error;
  }

  Widget permissionSubtitle(Map<String, dynamic> account) {
    final id = int.tryParse('${account['id']}');
    final detail = id == null ? null : permissionResults[id];
    final status = '${detail?['status'] ?? 'not_checked'}';
    final needsAuthorization = const {
      'expired', 'missing_permissions', 'permission_error', 'not_connected',
    }.contains(status);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(_accountSubtitle(account)),
        if (detail != null) ...[
          const SizedBox(height: 6),
          Row(children: [
            Icon(permissionIcon(status), size: 17,
                color: permissionColor(context, status)),
            const SizedBox(width: 5),
            Expanded(
              child: Text(
                permissionLabel(status),
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: permissionColor(context, status),
                ),
              ),
            ),
          ]),
          const SizedBox(height: 3),
          Text('${detail['message'] ?? ''}',
            style: Theme.of(context).textTheme.bodySmall),
          if (needsAuthorization) ...[
            const SizedBox(height: 4),
            TextButton.icon(
              onPressed: busy || checkingPermissions || id == null
                  ? null : () => connect(id),
              icon: const Icon(Icons.refresh, size: 17),
              label: const Text('Volver a autorizar'),
            ),
          ],
        ],
      ],
    );
  }

'''
change("  Future<void> connect([int? accountId]) async {\n",
       methods + "  Future<void> connect([int? accountId]) async {\n",
       'methods')

change("""                  if (error.isNotEmpty) ...[
""",
"""                  const SizedBox(height: 10),
                  FilledButton.icon(
                    onPressed: busy || checkingPermissions || accounts.isEmpty
                        ? null : checkGmailPermissions,
                    icon: const Icon(Icons.shield_outlined),
                    label: Text(checkingPermissions
                        ? 'Comprobando permisos…'
                        : 'Comprobar permisos de Gmail'),
                  ),
                  if (checkingPermissions) ...[
                    const SizedBox(height: 8),
                    const LinearProgressIndicator(),
                    const SizedBox(height: 6),
                    const Text('Consultando Google sin cambiar las cuentas ni leer correos.'),
                  ],
                  if (permissionsCheckedAt != null) ...[
                    const SizedBox(height: 8),
                    Text('Permisos verificados: '
                        '${permissionResults.values.where((x) => x['status'] == 'authorized').length} de '
                        '${accounts.where((x) => x['enabled'] == true).length} cuentas activas. '
                        'Comprobado: '
                        '${permissionsCheckedAt!.hour.toString().padLeft(2, '0')}:'
                        '${permissionsCheckedAt!.minute.toString().padLeft(2, '0')}.'),
                  ] else if (!checkingPermissions) ...[
                    const SizedBox(height: 6),
                    const Text('«Activa» solo habilita búsquedas; no confirma que Google conserve el permiso.'),
                  ],
                  if (permissionCheckError.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(permissionCheckError,
                      style: TextStyle(color: Theme.of(context).colorScheme.error)),
                  ],
                  if (error.isNotEmpty) ...[
""",
'button and summary')
change("                        subtitle: Text(_accountSubtitle(account)),",
       "                        subtitle: permissionSubtitle(account),",
       'per-account results')
p.write_text(s)
print('Gmail v34: manual permission verification and status per account installed.')
