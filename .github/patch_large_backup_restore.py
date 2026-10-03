from pathlib import Path

backup = Path('app/lib/backup_service.dart')
s = backup.read_text()

# Bridge helper: materialize a MediaStore/content URI into a temporary file so
# large backups never cross the Flutter MethodChannel as one giant byte array.
old_bridge = """  static Future<Uint8List> read(String uri) async {
    return await _channel.invokeMethod<Uint8List>(
          'readBackup',
          {'uri': uri},
        ) ??
        Uint8List(0);
  }
"""
new_bridge = old_bridge + """
  static Future<String> materialize(String uri) async {
    return await _channel.invokeMethod<String>(
          'materializeBackup',
          {'uri': uri},
        ) ??
        '';
  }
"""
if "static Future<String> materialize(" not in s:
    if old_bridge not in s:
        raise SystemExit('PaqueteriaBackupBridge.read block not found')
    s = s.replace(old_bridge, new_bridge, 1)

# Large-file restore path. InputFileStream + OutputFileStream keep the ZIP and
# extracted photos/documents off the Dart heap instead of loading everything
# into RAM at once.
marker = "  static Future<void> restoreBytes(Uint8List bytes) async {"
stream_restore = r'''  static Future<void> restoreFile(String path) async {
    final source = File(path);
    if (!await source.exists() || await source.length() == 0) {
      throw Exception('La copia está vacía.');
    }

    final input = InputFileStream(path);
    try {
      Archive archive;
      try {
        archive = ZipDecoder().decodeStream(input);
      } catch (_) {
        throw Exception('El archivo seleccionado no es un ZIP válido.');
      }

      ArchiveFile? meta;
      ArchiveFile? prefsFile;
      for (final file in archive.files) {
        if (file.name == 'meta/backup.json') meta = file;
        if (file.name == 'meta/preferences.json') prefsFile = file;
      }
      if (meta == null || prefsFile == null) {
        throw Exception('No es una copia válida de Paquetería.');
      }

      final metaBytes = meta.readBytes();
      final prefBytes = prefsFile.readBytes();
      if (metaBytes == null || prefBytes == null) {
        throw Exception('No pude leer los metadatos de la copia.');
      }
      final decodedMeta = jsonDecode(utf8.decode(metaBytes));
      if (decodedMeta is! Map || decodedMeta['format'] != 'PaqueteriaBackup') {
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
        final output = OutputFileStream(out.path);
        try {
          file.writeContent(output);
        } finally {
          output.closeSync();
        }
      }

      final prefData = jsonDecode(utf8.decode(prefBytes));
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
    } finally {
      input.closeSync();
    }
  }

'''
if 'static Future<void> restoreFile(String path)' not in s:
    if marker not in s:
        raise SystemExit('restoreBytes marker not found')
    s = s.replace(marker, stream_restore + marker, 1)

old_restore = """  static Future<void> restore(String uri) async {
    final bytes = await PaqueteriaBackupBridge.read(uri);
    await restoreBytes(bytes);
  }
"""
new_restore = """  static Future<void> restore(String uri) async {
    final path = await PaqueteriaBackupBridge.materialize(uri);
    if (path.isEmpty) throw Exception('No pude preparar la copia para restaurarla.');
    try {
      await restoreFile(path);
    } finally {
      try {
        final f = File(path);
        if (await f.exists()) await f.delete();
      } catch (_) {}
    }
  }
"""
if old_restore in s:
    s = s.replace(old_restore, new_restore, 1)
elif new_restore not in s:
    raise SystemExit('restore(String uri) block not found')

s = s.replace('        withData: true,', '        withData: false,', 1)
old_import = """      Uint8List bytes;
      if (picked.bytes != null && picked.bytes!.isNotEmpty) {
        bytes = picked.bytes!;
      } else if (picked.path != null && picked.path!.isNotEmpty) {
        bytes = await File(picked.path!).readAsBytes();
      } else {
        throw Exception('No pude leer el archivo seleccionado.');
      }

      await PaqueteriaBackupService.restoreBytes(bytes);
"""
new_import = """      final path = picked.path;
      if (path == null || path.isEmpty) {
        throw Exception('Android no pudo preparar el archivo seleccionado.');
      }
      await PaqueteriaBackupService.restoreFile(path);
"""
if old_import in s:
    s = s.replace(old_import, new_import, 1)
elif new_import not in s:
    raise SystemExit('large-file picker restore block not found')

# Tell the user explicitly that large backups are supported.
s = s.replace(
    "label: const Text('Importar copia desde archivo'),",
    "label: const Text('Importar copia desde archivo (incluye copias grandes)'),",
    1,
)
backup.write_text(s)

# Patch the Android storage bridge so restoring a backup already listed under
# Descargas/Paqueteria also streams to a temporary file instead of readBytes().
bridge = Path('app/android/app/src/main/kotlin/com/angelapps/paqueteria/PaqueteriaBackupStorageBridge.kt')
k = bridge.read_text()
old_when = '''                    "readBackup" -> {
                        val uri = call.argument<String>("uri") ?: ""
                        result.success(read(context, uri))
                    }
'''
new_when = old_when + '''                    "materializeBackup" -> {
                        val uri = call.argument<String>("uri") ?: ""
                        result.success(materialize(context, uri))
                    }
'''
if '"materializeBackup"' not in k:
    if old_when not in k:
        raise SystemExit('Android readBackup handler not found')
    k = k.replace(old_when, new_when, 1)

materialize_fn = r'''
    private fun materialize(context: Context, rawUri: String): String {
        val uri = Uri.parse(rawUri)
        val temp = File(context.cacheDir, "paqueteria-restore-${System.currentTimeMillis()}.zip")
        val input = if (uri.scheme == "content") {
            context.contentResolver.openInputStream(uri)
                ?: throw IllegalStateException("No pude abrir la copia.")
        } else {
            File(uri.path ?: throw IllegalArgumentException("Ruta inválida.")).inputStream()
        }
        input.use { source ->
            temp.outputStream().buffered(1024 * 1024).use { target ->
                source.copyTo(target, 1024 * 1024)
                target.flush()
            }
        }
        if (!temp.exists() || temp.length() <= 0L) {
            throw IllegalStateException("La copia seleccionada está vacía.")
        }
        return temp.absolutePath
    }
'''
if 'private fun materialize(context: Context' not in k:
    insert_at = k.rfind('\n}')
    if insert_at < 0:
        raise SystemExit('Android bridge closing brace not found')
    k = k[:insert_at] + materialize_fn + k[insert_at:]
bridge.write_text(k)
