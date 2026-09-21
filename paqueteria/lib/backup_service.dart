import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class PaqueteriaBackupBridge {
  static const _channel = MethodChannel('com.angelapps.paqueteria/backups');

  static Future<Map<String, dynamic>> write({
    required String fileName,
    required Uint8List bytes,
    bool overwrite = false,
  }) async {
    final raw = await _channel.invokeMethod<Map<dynamic, dynamic>>(
      'writeBackup',
      {'fileName': fileName, 'bytes': bytes, 'overwrite': overwrite},
    );
    return Map<String, dynamic>.from(raw ?? const {});
  }

  static Future<List<Map<String, dynamic>>> list() async {
    final raw = await _channel.invokeMethod<List<dynamic>>('listBackups');
    return (raw ?? const [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
  }

  static Future<Uint8List> read(String uri) async {
    return await _channel.invokeMethod<Uint8List>(
          'readBackup',
          {'uri': uri},
        ) ??
        Uint8List(0);
  }
}

class PaqueteriaBackupService {
  static const _enabledKey = 'paqueteria_auto_backup_enabled';
  static const _lastKey = 'paqueteria_last_auto_backup_at';

  static bool _sensitive(String key) {
    final k = key.toLowerCase();
    return k.contains('api_key') ||
        k.contains('apikey') ||
        k.contains('password') ||
        k.contains('secret') ||
        k.contains('token');
  }

  static Future<Uint8List> buildBackup() async {
    final archive = Archive();
    final prefs = await SharedPreferences.getInstance();
    final prefMap = <String, dynamic>{};
    final excluded = <String>[];
    for (final key in prefs.getKeys()) {
      if (_sensitive(key)) {
        excluded.add(key);
        continue;
      }
      final value = prefs.get(key);
      if (value is String ||
          value is bool ||
          value is int ||
          value is double ||
          value is List<String>) {
        prefMap[key] = value;
      }
    }

    final meta = utf8.encode(jsonEncode({
      'format': 'PaqueteriaBackup',
      'formatVersion': 1,
      'createdAt': DateTime.now().toIso8601String(),
      'secureCredentialsIncluded': false,
      'excludedPreferences': excluded,
    }));
    archive.addFile(ArchiveFile('meta/backup.json', meta.length, meta));

    final prefBytes = utf8.encode(jsonEncode(prefMap));
    archive.addFile(
      ArchiveFile('meta/preferences.json', prefBytes.length, prefBytes),
    );

    Future<void> addDir(Directory root, String prefix) async {
      if (!await root.exists()) return;
      final base = root.path.endsWith(Platform.pathSeparator)
          ? root.path
          : root.path + Platform.pathSeparator;
      await for (final entity in root.list(recursive: true, followLinks: false)) {
        if (entity is! File || !entity.path.startsWith(base)) continue;
        final rel = entity.path.substring(base.length).replaceAll('\\', '/');
        if (rel.isEmpty) continue;
        final bytes = await entity.readAsBytes();
        archive.addFile(ArchiveFile('$prefix/$rel', bytes.length, bytes));
      }
    }

    final docs = await getApplicationDocumentsDirectory();
    final support = await getApplicationSupportDirectory();
    await addDir(docs, 'documents');
    if (support.path != docs.path) await addDir(support, 'support');

    final encoded = ZipEncoder().encode(archive);
    if (encoded == null) throw Exception('No pude crear la copia ZIP.');
    return Uint8List.fromList(encoded);
  }

  static Future<Map<String, dynamic>> createManual() async {
    final bytes = await buildBackup();
    final now = DateTime.now();
    String p(int n) => n.toString().padLeft(2, '0');
    return PaqueteriaBackupBridge.write(
      fileName:
          'Paqueteria-Backup-${now.year}${p(now.month)}${p(now.day)}-'
          '${p(now.hour)}${p(now.minute)}${p(now.second)}.zip',
      bytes: bytes,
    );
  }

  static Future<void> autoBackupIfDue() async {
    final prefs = await SharedPreferences.getInstance();
    if (!(prefs.getBool(_enabledKey) ?? true)) return;
    final last = DateTime.tryParse(prefs.getString(_lastKey) ?? '');
    final now = DateTime.now();
    if (last != null && now.difference(last) < const Duration(hours: 24)) {
      return;
    }
    final bytes = await buildBackup();
    await PaqueteriaBackupBridge.write(
      fileName: 'Paqueteria-AutoBackup.zip',
      bytes: bytes,
      overwrite: true,
    );
    await prefs.setString(_lastKey, now.toIso8601String());
  }

  static Future<bool> autoEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_enabledKey) ?? true;
  }

  static Future<void> setAutoEnabled(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_enabledKey, value);
  }

  static Future<void> restore(String uri) async {
    final bytes = await PaqueteriaBackupBridge.read(uri);
    if (bytes.isEmpty) throw Exception('La copia está vacía.');
    final archive = ZipDecoder().decodeBytes(bytes);

    ArchiveFile? meta;
    ArchiveFile? prefsFile;
    for (final file in archive.files) {
      if (file.name == 'meta/backup.json') meta = file;
      if (file.name == 'meta/preferences.json') prefsFile = file;
    }
    if (meta == null || prefsFile == null) {
      throw Exception('No es una copia válida de Paquetería.');
    }
    final decodedMeta = jsonDecode(utf8.decode(meta.content as List<int>));
    if (decodedMeta is! Map ||
        decodedMeta['format'] != 'PaqueteriaBackup') {
      throw Exception('Formato de copia no compatible.');
    }

    final docs = await getApplicationDocumentsDirectory();
    final support = await getApplicationSupportDirectory();

    Future<void> clear(Directory root) async {
      if (!await root.exists()) return;
      for (final e in await root.list(followLinks: false).toList()) {
        await e.delete(recursive: true);
      }
    }

    await clear(docs);
    if (support.path != docs.path) await clear(support);

    for (final file in archive.files) {
      if (!file.isFile) continue;
      Directory? root;
      String? rel;
      if (file.name.startsWith('documents/')) {
        root = docs;
        rel = file.name.substring('documents/'.length);
      } else if (file.name.startsWith('support/')) {
        root = support;
        rel = file.name.substring('support/'.length);
      }
      if (root == null || rel == null || rel.isEmpty || rel.contains('..')) {
        continue;
      }
      final out = File(
        root.path +
            Platform.pathSeparator +
            rel.replaceAll('/', Platform.pathSeparator),
      );
      await out.parent.create(recursive: true);
      await out.writeAsBytes(List<int>.from(file.content as List), flush: true);
    }

    final prefData =
        jsonDecode(utf8.decode(prefsFile.content as List<int>));
    if (prefData is Map) {
      final prefs = await SharedPreferences.getInstance();
      final auto = prefs.getBool(_enabledKey) ?? true;
      await prefs.clear();
      for (final e in prefData.entries) {
        final key = e.key.toString();
        if (_sensitive(key)) continue;
        final value = e.value;
        if (value is String) {
          await prefs.setString(key, value);
        } else if (value is bool) {
          await prefs.setBool(key, value);
        } else if (value is int) {
          await prefs.setInt(key, value);
        } else if (value is double) {
          await prefs.setDouble(key, value);
        } else if (value is List) {
          await prefs.setStringList(
            key,
            value.map((x) => x.toString()).toList(),
          );
        }
      }
      if (!prefs.containsKey(_enabledKey)) {
        await prefs.setBool(_enabledKey, auto);
      }
    }
  }
}

class PaqueteriaBackupPage extends StatefulWidget {
  const PaqueteriaBackupPage({super.key});

  @override
  State<PaqueteriaBackupPage> createState() => _PaqueteriaBackupPageState();
}

class _PaqueteriaBackupPageState extends State<PaqueteriaBackupPage> {
  bool loading = true;
  bool working = false;
  bool autoEnabled = true;
  List<Map<String, dynamic>> backups = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final enabled = await PaqueteriaBackupService.autoEnabled();
    final list = await PaqueteriaBackupBridge.list();
    if (!mounted) return;
    setState(() {
      autoEnabled = enabled;
      backups = list;
      loading = false;
    });
  }

  Future<void> _create() async {
    setState(() => working = true);
    try {
      final result = await PaqueteriaBackupService.createManual();
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Copia creada en Descargas/Paqueteria: ' +
                (result['name']?.toString() ?? 'backup'),
          ),
        ),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No pude crear la copia: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => working = false);
    }
  }

  Future<void> _restore(Map<String, dynamic> item) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Restaurar copia'),
        content: Text(
          'Se reemplazarán los datos actuales por "' +
              (item['name']?.toString() ?? 'backup') +
              '".',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Restaurar'),
          ),
        ],
      ),
    );
    if (ok != true) return;

    setState(() => working = true);
    try {
      await PaqueteriaBackupService.restore(item['uri']?.toString() ?? '');
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Copia restaurada'),
          content: const Text(
            'Cierra y vuelve a abrir Paquetería para cargar todos los datos restaurados.',
          ),
          actions: [
            FilledButton(
              onPressed: () {
                Navigator.pop(dialogContext);
                SystemNavigator.pop();
              },
              child: const Text('Cerrar Paquetería'),
            ),
          ],
        ),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No pude restaurar la copia: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => working = false);
    }
  }

  String _date(Map<String, dynamic> item) {
    final ms = (item['modifiedMs'] as num?)?.toInt();
    if (ms == null || ms <= 0) return '';
    final d = DateTime.fromMillisecondsSinceEpoch(ms);
    String p(int n) => n.toString().padLeft(2, '0');
    return '${d.year}-${p(d.month)}-${p(d.day)} '
        '${p(d.hour)}:${p(d.minute)}';
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Copias de seguridad')),
        body: loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Copia automática diaria'),
                    subtitle: const Text(
                      'Se guarda en Descargas/Paqueteria y sobrevive a una desinstalación.',
                    ),
                    value: autoEnabled,
                    onChanged: working
                        ? null
                        : (value) async {
                            await PaqueteriaBackupService.setAutoEnabled(value);
                            if (mounted) setState(() => autoEnabled = value);
                          },
                  ),
                  FilledButton.icon(
                    onPressed: working ? null : _create,
                    icon: const Icon(Icons.backup_outlined),
                    label:
                        Text(working ? 'Procesando…' : 'Crear copia ahora'),
                  ),
                  const SizedBox(height: 10),
                  const Text(
                    'Incluye clientes, pedidos, paquetes, fotos, tickets, '
                    'agentes, remesas, viajes y configuraciones. No incluye '
                    'credenciales seguras/API keys.',
                  ),
                  const Divider(height: 28),
                  if (backups.isEmpty)
                    const Text('Todavía no hay copias guardadas.'),
                  for (final item in backups)
                    Card(
                      child: ListTile(
                        leading: const Icon(Icons.restore_outlined),
                        title: Text(item['name']?.toString() ?? 'Backup'),
                        subtitle: Text(_date(item)),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: working ? null : () => _restore(item),
                      ),
                    ),
                ],
              ),
      );
}
