from pathlib import Path

native = Path('app/android/app/src/main/kotlin/com/angelapps/paqueteria/PaqueteriaLocalStoreBridge.kt')
native.parent.mkdir(parents=True, exist_ok=True)
native.write_text(r'''package com.angelapps.paqueteria

import android.content.Context
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel

// Uses the existing legacy SharedPreferences file without migration.
// Avoids transporting *all* user data over Android IPC on startup.
object PaqueteriaLocalStoreBridge {
    private const val CHANNEL = "com.angelapps.paqueteria/local_store"
    private const val NAME = "FlutterSharedPreferences"
    private const val SIZE = 48000

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
        final success = await _perKeyStore.invokeMethod<bool>(
          'writeString', {'key': 'flutter.$key', 'value': value},
        ).timeout(const Duration(seconds: 30));
        if (success != true) throw StateError('No se pudo guardar $key.');
        return;
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
print('v38 per-key native preferences: original data preserved, no getAll IPC.')
