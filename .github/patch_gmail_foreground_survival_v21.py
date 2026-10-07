from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Missing expected block: {label}')
    return text.replace(old, new, 1)


# Keep the Flutter isolate alive with a real Android foreground service while a
# Gmail reconstruction is active. WorkManager remains as a second safety net.
main_path = Path('app/lib/main.dart')
ms = main_path.read_text()
if "package:flutter_background/flutter_background.dart" not in ms:
    ms = replace_once(
        ms,
        "import 'package:flutter/material.dart';\n",
        "import 'package:flutter/material.dart';\n"
        "import 'package:flutter_background/flutter_background.dart';\n",
        'flutter_background import',
    )
main_path.write_text(ms)

pub_path = Path('app/pubspec.yaml')
pub = pub_path.read_text()
if '  flutter_background:' not in pub:
    # place beside workmanager so background dependencies stay grouped
    if '  workmanager:' in pub:
        line = next(x for x in pub.splitlines() if x.startswith('  workmanager:'))
        pub = pub.replace(line + '\n', line + '\n  flutter_background: ^1.3.1\n', 1)
    else:
        pub = replace_once(
            pub,
            'dependencies:\n',
            'dependencies:\n  flutter_background: ^1.3.1\n',
            'flutter_background dependency',
        )
pub_path.write_text(pub)


bg_path = Path('app/lib/background_sync.dart')
bs = bg_path.read_text()

guard_class = r'''
class GmailForegroundExecution {
  static bool _initialized = false;

  static Future<bool> start() async {
    if (!Platform.isAndroid) return true;
    try {
      if (!_initialized) {
        _initialized = await FlutterBackground.initialize(
          androidConfig: const FlutterBackgroundAndroidConfig(
            notificationTitle: 'Paquetería · Reconstrucción en curso',
            notificationText:
                'Buscando correos y preparando fotos. Puedes minimizar Paquetería.',
            notificationImportance: AndroidNotificationImportance.normal,
            enableWifiLock: true,
            showBadge: false,
            shouldRequestBatteryOptimizationsOff: true,
          ),
        );
      }
      if (!_initialized) return false;
      if (FlutterBackground.isBackgroundExecutionEnabled) return true;
      return await FlutterBackground.enableBackgroundExecution();
    } catch (_) {
      return false;
    }
  }

  static bool get canProcess {
    if (WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed) {
      return true;
    }
    if (!Platform.isAndroid) return false;
    return FlutterBackground.isBackgroundExecutionEnabled;
  }

  static Future<void> stop() async {
    if (!Platform.isAndroid || !_initialized) return;
    try {
      if (FlutterBackground.isBackgroundExecutionEnabled) {
        await FlutterBackground.disableBackgroundExecution();
      }
    } catch (_) {}
  }
}

'''

anchor = 'class GmailBackgroundSearch {\n'
if 'class GmailForegroundExecution {' not in bs:
    bs = replace_once(
        bs,
        anchor,
        guard_class + anchor,
        'foreground execution helper',
    )
bg_path.write_text(bs)


packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()

method_start = ps.find('  Future<void> reconstructFromGmail() async {')
method_end = ps.find('\n  Future<void> openEmailPhoto(', method_start)
if method_start < 0 or method_end < 0:
    raise SystemExit('Could not locate reconstructFromGmail for foreground guard')
method = ps[method_start:method_end]

# Start the foreground service after credentials are known, but before any
# server/network wait. Android then keeps the main isolate + wake lock alive.
credentials_anchor = r'''    if (gmailApiKey.isEmpty) {
      if (!mounted) return;
      setState(() => gmailLoading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Falta la API key del servidor de WhatsBot en Configuración.')),
      );
      return;
    }
'''
if credentials_anchor not in method:
    # Compatibility with a generated variant without the explicit loading reset.
    credentials_anchor = r'''    if (gmailApiKey.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Falta la API key del servidor de WhatsBot en Configuración.')),
      );
      return;
    }
'''

start_insert = credentials_anchor + r'''    final foregroundKeptAlive = await GmailForegroundExecution.start();
    if (!foregroundKeptAlive && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Android no concedió el modo continuo. La búsqueda seguirá con el respaldo de segundo plano.',
          ),
          duration: Duration(seconds: 3),
        ),
      );
    }
'''
method = replace_once(
    method,
    credentials_anchor,
    start_insert,
    'start foreground execution before Gmail request',
)

# Always remove the ongoing foreground notification once this particular search
# has either completed, failed, or been handed back to the durable worker.
finally_old = r'''    } finally {
      if (mounted) setState(() => gmailLoading = false);
    }
'''
finally_new = r'''    } finally {
      if (mounted) setState(() => gmailLoading = false);
      await GmailForegroundExecution.stop();
    }
'''
method = replace_once(
    method,
    finally_old,
    finally_new,
    'stop foreground execution after Gmail search',
)

ps = ps[:method_start] + method + ps[method_end:]

# v13 intentionally blocked all UI-isolate processing while paused because the
# process used to be suspendable. With the foreground service active it is safe
# to continue OCR/cache/persistence while minimized.
old_guard = 'WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed'
count = ps.count(old_guard)
if count < 3:
    raise SystemExit(f'Expected lifecycle guards from v13, found only {count}')
ps = ps.replace(old_guard, '!GmailForegroundExecution.canProcess')

packages_path.write_text(ps)


# Android 14+ requires an explicit foreground-service type. Also declare wake
# and battery-optimization permissions because the user explicitly needs the
# reconstruction to survive Samsung/Android background suspension.
manifest_path = Path('app/android/app/src/main/AndroidManifest.xml')
manifest = manifest_path.read_text()

permission_anchor = '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
permissions = [
    'android.permission.FOREGROUND_SERVICE',
    'android.permission.FOREGROUND_SERVICE_DATA_SYNC',
    'android.permission.WAKE_LOCK',
    'android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS',
]
for perm in permissions:
    marker = f'<uses-permission android:name="{perm}" />'
    if marker not in manifest:
        manifest = manifest.replace(
            permission_anchor,
            permission_anchor + f'    {marker}\n',
            1,
        )

service = '''        <service
            android:name="de.julianassmann.flutter_background.IsolateHolderService"
            android:exported="false"
            android:foregroundServiceType="dataSync" />
'''
if 'de.julianassmann.flutter_background.IsolateHolderService' not in manifest:
    manifest = manifest.replace('    </application>', service + '    </application>', 1)

manifest_path.write_text(manifest)

print('Gmail v21 applied: foreground data-sync service keeps reconstruction alive while minimized.')
