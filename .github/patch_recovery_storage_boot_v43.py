from pathlib import Path

native = Path('app/android/app/src/main/kotlin/com/angelapps/paqueteria/PaqueteriaLocalStoreBridge.kt')
native.parent.mkdir(parents=True, exist_ok=True)
native.write_text(r'''package com.angelapps.paqueteria

import android.content.Context
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel
import java.util.UUID

// Uses the existing legacy SharedPreferences file without migration.
// Avoids transporting *all* user data over Android IPC on startup.
object PaqueteriaLocalStoreBridge {
    private const val CHANNEL = "com.angelapps.paqueteria/local_store"
    private const val NAME = "FlutterSharedPreferences"
    private const val SIZE = 48000
    private data class PendingWrite(val key: String, val expected: Int, val text: StringBuilder)
    private val pendingWrites = mutableMapOf<String, PendingWrite>()

    fun register(context: Context, messenger: BinaryMessenger) {
        val prefs = context.getSharedPreferences(NAME, Context.MODE_PRIVATE)
        MethodChannel(messenger, CHANNEL).setMethodCallHandler { call, result ->
            try {
                when (call.method) {
                    "readChunk" -> {
                        val key = call.argument<String>("key") ?: ""
                        val offset = call.argument<Int>("offset") ?: 0
                        val value = if (key.startsWith("flutter.")) prefs.getString(key, null) else null
                        if (value == null) {
                            result.success(mapOf("exists" to false))
                        } else if (offset < 0 || offset > value.length) {
                            result.error("INVALID_OFFSET", "Invalid read offset.", null)
                        } else {
                            var end = minOf(offset + SIZE, value.length)
                            if (end < value.length && end > offset &&
                                Character.isHighSurrogate(value[end - 1]) &&
                                Character.isLowSurrogate(value[end])) {
                                end--
                            }
                            result.success(mapOf(
                                "exists" to true,
                                "chunk" to value.substring(offset, end),
                                "next" to end,
                                "total" to value.length
                            ))
                        }
                    }
                    "writeString" -> {
                        val key = call.argument<String>("key") ?: ""
                        val value = call.argument<String>("value")
                        if (!key.startsWith("flutter.") || value == null) {
                            result.error("INVALID_WRITE", "Invalid preference key.", null)
                        } else if (prefs.edit().putString(key, value).commit()) {
                            result.success(true)
                        } else {
                            result.error("WRITE_FAILED", "Could not persist local data.", null)
                        }
                    }
                    "startWrite" -> {
                        val key = call.argument<String>("key") ?: ""
                        val length = call.argument<Int>("length") ?: -1
                        if (!key.startsWith("flutter.") || length < 0 || length > 50000000) {
                            result.error("INVALID_WRITE", "Invalid write length.", null)
                        } else {
                            val handle = UUID.randomUUID().toString()
                            pendingWrites[handle] = PendingWrite(key, length, StringBuilder())
                            result.success(handle)
                        }
                    }
                    "appendWrite" -> {
                        val handle = call.argument<String>("handle") ?: ""
                        val chunk = call.argument<String>("chunk") ?: ""
                        val write = pendingWrites[handle]
                        if (write == null || chunk.length > SIZE ||
                            write.text.length + chunk.length > write.expected) {
                            result.error("INVALID_CHUNK", "Invalid write chunk.", null)
                        } else {
                            write.text.append(chunk)
                            result.success(true)
                        }
                    }
                    "finishWrite" -> {
                        val handle = call.argument<String>("handle") ?: ""
                        val write = pendingWrites.remove(handle)
                        if (write == null || write.text.length != write.expected) {
                            result.error("INCOMPLETE_WRITE", "Write was incomplete.", null)
                        } else if (prefs.edit().putString(write.key, write.text.toString()).commit()) {
                            result.success(true)
                        } else {
                            result.error("WRITE_FAILED", "Could not persist local data.", null)
                        }
                    }
                    "abortWrite" -> {
                        pendingWrites.remove(call.argument<String>("handle") ?: "")
                        result.success(true)
                    }
                    else -> result.notImplemented()
                }
            } catch (e: Exception) {
                result.error("LOCAL_STORE", e.javaClass.simpleName, null)
            }
        }
    }
}
''')

p = Path('app/android/app/src/main/kotlin/com/angelapps/paqueteria/MainActivity.kt')
s = p.read_text()
anchor = '''        PaqueteriaBackupStorageBridge.register(
            applicationContext,
            flutterEngine.dartExecutor.binaryMessenger
        )'''
if s.count(anchor) != 1: raise SystemExit('v38: MainActivity native registration mismatch')
s = s.replace(anchor, anchor + '''
        PaqueteriaLocalStoreBridge.register(
            applicationContext,
            flutterEngine.dartExecutor.binaryMessenger
        )''')
p.write_text(s)

p = Path('app/lib/main.dart')
s = p.read_text()
anchor = "import 'package:flutter/material.dart';"
if s.count(anchor) != 1: raise SystemExit('v38: Flutter imports mismatch')
s = s.replace(anchor, anchor + "\nimport 'package:flutter/services.dart';")
start = s.index('  static Future<List<Map<String, dynamic>>> list(', s.index('class Store {'))
end = s.index('  static void clearListCache(', start)
s = s[:start] + r'''  static const MethodChannel _perKeyStore =
      MethodChannel('com.angelapps.paqueteria/local_store');

  static Future<String?> _readRaw(String key) async {
    if (Platform.isAndroid) {
      try {
        var offset = 0;
        final buffer = StringBuffer();
        while (true) {
          final part = await _perKeyStore.invokeMapMethod<String, dynamic>(
            'readChunk', {'key': 'flutter.$key', 'offset': offset},
          ).timeout(const Duration(seconds: 15));
          if (part == null || part['exists'] != true) return null;
          final total = (part['total'] as num?)?.toInt() ?? -1;
          final next = (part['next'] as num?)?.toInt() ?? -1;
          if (next < offset || next > total || (next == offset && next < total)) {
            throw StateError('La lectura de $key quedó incompleta.');
          }
          buffer.write(part['chunk'] as String? ?? '');
          if (next == total) return buffer.toString();
          offset = next;
        }
      } on MissingPluginException {
        // Background FlutterEngines without the Activity bridge use legacy API.
      }
    }
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(key);
  }

  static Future<void> _writeRaw(String key, String value) async {
    if (Platform.isAndroid) {
      try {
        if (value.length <= 48000) {
          final success = await _perKeyStore.invokeMethod<bool>(
            'writeString', {'key': 'flutter.$key', 'value': value},
          ).timeout(const Duration(seconds: 30));
          if (success != true) throw StateError('No se pudo guardar $key.');
          return;
        }
        final handle = await _perKeyStore.invokeMethod<String>(
          'startWrite', {'key': 'flutter.$key', 'length': value.length},
        ).timeout(const Duration(seconds: 15));
        if (handle == null) throw StateError('No se pudo iniciar el guardado de $key.');
        try {
          var offset = 0;
          while (offset < value.length) {
            var end = (offset + 48000).clamp(0, value.length);
            // Do not split a UTF-16 surrogate pair between channel messages.
            if (end < value.length && end > offset) {
              final before = value.codeUnitAt(end - 1);
              final after = value.codeUnitAt(end);
              if (before >= 0xD800 && before <= 0xDBFF &&
                  after >= 0xDC00 && after <= 0xDFFF) end--;
            }
            await _perKeyStore.invokeMethod<bool>('appendWrite',
              {'handle': handle, 'chunk': value.substring(offset, end)},
            ).timeout(const Duration(seconds: 15));
            offset = end;
          }
          final saved = await _perKeyStore.invokeMethod<bool>(
            'finishWrite', {'handle': handle},
          ).timeout(const Duration(seconds: 45));
          if (saved != true) throw StateError('No se pudo terminar el guardado de $key.');
          return;
        } finally {
          try {
            await _perKeyStore.invokeMethod<bool>('abortWrite', {'handle': handle});
          } catch (_) {}
        }
      } on MissingPluginException {
        // Flutter background workers still use the existing legacy storage.
      }
    }
    final prefs = await SharedPreferences.getInstance();
    if (!await prefs.setString(key, value)) {
      throw StateError('No se pudo guardar $key.');
    }
  }

  static Future<List<Map<String, dynamic>>> list(
    String key, {bool forceRefresh = false}
  ) async {
    if (!forceRefresh) {
      final cached = _listCache[key];
      if (cached != null) return _copyRows(cached);
    }
    final raw = await _readRaw(key);
    if (raw == null || raw.isEmpty) {
      _listCache[key] = <Map<String, dynamic>>[];
      return <Map<String, dynamic>>[];
    }
    try {
      final decoded = (jsonDecode(raw) as List)
          .map((e) => Map<String, dynamic>.from(e as Map)).toList();
      _listCache[key] = _copyRows(decoded);
      return decoded;
    } catch (error) {
      // Never mistake an unreadable collection for an empty one and overwrite it.
      throw FormatException('Los datos de $key no se pudieron interpretar: ${error.runtimeType}');
    }
  }

''' + s[end:]
start=s.index('  static Future<void> saveList(',s.index('class Store {'))
end=s.index('  static Future<Map<String, dynamic>> settings()',start)
s=s[:start]+r'''  static Future<void> saveList(String key, List<Map<String, dynamic>> value) async {
    await _writeRaw(key, jsonEncode(value));
    _listCache[key] = _copyRows(value);
    unawaited(FinanceSyncService.refreshSnapshot());
  }

'''+s[end:]
start=s.index('  static Future<Map<String, dynamic>> settings()',s.index('class Store {'))
end=s.index('  static Future<void> saveSettings(',start)
old=s[start:end]
if old.count("    final p = await SharedPreferences.getInstance();\n    final raw = p.getString('settings');") != 1:
    raise SystemExit('v38: settings getter mismatch')
old=old.replace("    final p = await SharedPreferences.getInstance();\n    final raw = p.getString('settings');", "    final raw = await _readRaw('settings');",1)
s=s[:start]+old+s[end:]
start=s.index('  static Future<void> saveSettings(',s.index('class Store {'))
end=s.index('\n}',start)
s=s[:start]+r'''  static Future<void> saveSettings(Map<String, dynamic> value) async {
    await _writeRaw('settings', jsonEncode(value));
    unawaited(FinanceSyncService.refreshSnapshot());
  }'''+s[end:]
p.write_text(s)


# Minimal recovery-only startup changes. Do not touch the old Gmail photo
# filters or reconstruction pipeline; their behavior needs comparison first.
p = Path('app/lib/main.dart')
s = p.read_text()

def one(old: str, new: str, label: str) -> None:
    global s
    found = s.count(old)
    if found != 1:
        raise SystemExit(f'Recovery 43: {label}: expected one anchor, got {found}')
    s = s.replace(old, new, 1)

# Automatic backup and WhatsBot sync both invoke legacy SharedPreferences
# getAll() on launch, before any local-read health check. Keep the manual
# features available but suspend those automatic writes during recovery.
one(
    '''  runApp(const PaqueteriaApp());
  try {
    await PaqueteriaBackupService.autoBackupIfDue();
  } catch (_) {}
  await WhatsBotPurchaseSyncService.syncSilently();
''',
    '''  runApp(const PaqueteriaApp());
  // Recovery mode: never start an all-keys backup or a remote sync before
  // local data has been verified. Manual sync and export remain available.
''',
    'early automatic sync and backups',
)

one(
    '''    FinanceSyncService.refreshSnapshot();
    Timer(const Duration(milliseconds: 1350), () {''',
    '''    // Avoid all-collection snapshot generation during cold start.
    Timer(const Duration(milliseconds: 1350), () {''',
    'splash finance snapshot',
)

# Keep tab state once visited, but do not instantiate other five screens on
# startup and compete for disk reads. This is a recovery-only loading change.
one(
    '''  int index = 0;
  List<Widget> pages =''',
    '''  int index = 0;
  final Set<int> _visitedTabs = <int>{0};
  List<Widget> pages =''',
    'lazy tab visit state',
)
one(
    '''      body: IndexedStack(
        index: index,
        children: pages,
      ),''',
    '''      body: IndexedStack(
        index: index,
        children: List<Widget>.generate(pages.length,
          (i) => _visitedTabs.contains(i)
              ? pages[i] : const SizedBox.shrink(),
        ),
      ),''',
    'build tab on first use',
)
one(
    '''        onDestinationSelected: (v) => setState(() => index = v),''',
    '''        onDestinationSelected: (v) => setState(() {
          index = v;
          _visitedTabs.add(v);
        }),''',
    'activate tab on selection',
)

one(
    '''  bool courierSyncing = false;
  List<Map<String, dynamic>> clients =''',
    '''  bool courierSyncing = false;
  String dashboardLoadError = '';
  String dashboardLoadWarning = '';
  List<Map<String, dynamic>> clients =''',
    'dashboard diagnostic state',
)
one(
    '''    load(syncCourier: true);
  }

  Future<void> load({bool syncCourier = false}) async {''',
    '''    // Show saved data without waiting for a network/courier call.
    load();
  }

  Future<void> load({bool syncCourier = false}) async {''',
    'network-free dashboard startup',
)

begin=s.index('  Future<void> load({bool syncCourier = false}) async {',s.index('class _DashboardPageState'))
end=s.index('\n  Future<void> openCourier() async {',begin)
s=s[:begin]+r'''  Future<void> load({bool syncCourier = false}) async {
    if (syncCourier) {
      if (mounted) setState(() => courierSyncing = true);
      try {
        await EasyPostService.syncAll().timeout(const Duration(minutes: 4));
      } catch (_) {
        // Courier errors may be retried manually. They must never prevent
        // the existing on-device collections from being shown.
      } finally {
        if (mounted) setState(() => courierSyncing = false);
      }
    }

    const names = <String>[
      'clients', 'purchases', 'packages', 'trips', 'payments',
      'flightWatches', 'agents', 'agentReports',
    ];
    final failures = <String>[];
    Future<Object?> readList(String key) async {
      try {
        return await Store.list(key).timeout(const Duration(seconds: 40));
      } catch (_) {
        failures.add(key);
        return null;
      }
    }
    Future<Object?> readSettings() async {
      try {
        return await Store.settings().timeout(const Duration(seconds: 40));
      } catch (_) {
        failures.add('settings');
        return null;
      }
    }
    final values = await Future.wait<Object?>([
      for (final key in names) readList(key),
      readSettings(),
    ]);
    if (!mounted) return;
    setState(() {
      if (values[0] != null) clients = active(values[0] as List<Map<String, dynamic>>);
      if (values[1] != null) purchases = active(values[1] as List<Map<String, dynamic>>);
      if (values[2] != null) packages = active(values[2] as List<Map<String, dynamic>>);
      if (values[3] != null) trips = active(values[3] as List<Map<String, dynamic>>);
      if (values[4] != null) payments = active(values[4] as List<Map<String, dynamic>>);
      if (values[5] != null) watches = active(values[5] as List<Map<String, dynamic>>);
      if (values[6] != null) agents = active(values[6] as List<Map<String, dynamic>>);
      if (values[7] != null) agentReports = active(values[7] as List<Map<String, dynamic>>);
      if (values[8] != null) settings = values[8] as Map<String, dynamic>;
      loading = false;
      dashboardLoadError = failures.length == values.length
          ? 'No se pudo leer el almacenamiento local. No se modificó ningún registro.'
          : '';
      dashboardLoadWarning = failures.isEmpty ? '' :
          'Datos incompletos: no se pudieron leer ' + failures.join(', ') +
          '. No se ha borrado ni guardado ningún registro.';
    });
  }
'''+s[end:]

one(
    '''    if (loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    final pendingPurchases =''',
    '''    if (loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    if (dashboardLoadError.isNotEmpty) {
      return Scaffold(
        appBar: AppBar(title: const Text('Paquetería Recovery')),
        body: Center(child: Padding(
          padding: const EdgeInsets.all(22),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.warning_amber_rounded, size: 40),
            const SizedBox(height: 12),
            Text(dashboardLoadError, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: () {
                setState(() => loading = true);
                unawaited(load());
              },
              icon: const Icon(Icons.refresh),
              label: const Text('Reintentar leer mis datos'),
            ),
          ]),
        )),
      );
    }
    final pendingPurchases =''',
    'explicit error and retry instead of spinner',
)
one(
    '''        child: ListView(padding: const EdgeInsets.all(12), children: [
          Text('Centro de operaciones',''',
    '''        child: ListView(padding: const EdgeInsets.all(12), children: [
          if (dashboardLoadWarning.isNotEmpty)
            Card(child: ListTile(
              leading: const Icon(Icons.warning_amber_rounded),
              title: const Text('Algunos registros no se han podido leer'),
              subtitle: Text(dashboardLoadWarning),
              trailing: IconButton(
                tooltip: 'Reintentar',
                onPressed: () => unawaited(load()),
                icon: const Icon(Icons.refresh),
              ),
            )),
          Text('Centro de operaciones',''',
    'read failure warning',
)
p.write_text(s)

# Finance snapshots must not re-trigger the all-preferences initialization.
p=Path('app/lib/extras.dart')
s=p.read_text()
old='''      final p = await SharedPreferences.getInstance();
      await p.setString(snapshotKey, jsonEncode(snapshot));
      await p.setString(syncedAtKey, generatedAt);'''
if s.count(old)!=1: raise SystemExit('Recovery 43: snapshot writer changed')
s=s.replace(old,'''      await Store._writeRaw(snapshotKey, jsonEncode(snapshot));
      await Store._writeRaw(syncedAtKey, generatedAt);''',1)
old='''    final p = await SharedPreferences.getInstance();
    final raw = p.getString(snapshotKey);'''
if s.count(old)!=1: raise SystemExit('Recovery 43: snapshot reader changed')
s=s.replace(old,"    final raw = await Store._readRaw(snapshotKey);",1)
p.write_text(s)

print('Recovery 43: per-key legacy storage, lazy dashboard, original Gmail photos untouched.')
