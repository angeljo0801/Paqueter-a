from pathlib import Path

migration = r'''import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class MigrationMergeStats {
  final String key;
  final String label;
  final int current;
  final int incoming;
  final int added;
  final int enriched;
  final int duplicatesAvoided;
  final int unchanged;

  const MigrationMergeStats({
    required this.key,
    required this.label,
    required this.current,
    required this.incoming,
    required this.added,
    required this.enriched,
    required this.duplicatesAvoided,
    required this.unchanged,
  });
}

class MigrationMergePlan {
  final String generatedAt;
  final Map<String, List<Map<String, dynamic>>> lists;
  final Map<String, dynamic> settings;
  final List<MigrationMergeStats> stats;
  final int skippedLegacyPhotoRefs;
  final int remappedReferences;

  const MigrationMergePlan({
    required this.generatedAt,
    required this.lists,
    required this.settings,
    required this.stats,
    required this.skippedLegacyPhotoRefs,
    required this.remappedReferences,
  });

  int get totalAdded => stats.fold(0, (sum, e) => sum + e.added);
  int get totalEnriched => stats.fold(0, (sum, e) => sum + e.enriched);
  int get totalDuplicates =>
      stats.fold(0, (sum, e) => sum + e.duplicatesAvoided);
}

class PaqueteriaMigrationMergeService {
  static const Map<String, String> _labels = {
    'clients': 'Clientes',
    'recipients': 'Destinatarios',
    'purchases': 'Compras',
    'packages': 'Paquetes',
    'payments': 'Pagos',
    'agents': 'Agentes',
    'agentReports': 'Informes de agentes',
    'trips': 'Viajes',
    'expenses': 'Gastos',
    'agencyShipments': 'Envíos por agencia',
  };

  // Dependencies are deliberately ordered. IDs deduplicated in an earlier
  // collection can therefore be remapped before a dependent record is merged.
  static const List<String> _mergeOrder = [
    'clients',
    'recipients',
    'purchases',
    'packages',
    'agents',
    'payments',
    'agentReports',
    'trips',
    'expenses',
    'agencyShipments',
  ];

  static int _idSeed = 0;

  static String _freshId() {
    _idSeed++;
    return '${DateTime.now().microsecondsSinceEpoch}$_idSeed';
  }

  static String _text(dynamic value) => '${value ?? ''}'.trim();

  static String _norm(dynamic value) => _text(value)
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9]+'), '');

  static String _phone(dynamic value) =>
      _text(value).replaceAll(RegExp(r'[^0-9]+'), '');

  static bool _missing(dynamic value) {
    if (value == null) return true;
    if (value is String) return value.trim().isEmpty;
    if (value is List) return value.isEmpty;
    if (value is Map) return value.isEmpty;
    return false;
  }

  static dynamic _clone(dynamic value) {
    if (value is Map) {
      return value.map((k, v) => MapEntry('$k', _clone(v)));
    }
    if (value is List) return value.map(_clone).toList();
    return value;
  }

  static String _mapIdentity(Map<dynamic, dynamic> row) {
    for (final key in const [
      'id',
      'clientId',
      'itemId',
      'tracking',
      'orderNumber',
      'url',
      'name',
    ]) {
      final value = _norm(row[key]);
      if (value.isNotEmpty) return '$key:$value';
    }
    return 'json:${jsonEncode(row)}';
  }

  static List<dynamic> _mergeLists(List<dynamic> current, List<dynamic> incoming) {
    final out = current.map(_clone).toList();
    for (final incomingValue in incoming) {
      if (incomingValue is Map) {
        final id = _mapIdentity(incomingValue);
        final index = out.indexWhere(
          (value) => value is Map && _mapIdentity(value) == id,
        );
        if (index >= 0 && out[index] is Map) {
          out[index] = _deepFill(
            Map<String, dynamic>.from(out[index] as Map),
            Map<String, dynamic>.from(incomingValue),
          );
        } else {
          out.add(_clone(incomingValue));
        }
      } else if (!out.any((value) => '$value' == '$incomingValue')) {
        out.add(_clone(incomingValue));
      }
    }
    return out;
  }

  static Map<String, dynamic> _deepFill(
    Map<String, dynamic> current,
    Map<String, dynamic> incoming,
  ) {
    final out = Map<String, dynamic>.from(current);
    for (final entry in incoming.entries) {
      final key = entry.key;
      final incomingValue = entry.value;
      if (!out.containsKey(key) || _missing(out[key])) {
        if (!_missing(incomingValue)) out[key] = _clone(incomingValue);
        continue;
      }
      final currentValue = out[key];
      if (currentValue is Map && incomingValue is Map) {
        out[key] = _deepFill(
          Map<String, dynamic>.from(currentValue),
          Map<String, dynamic>.from(incomingValue),
        );
      } else if (currentValue is List && incomingValue is List) {
        out[key] = _mergeLists(currentValue, incomingValue);
      }
    }
    return out;
  }

  static List<Map<String, dynamic>> _decodeStoredList(
    SharedPreferences prefs,
    String key,
  ) {
    final raw = prefs.getString(key);
    if (raw == null || raw.trim().isEmpty) return <Map<String, dynamic>>[];
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return <Map<String, dynamic>>[];
      return decoded
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
    } catch (_) {
      return <Map<String, dynamic>>[];
    }
  }

  static Map<String, dynamic> _decodeStoredSettings(SharedPreferences prefs) {
    final raw = prefs.getString('settings');
    if (raw == null || raw.trim().isEmpty) return <String, dynamic>{};
    try {
      final decoded = jsonDecode(raw);
      return decoded is Map
          ? Map<String, dynamic>.from(decoded)
          : <String, dynamic>{};
    } catch (_) {
      return <String, dynamic>{};
    }
  }

  static bool _legacyPrivatePath(String value) {
    final path = value.trim();
    return path.startsWith('/data/user/0/') ||
        path.startsWith('/data/data/');
  }

  static Map<String, dynamic> _sanitizeImportedRecord(
    Map<String, dynamic> source,
    List<int> skippedPhotos,
  ) {
    final row = Map<String, dynamic>.from(source);

    for (final key in const ['photoPath', 'receiptPath']) {
      final value = _text(row[key]);
      if (value.isNotEmpty && _legacyPrivatePath(value) && !File(value).existsSync()) {
        row[key] = '';
        skippedPhotos[0]++;
      }
    }

    final paths = row['photoPaths'];
    if (paths is List) {
      final kept = <dynamic>[];
      for (final value in paths) {
        final path = _text(value);
        if (path.isNotEmpty &&
            _legacyPrivatePath(path) &&
            !File(path).existsSync()) {
          skippedPhotos[0]++;
          continue;
        }
        kept.add(value);
      }
      row['photoPaths'] = kept;
    }
    return row;
  }

  static List<String> _orders(Map<String, dynamic> row) {
    final out = <String>{};
    final one = _norm(row['orderNumber']);
    if (one.isNotEmpty) out.add(one);
    final many = row['orderNumbers'];
    if (many is List) {
      for (final value in many) {
        final n = _norm(value);
        if (n.isNotEmpty) out.add(n);
      }
    }
    return out.toList();
  }

  static int _uniqueIndex(
    List<Map<String, dynamic>> current,
    bool Function(Map<String, dynamic>) test,
  ) {
    var found = -1;
    for (var i = 0; i < current.length; i++) {
      if (!test(current[i])) continue;
      if (found >= 0) return -1;
      found = i;
    }
    return found;
  }

  static int _findMatch(
    String key,
    Map<String, dynamic> incoming,
    List<Map<String, dynamic>> current,
    Map<String, int> incomingNameCounts,
  ) {
    final importedId = _text(incoming['id']);
    if (importedId.isNotEmpty) {
      final i = current.indexWhere((row) => _text(row['id']) == importedId);
      if (i >= 0) return i;
    }

    final syncKeys = switch (key) {
      'clients' => const ['whatsbotClientSyncId'],
      'purchases' => const ['whatsbotSyncId', 'whatsbotRemoteId'],
      'packages' => const ['whatsbotPackageSyncId', 'whatsbotPackageRemoteId'],
      _ => const <String>[],
    };
    for (final syncKey in syncKeys) {
      final value = _norm(incoming[syncKey]);
      if (value.isEmpty) continue;
      final i = _uniqueIndex(
        current,
        (row) => _norm(row[syncKey]) == value,
      );
      if (i >= 0) return i;
    }

    if (key == 'packages') {
      final tracking = _norm(incoming['tracking']);
      if (tracking.isNotEmpty &&
          tracking != 'unknown' &&
          tracking != 'sintracking' &&
          tracking != 'na') {
        final i = _uniqueIndex(
          current,
          (row) => _norm(row['tracking']) == tracking,
        );
        if (i >= 0) return i;
      }
    }

    if (key == 'purchases') {
      final orders = _orders(incoming).toSet();
      if (orders.isNotEmpty) {
        final clientId = _text(incoming['clientId']);
        final i = _uniqueIndex(current, (row) {
          final sameClient = clientId.isEmpty || _text(row['clientId']) == clientId;
          if (!sameClient) return false;
          return _orders(row).any(orders.contains);
        });
        if (i >= 0) return i;
      }
    }

    if (key == 'clients') {
      final phone = _phone(incoming['phone']);
      if (phone.length >= 7) {
        final i = _uniqueIndex(current, (row) => _phone(row['phone']) == phone);
        if (i >= 0) return i;
      }
      final email = _text(incoming['email']).toLowerCase();
      if (email.contains('@')) {
        final i = _uniqueIndex(
          current,
          (row) => _text(row['email']).toLowerCase() == email,
        );
        if (i >= 0) return i;
      }
    }

    if (key == 'recipients') {
      final clientId = _text(incoming['clientId']);
      final phone = _phone(incoming['phone']);
      final name = _norm(incoming['name']);
      if (phone.length >= 7 || name.isNotEmpty) {
        final i = _uniqueIndex(current, (row) {
          if (clientId.isNotEmpty && _text(row['clientId']) != clientId) {
            return false;
          }
          if (phone.length >= 7 && _phone(row['phone']) == phone) return true;
          return name.isNotEmpty && _norm(row['name']) == name;
        });
        if (i >= 0) return i;
      }
    }

    if (key == 'clients' || key == 'agents') {
      final name = _norm(incoming['name']);
      if (name.length >= 3 && incomingNameCounts[name] == 1) {
        final i = _uniqueIndex(current, (row) => _norm(row['name']) == name);
        if (i >= 0) return i;
      }
    }

    return -1;
  }

  static dynamic _remapValue(dynamic value, Map<String, String> idMap) {
    if (value == null) return value;
    final text = '$value';
    return idMap[text] ?? value;
  }

  static Map<String, dynamic> _remapReferences(
    Map<String, dynamic> source,
    Map<String, Map<String, String>> idMaps,
    List<int> remapped,
  ) {
    dynamic walk(dynamic value, [String? field]) {
      if (value is Map) {
        final out = <String, dynamic>{};
        for (final entry in value.entries) {
          final key = '${entry.key}';
          if (key == 'id') {
            out[key] = entry.value;
            continue;
          }
          const singleRefs = {
            'clientId': 'clients',
            'recipientId': 'recipients',
            'purchaseId': 'purchases',
            'packageId': 'packages',
            'agentId': 'agents',
          };
          const listRefs = {
            'clientIds': 'clients',
            'recipientIds': 'recipients',
            'purchaseIds': 'purchases',
            'packageIds': 'packages',
            'agentIds': 'agents',
          };
          if (singleRefs.containsKey(key)) {
            final map = idMaps[singleRefs[key]] ?? const <String, String>{};
            final before = entry.value;
            final after = _remapValue(before, map);
            if ('$before' != '$after') remapped[0]++;
            out[key] = after;
          } else if (listRefs.containsKey(key) && entry.value is List) {
            final map = idMaps[listRefs[key]] ?? const <String, String>{};
            out[key] = (entry.value as List).map((item) {
              final after = _remapValue(item, map);
              if ('$item' != '$after') remapped[0]++;
              return after;
            }).toList();
          } else {
            out[key] = walk(entry.value, key);
          }
        }
        return out;
      }
      if (value is List) return value.map((item) => walk(item, field)).toList();
      return value;
    }

    return Map<String, dynamic>.from(walk(source) as Map);
  }

  static Future<MigrationMergePlan> preview(Map<String, dynamic> migration) async {
    final schema = _text(migration['schema']);
    if (schema != 'alas-cargo-finance-sync-v1') {
      throw Exception(
        'Este JSON no es un archivo de Paquetería Migrador compatible. '
        'Esquema recibido: ${schema.isEmpty ? 'desconocido' : schema}.',
      );
    }

    final prefs = await SharedPreferences.getInstance();
    final output = <String, List<Map<String, dynamic>>>{};
    final stats = <MigrationMergeStats>[];
    final idMaps = <String, Map<String, String>>{};
    final skippedPhotos = [0];
    final remapped = [0];

    for (final key in _mergeOrder) {
      final current = _decodeStoredList(prefs, key);
      final rawIncoming = migration[key];
      final incoming = rawIncoming is List
          ? rawIncoming
              .whereType<Map>()
              .map((e) => _sanitizeImportedRecord(
                    Map<String, dynamic>.from(e),
                    skippedPhotos,
                  ))
              .toList()
          : <Map<String, dynamic>>[];

      final nameCounts = <String, int>{};
      for (final row in incoming) {
        final name = _norm(row['name']);
        if (name.isNotEmpty) nameCounts[name] = (nameCounts[name] ?? 0) + 1;
      }

      final merged = current.map((e) => Map<String, dynamic>.from(e)).toList();
      final mapForEntity = <String, String>{};
      idMaps[key] = mapForEntity;
      var added = 0;
      var enriched = 0;
      var duplicates = 0;
      var unchanged = 0;

      for (final originalIncoming in incoming) {
        final importedId = _text(originalIncoming['id']);
        var row = _remapReferences(originalIncoming, idMaps, remapped);
        var match = _findMatch(key, row, merged, nameCounts);

        if (match >= 0) {
          duplicates++;
          final existingId = _text(merged[match]['id']);
          if (importedId.isNotEmpty && existingId.isNotEmpty) {
            mapForEntity[importedId] = existingId;
          }
          final before = jsonEncode(merged[match]);
          final after = _deepFill(merged[match], row);
          // Never let a semantically matched imported row replace the local ID.
          if (existingId.isNotEmpty) after['id'] = existingId;
          merged[match] = after;
          if (jsonEncode(after) == before) {
            unchanged++;
          } else {
            enriched++;
          }
        } else {
          row = Map<String, dynamic>.from(row);
          var finalId = _text(row['id']);
          if (finalId.isEmpty || merged.any((e) => _text(e['id']) == finalId)) {
            finalId = _freshId();
            row['id'] = finalId;
          }
          if (importedId.isNotEmpty) mapForEntity[importedId] = finalId;
          merged.add(row);
          added++;
        }
      }

      output[key] = merged;
      stats.add(MigrationMergeStats(
        key: key,
        label: _labels[key] ?? key,
        current: current.length,
        incoming: incoming.length,
        added: added,
        enriched: enriched,
        duplicatesAvoided: duplicates,
        unchanged: unchanged,
      ));
    }

    final currentSettings = _decodeStoredSettings(prefs);
    final importedSettings = migration['settings'] is Map
        ? Map<String, dynamic>.from(migration['settings'] as Map)
        : <String, dynamic>{};
    final settings = _deepFill(currentSettings, importedSettings);

    return MigrationMergePlan(
      generatedAt: _text(migration['generatedAt']),
      lists: output,
      settings: settings,
      stats: stats,
      skippedLegacyPhotoRefs: skippedPhotos[0],
      remappedReferences: remapped[0],
    );
  }

  static Future<void> apply(MigrationMergePlan plan) async {
    final prefs = await SharedPreferences.getInstance();

    // This operation is intentionally additive/fill-only. It does not clear
    // SharedPreferences, does not delete rows and does not replace populated
    // local fields with migration values.
    for (final entry in plan.lists.entries) {
      await prefs.setString(entry.key, jsonEncode(entry.value));
    }
    await prefs.setString('settings', jsonEncode(plan.settings));
    await prefs.setString(
      'migration_merge_last_at',
      DateTime.now().toIso8601String(),
    );
    await prefs.setString(
      'migration_merge_last_summary',
      jsonEncode({
        'added': plan.totalAdded,
        'enriched': plan.totalEnriched,
        'duplicatesAvoided': plan.totalDuplicates,
        'remappedReferences': plan.remappedReferences,
        'skippedLegacyPhotoRefs': plan.skippedLegacyPhotoRefs,
      }),
    );
  }
}

class MigrationMergePage extends StatefulWidget {
  const MigrationMergePage({super.key});

  @override
  State<MigrationMergePage> createState() => _MigrationMergePageState();
}

class _MigrationMergePageState extends State<MigrationMergePage> {
  bool working = false;
  String fileName = '';
  String error = '';
  MigrationMergePlan? plan;

  Future<void> _pick() async {
    setState(() {
      working = true;
      error = '';
      plan = null;
      fileName = '';
    });
    try {
      final result = await FilePicker.platform.pickFiles(
        dialogTitle: 'Selecciona el JSON de Paquetería Migrador',
        type: FileType.custom,
        allowedExtensions: const ['json'],
        allowMultiple: false,
        withData: true,
      );
      if (result == null || result.files.isEmpty) return;
      final picked = result.files.single;
      String raw;
      if (picked.bytes != null && picked.bytes!.isNotEmpty) {
        raw = utf8.decode(picked.bytes!);
      } else if (picked.path != null && picked.path!.isNotEmpty) {
        raw = await File(picked.path!).readAsString();
      } else {
        throw Exception('No pude leer el JSON seleccionado.');
      }
      final decoded = jsonDecode(raw);
      if (decoded is! Map) throw Exception('El archivo JSON no contiene un objeto válido.');
      final preview = await PaqueteriaMigrationMergeService.preview(
        Map<String, dynamic>.from(decoded),
      );
      if (!mounted) return;
      setState(() {
        fileName = picked.name;
        plan = preview;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => error = '$e'.replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => working = false);
    }
  }

  Future<void> _apply() async {
    final currentPlan = plan;
    if (currentPlan == null || working) return;
    final yes = await showDialog<bool>(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('Combinar datos del Migrador'),
            content: Text(
              'Se añadirán ${currentPlan.totalAdded} registros que faltan y se '
              'rellenarán ${currentPlan.totalEnriched} registros existentes con '
              'campos vacíos.\n\n'
              'No se borrará ningún registro actual y los campos que ya tienen '
              'información en este teléfono tienen prioridad sobre el JSON. '
              'Se evitaron ${currentPlan.totalDuplicates} posibles réplicas en la vista previa.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Cancelar'),
              ),
              FilledButton.icon(
                onPressed: () => Navigator.pop(context, true),
                icon: const Icon(Icons.merge_type),
                label: const Text('Combinar y recuperar'),
              ),
            ],
          ),
        ) ??
        false;
    if (!yes) return;

    setState(() => working = true);
    try {
      await PaqueteriaMigrationMergeService.apply(currentPlan);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Datos recuperados'),
          content: Text(
            'Se añadieron ${currentPlan.totalAdded} registros y '
            'se completaron ${currentPlan.totalEnriched}. '
            'No se borraron los datos que ya tenías.\n\n'
            '${currentPlan.totalDuplicates} coincidencias se combinaron sin crear duplicados.',
          ),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Listo'),
            ),
          ],
        ),
      );
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No pude combinar los datos: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => working = false);
    }
  }

  Widget _summaryCard(MigrationMergePlan p) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Vista previa segura',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 17),
            ),
            const SizedBox(height: 8),
            Text('Archivo: $fileName'),
            if (p.generatedAt.isNotEmpty) Text('Generado: ${p.generatedAt}'),
            const SizedBox(height: 10),
            Text('Nuevos que se recuperarán: ${p.totalAdded}'),
            Text('Existentes que se completarán: ${p.totalEnriched}'),
            Text('Réplicas evitadas: ${p.totalDuplicates}'),
            if (p.remappedReferences > 0)
              Text('Referencias internas corregidas: ${p.remappedReferences}'),
            if (p.skippedLegacyPhotoRefs > 0) ...[
              const SizedBox(height: 8),
              Text(
                '${p.skippedLegacyPhotoRefs} referencia(s) de fotos antiguas no '
                'existen ya en el teléfono y no se importarán como imágenes rotas.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final p = plan;
    return Scaffold(
      appBar: AppBar(title: const Text('Recuperar JSON del Migrador')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Card(
            child: Padding(
              padding: EdgeInsets.all(14),
              child: Text(
                'Esta recuperación COMBINA el JSON con lo que ya tienes. '
                'No vacía la aplicación. Primero busca coincidencias por ID, '
                'sincronización, tracking, número de orden, teléfono/correo y '
                'otras claves seguras. Si encuentra el mismo registro, conserva '
                'los datos actuales y solo rellena campos que estén vacíos.',
              ),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: working ? null : _pick,
            icon: const Icon(Icons.data_object),
            label: Text(working ? 'Analizando…' : 'Seleccionar JSON de Paquetería Migrador'),
          ),
          if (error.isNotEmpty) ...[
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Text(error),
              ),
            ),
          ],
          if (p != null) ...[
            const SizedBox(height: 12),
            _summaryCard(p),
            const SizedBox(height: 12),
            for (final row in p.stats)
              if (row.incoming > 0)
                ListTile(
                  dense: true,
                  title: Text(row.label),
                  subtitle: Text(
                    '${row.incoming} en JSON · ${row.added} nuevos · '
                    '${row.enriched} completados · '
                    '${row.duplicatesAvoided} coincidencias',
                  ),
                ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: working ? null : _apply,
              icon: const Icon(Icons.merge_type),
              label: const Text('Combinar y recuperar datos'),
            ),
          ],
        ],
      ),
    );
  }
}
'''

Path('app/lib/migration_merge.dart').write_text(migration)

backup = Path('app/lib/backup_service.dart')
s = backup.read_text()

if "import 'migration_merge.dart';" not in s:
    anchor = "import 'package:shared_preferences/shared_preferences.dart';\n"
    if anchor not in s:
        raise SystemExit('shared_preferences import not found in backup_service.dart')
    s = s.replace(anchor, anchor + "import 'migration_merge.dart';\n", 1)

button_anchor = """                  OutlinedButton.icon(
                    onPressed: working ? null : _importFromFile,
                    icon: const Icon(Icons.file_open_outlined),
                    label: const Text('Importar copia desde archivo (incluye copias grandes)'),
                  ),
                  const SizedBox(height: 10),
"""
button_replacement = button_anchor + """                  OutlinedButton.icon(
                    onPressed: working
                        ? null
                        : () => Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (_) => const MigrationMergePage(),
                              ),
                            ),
                    icon: const Icon(Icons.merge_type),
                    label: const Text('Recuperar datos desde JSON de Paquetería Migrador'),
                  ),
                  const SizedBox(height: 10),
"""
if 'Recuperar datos desde JSON de Paquetería Migrador' not in s:
    if button_anchor not in s:
        raise SystemExit('backup import button anchor not found')
    s = s.replace(button_anchor, button_replacement, 1)

backup.write_text(s)
print('Safe Paqueteria Migrador JSON merge recovery added.')
