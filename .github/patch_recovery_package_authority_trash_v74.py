from pathlib import Path

# Recovery v74: local package edits/deletes are authoritative. WhatsBot used to
# pull its *older* record first and overwrite a package before sending local
# changes back. Remote sync could also recreate packages removed from Trash.
# Add persistent deletion tombstones (survive Empty Trash), save confirmation,
# fresh-disk merges for async sync writers, and a confirmed Empty Trash action.

p = Path('app/lib/main.dart')
s = p.read_text()
a = "Future<void> softDelete(String key, String id) async {"
assert s.count(a) == 1
s = s.replace(a, r'''// Tombstones are separate from the Trash collection, so even an item
// permanently removed from Trash cannot be reimported by WhatsBot later.
// Explicit Restore or creating a new package with the same tracking clears
// the matching tombstone; ordinary sync does not.
class PackageDeletionLedger {
  static const String _key = 'packages_deleted_sync_ids_v1';

  static String tracking(dynamic v) =>
      (v ?? '').toString().replaceAll(RegExp(r'\s+'), '').toUpperCase();

  static Set<String> ids(Map<String, dynamic> row) {
    final tokens = <String>{};
    final track = tracking(row['tracking']);
    if (track.isNotEmpty) tokens.add('tracking:' + track);
    for (final field in <String>[
      'whatsbotPackageSyncId',
      'whatsbotPackageRemoteId',
    ]) {
      final id = (row[field] ?? '').toString().trim();
      if (id.isNotEmpty) tokens.add('external:' + id);
    }
    final id = (row['id'] ?? '').toString().trim();
    if (id.isNotEmpty) {
      tokens.add('local:' + id);
      tokens.add('external:paqueteria-package-' + id);
    }
    return tokens;
  }

  static Future<Set<String>> load() async {
    final raw = await Store._readRaw(_key);
    if (raw == null || raw.isEmpty) return <String>{};
    final decoded = jsonDecode(raw);
    if (decoded is! List) throw const FormatException(
        'No se pudo leer el registro de eliminaciones.');
    return decoded.map((e) => e.toString()).toSet();
  }

  static bool blocks(Map<String, dynamic> row, Set<String> ledger) =>
      ids(row).any(ledger.contains);

  static Future<void> remember(Map<String, dynamic> row) async {
    final all = await load();
    if (all.addAll(ids(row)).isNotEmpty) {
      await Store._writeRaw(_key, jsonEncode(all.toList()));
    }
  }

  static Future<void> allowExplicit(Map<String, dynamic> row) async {
    final all = await load();
    final remove = ids(row);
    final normalized = tracking(row['tracking']);
    if (normalized.isNotEmpty) remove.add('tracking:' + normalized);
    if (all.removeAll(remove).isNotEmpty) {
      await Store._writeRaw(_key, jsonEncode(all.toList()));
    }
  }
}

Future<void> softDelete(String key, String id) async {''',1)
# Set.addAll/removeAll are void in Dart, not bool. Compare lengths instead.
s=s.replace("    if (all.addAll(ids(row)).isNotEmpty) {\n      await Store._writeRaw(_key, jsonEncode(all.toList()));\n    }","    final sizeBefore = all.length;\n    all.addAll(ids(row));\n    if (all.length != sizeBefore) {\n      await Store._writeRaw(_key, jsonEncode(all.toList()));\n    }",1)
s=s.replace("    if (all.removeAll(remove).isNotEmpty) {\n      await Store._writeRaw(_key, jsonEncode(all.toList()));\n    }","    final sizeBefore = all.length;\n    all.removeAll(remove);\n    if (all.length != sizeBefore) {\n      await Store._writeRaw(_key, jsonEncode(all.toList()));\n    }",1)
old="""  final rows = await Store.list(key);
  final i = rows.indexWhere((e) => e['id'] == id);
  if (i >= 0) {
    rows[i]['deleted'] = true;
    rows[i]['deletedAt'] = DateTime.now().toIso8601String();
    await Store.saveList(key, rows);
  }"""
new="""  final rows = await Store.list(key, forceRefresh: true);
  final i = rows.indexWhere((e) => e['id'] == id);
  if (i >= 0) {
    if (key == 'packages') await PackageDeletionLedger.remember(rows[i]);
    rows[i]['deleted'] = true;
    rows[i]['deletedAt'] = DateTime.now().toIso8601String();
    await Store.saveList(key, rows);
  }"""
assert s.count(old) == 1, 'v74: soft delete changed'
s=s.replace(old,new,1)
p.write_text(s)

# Editing: preserve newest Gmail/photos/sync metadata from disk and always
# mark manual changes so the server pull cannot overwrite them. Never turn
# a deleted/missing package back into an active package from a stale editor.
p=Path('app/lib/packages.dart')
s=p.read_text()
a=s.index('  Future<void> save() async {',s.index('class PackageEditPage'))
b=s.index('\n  @override\n  Widget build(',a)
fn=s[a:b]
assert fn.count("    final rows = await Store.list('packages');")==1
fn=fn.replace("    final rows = await Store.list('packages');",r'''    final rows = await Store.list('packages', forceRefresh: true);
    final previousId = (widget.existing?['id'] ?? '').toString();
    final previousIndex = previousId.isEmpty ? -1 :
        rows.indexWhere((row) => (row['id'] ?? '').toString() == previousId);
    if (previousId.isNotEmpty &&
        (previousIndex < 0 || rows[previousIndex]['deleted'] == true)) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text(
            'Este paquete ya fue eliminado. No se guardaron cambios.',
          )),
        );
      }
      return;
    }''',1)
assert fn.count("      'deleted': false,")==1
fn=fn.replace("      'deleted': false,","      'deleted': false,\n      'paqueteriaLocalEditedAt': DateTime.now().toUtc().toIso8601String(),",1)
assert fn.count("    await Store.saveList('packages', rows);")==1
fn=fn.replace("    await Store.saveList('packages', rows);",r'''    await Store.saveList('packages', rows);
    // Creating a package intentionally with a formerly deleted tracking
    // permits that user-selected package; remote sync never does this itself.
    if (previousId.isEmpty) await PackageDeletionLedger.allowExplicit(item);
    final verified = await Store.list('packages', forceRefresh: true);
    final saved = verified.where((row) => row['id'] == item['id']).firstOrNull;
    if (saved == null || saved['deleted'] == true ||
        saved['paqueteriaLocalEditedAt'] != item['paqueteriaLocalEditedAt']) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text(
            'No se pudo verificar el guardado del paquete. Inténtalo de nuevo.',
          )),
        );
      }
      return;
    }''',1)
s=s[:a]+fn+s[b:]
p.write_text(s)

# Trash: restore is explicit and clears the tombstone, permanent delete
# retains it; Empty Trash covers every category but never active records.
p=Path('app/lib/extras.dart')
s=p.read_text()
a=s.index('class TrashPage extends StatefulWidget')
b=s.index('\nclass MorePage extends StatelessWidget',a)
trash = r'''class TrashPage extends StatefulWidget {
  const TrashPage({super.key});
  @override
  State<TrashPage> createState() => _TrashPageState();
}

class _TrashPageState extends State<TrashPage> {
  final keys = <String, String>{
    'clients': 'Clientes',
    'recipients': 'Destinatarios',
    'purchases': 'Compras',
    'packages': 'Paquetes',
    'trips': 'Viajes',
    'payments': 'Pagos',
    'expenses': 'Gastos',
    'flightWatches': 'Alertas de vuelos',
  };
  List<Map<String, dynamic>> deleted = [];
  bool busy = false;

  Future<void> load() async {
    final out = <Map<String, dynamic>>[];
    for (final entry in keys.entries) {
      final rows = await Store.list(entry.key, forceRefresh: true);
      for (final row in rows.where((e) => e['deleted'] == true)) {
        out.add({...row, '_key': entry.key, '_type': entry.value});
      }
    }
    if (mounted) setState(() => deleted = out);
  }

  @override
  void initState() { super.initState(); load(); }

  String label(Map<String, dynamic> row) => (
    row['name'] ?? row['tracking'] ?? row['store'] ??
    row['origin'] ?? row['amount'] ?? row['id']
  ).toString();

  Future<void> restore(Map<String, dynamic> row) async {
    if (busy) return;
    setState(() => busy = true);
    try {
      final key = (row['_key'] ?? '').toString();
      final rows = await Store.list(key, forceRefresh: true);
      final i = rows.indexWhere((e) => e['id'] == row['id'] &&
          e['deleted'] == true);
      if (i >= 0) {
        rows[i]['deleted'] = false;
        rows[i].remove('deletedAt');
        if (key == 'packages') {
          rows[i]['paqueteriaLocalEditedAt'] =
              DateTime.now().toUtc().toIso8601String();
        }
        await Store.saveList(key, rows);
        if (key == 'packages') {
          await PackageDeletionLedger.allowExplicit(rows[i]);
        }
      }
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('No se pudo restaurar: ' + error.toString())),
      );
    } finally {
      if (mounted) setState(() => busy = false);
      await load();
    }
  }

  Future<void> permanent(Map<String, dynamic> row) async {
    if (busy) return;
    setState(() => busy = true);
    try {
      final key = (row['_key'] ?? '').toString();
      final rows = await Store.list(key, forceRefresh: true);
      if (key == 'packages') {
        for (final saved in rows.where((e) =>
            e['id'] == row['id'] && e['deleted'] == true)) {
          await PackageDeletionLedger.remember(saved);
        }
      }
      rows.removeWhere((e) => e['id'] == row['id'] && e['deleted'] == true);
      await Store.saveList(key, rows);
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('No se pudo eliminar: ' + error.toString())),
      );
    } finally {
      if (mounted) setState(() => busy = false);
      await load();
    }
  }

  Future<void> emptyTrash() async {
    if (busy || deleted.isEmpty) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Vaciar papelera'),
        content: Text(
          '¿Eliminar definitivamente los ' +
          deleted.length.toString() +
          ' registros de la papelera? No se podrán recuperar desde la app. '
          'Los registros activos no se eliminarán.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Vaciar definitivamente'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => busy = true);
    var removed = 0;
    try {
      for (final key in keys.keys) {
        final rows = await Store.list(key, forceRefresh: true);
        final trash = rows.where((e) => e['deleted'] == true).toList();
        if (trash.isEmpty) continue;
        if (key == 'packages') {
          for (final row in trash) {
            await PackageDeletionLedger.remember(row);
          }
        }
        final kept = rows.where((e) => e['deleted'] != true).toList();
        await Store.saveList(key, kept);
        removed += trash.length;
      }
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(
          'Papelera vaciada: ' + removed.toString() + ' registros eliminados.',
        )),
      );
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('No se pudo completar el vaciado: ' +
          error.toString())),
      );
    } finally {
      if (mounted) setState(() => busy = false);
      await load();
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Papelera'),
      actions: [
        if (deleted.isNotEmpty)
          TextButton.icon(
            onPressed: busy ? null : emptyTrash,
            icon: const Icon(Icons.delete_forever_outlined),
            label: const Text('Vaciar'),
          ),
      ],
    ),
    body: busy
      ? const Center(child: CircularProgressIndicator())
      : deleted.isEmpty
        ? const Center(child: Text('Papelera vacía.'))
        : ListView.builder(
            itemCount: deleted.length,
            itemBuilder: (_, i) {
              final row = deleted[i];
              return ListTile(
                title: Text(label(row)),
                subtitle: Text((row['_type'] ?? '').toString()),
                trailing: PopupMenuButton<String>(
                  onSelected: (value) {
                    if (value == 'restore') {
                      restore(row);
                    } else {
                      permanent(row);
                    }
                  },
                  itemBuilder: (_) => const [
                    PopupMenuItem(
                      value: 'restore', child: Text('Restaurar'),
                    ),
                    PopupMenuItem(
                      value: 'delete', child: Text('Eliminar definitivamente'),
                    ),
                  ],
                ),
              );
            },
          ),
  );
}
'''
s=s[:a]+trash+s[b:]
p.write_text(s)

print('v74: package deletion ledger, verified manual edits, full confirmed trash empty implemented.')
