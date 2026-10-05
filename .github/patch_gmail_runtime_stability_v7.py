from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# v7 runtime stability:
# 1) The canonical source already has an async main(), so the older background
#    patch never inserted WorkManager initialization. Initialize it before the
#    UI starts so the first Gmail tap cannot fail with "initialize first".
# 2) Also make Gmail background initialization idempotent and defensive in case
#    Android recreates the process or startup initialization ever fails.
# 3) Retry transient socket/client failures and never expose a raw ClientException
#    / PlatformException / stack trace to the user.
# 4) Delay the safety-net worker slightly and make it exit before network I/O if
#    the foreground request already finished, avoiding duplicate Railway calls.

main_path = Path('app/lib/main.dart')
ms = main_path.read_text()
startup_anchor = "Future<void> main() async {\n  WidgetsFlutterBinding.ensureInitialized();\n"
startup_new = (
    "Future<void> main() async {\n"
    "  WidgetsFlutterBinding.ensureInitialized();\n"
    "  try {\n"
    "    await NotificationService.initialize(requestPermission: true);\n"
    "    await BackgroundCourierSync.initializeAndSchedule();\n"
    "  } catch (_) {}\n"
)
if "await BackgroundCourierSync.initializeAndSchedule();" not in ms:
    ms = replace_once(ms, startup_anchor, startup_new, 'startup WorkManager initialization')
main_path.write_text(ms)


bg_path = Path('app/lib/background_sync.dart')
bs = bg_path.read_text()

old_init = r'''class BackgroundCourierSync {
  static Future<void> initializeAndSchedule() async {
    await Workmanager().initialize(courierCallbackDispatcher);
    await schedule();
  }
'''
new_init = r'''class BackgroundCourierSync {
  static bool _initialized = false;
  static Future<void>? _initializing;

  static Future<void> ensureInitialized() async {
    if (_initialized) return;
    final existing = _initializing;
    if (existing != null) return existing;
    final future = () async {
      await Workmanager().initialize(courierCallbackDispatcher);
      _initialized = true;
      await schedule();
    }();
    _initializing = future;
    try {
      await future;
    } finally {
      _initializing = null;
    }
  }

  static Future<void> initializeAndSchedule() => ensureInitialized();
'''
bs = replace_once(bs, old_init, new_init, 'idempotent WorkManager initialization')

request_end_anchor = r'''    return Map<String, dynamic>.from(decoded);
  }

  static Future<Map<String, dynamic>?> _readFinished(
'''
request_retry_block = r'''    return Map<String, dynamic>.from(decoded);
  }

  static bool _transientNetworkError(Object error) {
    final lower = '$error'.toLowerCase();
    return lower.contains('clientexception') ||
        lower.contains('socketexception') ||
        lower.contains('software caused connection abort') ||
        lower.contains('connection abort') ||
        lower.contains('connection reset') ||
        lower.contains('connection closed') ||
        lower.contains('broken pipe') ||
        lower.contains('failed host lookup') ||
        lower.contains('timed out') ||
        lower.contains('timeout');
  }

  static String friendlyError(Object error) {
    final raw = '$error';
    final lower = raw.toLowerCase();
    if (_transientNetworkError(error)) {
      return 'La conexión con Gmail se interrumpió temporalmente. Inténtalo de nuevo; si la búsqueda quedó en segundo plano, se recuperará al volver.';
    }
    if (lower.contains('app_api_key') || lower.contains('api key')) {
      return 'Falta o no es válida la clave del servidor de WhatsBot.';
    }
    if (lower.contains('401') || lower.contains('403') || lower.contains('unauthorized') || lower.contains('forbidden')) {
      return 'Gmail necesita volver a autorizarse o la clave del servidor no es válida.';
    }
    if (lower.contains('no enabled gmail') || lower.contains('no gmail')) {
      return 'No hay una cuenta de Gmail habilitada para buscar.';
    }
    return 'No se pudo completar la búsqueda en Gmail. Inténtalo nuevamente.';
  }

  static Future<Map<String, dynamic>> _requestWithRetry({
    required String baseUrl,
    required String apiKey,
    required String orderNumber,
    required String tracking,
  }) async {
    Object? lastError;
    for (var attempt = 0; attempt < 3; attempt++) {
      try {
        return await _request(
          baseUrl: baseUrl,
          apiKey: apiKey,
          orderNumber: orderNumber,
          tracking: tracking,
        );
      } catch (e) {
        lastError = e;
        if (!_transientNetworkError(e) || attempt >= 2) rethrow;
        await Future<void>.delayed(Duration(milliseconds: 700 * (attempt + 1)));
      }
    }
    throw Exception(friendlyError(lastError ?? Exception('network')));
  }

  static Future<Map<String, dynamic>?> _readFinished(
'''
bs = replace_once(bs, request_end_anchor, request_retry_block, 'Gmail transient retry helper')

validation_anchor = r'''    if (order.isEmpty && track.isEmpty) {
      throw Exception('Escribe un tracking o número de orden primero.');
    }

    final prefs = await SharedPreferences.getInstance();
'''
validation_new = r'''    if (order.isEmpty && track.isEmpty) {
      throw Exception('Escribe un tracking o número de orden primero.');
    }

    var backgroundAvailable = false;
    try {
      await BackgroundCourierSync.ensureInitialized();
      backgroundAvailable = true;
    } catch (_) {
      // Foreground Gmail search must still work even if Android refuses to
      // initialize the background scheduler for some reason.
    }
    var backgroundScheduled = false;

    final prefs = await SharedPreferences.getInstance();
'''
bs = replace_once(bs, validation_anchor, validation_new, 'defensive Gmail WorkManager initialization')

old_registration = r'''      await Workmanager().registerOneOffTask(
        'paqueteria-gmail-$slot-$token',
        gmailBackgroundTask,
        inputData: {
          'slot': slot,
          'token': token,
          'baseUrl': base,
          'apiKey': key,
          'orderNumber': order,
          'tracking': track,
        },
        constraints: Constraints(networkType: NetworkType.connected),
        existingWorkPolicy: ExistingWorkPolicy.keep,
        tag: 'gmail-background-search',
      );
'''
new_registration = r'''      if (backgroundAvailable) {
        try {
          await Workmanager().registerOneOffTask(
            'paqueteria-gmail-$slot-$token',
            gmailBackgroundTask,
            inputData: {
              'slot': slot,
              'token': token,
              'baseUrl': base,
              'apiKey': key,
              'orderNumber': order,
              'tracking': track,
            },
            initialDelay: const Duration(seconds: 8),
            constraints: Constraints(networkType: NetworkType.connected),
            existingWorkPolicy: ExistingWorkPolicy.keep,
            tag: 'gmail-background-search',
          );
          backgroundScheduled = true;
        } catch (_) {
          // Do not fail the visible Gmail search because WorkManager scheduling
          // was unavailable. The direct request below can still succeed.
        }
      }
'''
bs = replace_once(bs, old_registration, new_registration, 'safe delayed Gmail worker scheduling')

# Use retry helper for both foreground and worker requests.
bs = bs.replace('      final data = await _request(\n', '      final data = await _requestWithRetry(\n', 1)
bs = bs.replace('      final result = await _request(\n', '      final result = await _requestWithRetry(\n', 1)

old_direct_failure = r'''      throw Exception('$directError · La búsqueda seguirá intentando en segundo plano.');
'''
new_direct_failure = r'''      if (backgroundScheduled) {
        return <String, dynamic>{
          'found': false,
          '_backgroundPending': true,
          '_message': 'La conexión se interrumpió, pero la búsqueda continúa en segundo plano. Puedes salir de esta pantalla y volver después.',
        };
      }
      throw Exception(friendlyError(directError));
'''
bs = replace_once(bs, old_direct_failure, new_direct_failure, 'friendly foreground Gmail failure')

worker_anchor = r'''    final prefs = await SharedPreferences.getInstance();
    try {
      final result = await _requestWithRetry(
'''
worker_new = r'''    final prefs = await SharedPreferences.getInstance();
    await prefs.reload();
    final pendingBefore = prefs.getString(_pendingKey(slot)) ?? '';
    if (!pendingBefore.contains('\"token\":\"$token\"')) return true;
    try {
      final result = await _requestWithRetry(
'''
bs = replace_once(bs, worker_anchor, worker_new, 'skip obsolete Gmail worker before network call')

# Do not persist raw Java/Dart networking exceptions for later display.
bs = bs.replace("          'error': '$e',\n", "          'error': friendlyError(e),\n", 1)
bg_path.write_text(bs)


# Package editor: a direct connection interruption with a valid background job
# is informational, not a failed Gmail reconstruction.
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()
found_anchor = r'''      if (data['found'] != true) {
'''
pending_block = r'''      if (data['_backgroundPending'] == true) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('${data['_message'] ?? 'La búsqueda continúa en segundo plano.'}')),
          );
        }
        return;
      }
      if (data['found'] != true) {
'''
ps = replace_once(ps, found_anchor, pending_block, 'package background-pending Gmail result')

# Replace the raw exception snackbar with a user-facing message only.
raw_package_error = "          SnackBar(content: Text('No se pudo reconstruir desde Gmail: $e')),\n"
friendly_package_error = "          SnackBar(content: Text(GmailBackgroundSearch.friendlyError(e))),\n"
if raw_package_error in ps:
    ps = ps.replace(raw_package_error, friendly_package_error, 1)
packages_path.write_text(ps)


# Purchases/orders: sanitize safeLookup errors so ClientException/PlatformException
# strings never leak into the UI. If the worker continues in background, show
# that message directly instead of calling it a permanent failure.
purchases_path = Path('app/lib/purchases.dart')
us = purchases_path.read_text()
us = us.replace(
    "          return {'found': false, '_error': '$e'};\n",
    "          return {'found': false, '_error': GmailBackgroundSearch.friendlyError(e)};\n",
    1,
)
us = us.replace(
    "              content: Text(error.isEmpty\n                  ? 'No encontré correos para esos números de orden.'\n                  : 'No pude vincular la compra: $error'),\n",
    "              content: Text(error.isEmpty\n                  ? 'No encontré correos para esos números de orden.'\n                  : error),\n",
    1,
)
purchases_path.write_text(us)

print('Gmail runtime stability v7 applied: WorkManager ready on first tap, transient network retries, clean background fallback.')
