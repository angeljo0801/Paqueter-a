from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


bg_path = Path('app/lib/background_sync.dart')
bs = bg_path.read_text()

# A separate short-lived collector task avoids keeping one Dart worker alive in
# a Future.delayed polling loop. Some Samsung/Android builds suspend that loop
# as soon as the app is minimized even though Railway keeps working.
bs = replace_once(
    bs,
    "const String gmailBackgroundTask = 'gmailBackgroundReconstruct';\n",
    "const String gmailBackgroundTask = 'gmailBackgroundReconstruct';\n"
    "const String gmailBackgroundCollectTask = 'gmailBackgroundCollect';\n",
    'collector task constant',
)

bs = replace_once(
    bs,
    r'''    if (taskName == gmailBackgroundTask) {
      return GmailBackgroundSearch.execute(inputData);
    }
    if (taskName == gmailPhotoUpgradeTask) {
''',
    r'''    if (taskName == gmailBackgroundTask) {
      return GmailBackgroundSearch.execute(inputData);
    }
    if (taskName == gmailBackgroundCollectTask) {
      return GmailBackgroundSearch.collectServerJob(inputData);
    }
    if (taskName == gmailPhotoUpgradeTask) {
''',
    'collector dispatcher',
)

helper_anchor = r'''  static Future<Map<String, dynamic>> _requestServerJob({
'''
snapshot_helpers = r'''  static Future<Map<String, dynamic>> _serverJobSnapshot({
    required String baseUrl,
    required String apiKey,
    required String orderNumber,
    required String tracking,
    required String token,
  }) async {
    final base = baseUrl.trim().replaceAll(RegExp(r'/$'), '');
    if (base.isEmpty || apiKey.trim().isEmpty) {
      final direct = await _requestWithRetry(
        baseUrl: baseUrl,
        apiKey: apiKey,
        orderNumber: orderNumber,
        tracking: tracking,
      );
      return <String, dynamic>{'status': 'completed', 'result': direct};
    }

    final params = <String, String>{
      if (tracking.trim().isNotEmpty) 'tracking': tracking.trim(),
      if (tracking.trim().isEmpty && orderNumber.trim().isNotEmpty)
        'order_number': orderNumber.trim(),
      'client_token': token,
    };
    final startUri = Uri.parse('$base/api/gmail/reconstruct/jobs')
        .replace(queryParameters: params);
    final start = await http.post(
      startUri,
      headers: {'x-api-key': apiKey.trim()},
    ).timeout(const Duration(seconds: 15));

    if (start.statusCode == 404 || start.statusCode == 405) {
      final direct = await _requestWithRetry(
        baseUrl: baseUrl,
        apiKey: apiKey,
        orderNumber: orderNumber,
        tracking: tracking,
      );
      return <String, dynamic>{'status': 'completed', 'result': direct};
    }
    if (start.statusCode < 200 || start.statusCode >= 300) {
      throw Exception(start.body);
    }

    final started = jsonDecode(start.body);
    if (started is! Map) throw Exception('Respuesta inválida del servidor.');
    final jobId = '${started['jobId'] ?? ''}'.trim();
    if (jobId.isEmpty) throw Exception('Railway no devolvió el trabajo de Gmail.');

    final statusUri = Uri.parse(
      '$base/api/gmail/reconstruct/jobs/${Uri.encodeComponent(jobId)}',
    );
    final response = await http.get(
      statusUri,
      headers: {'x-api-key': apiKey.trim()},
    ).timeout(const Duration(seconds: 20));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(response.body);
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map) throw Exception('Respuesta inválida del servidor.');
    return Map<String, dynamic>.from(decoded);
  }

  static Future<void> _scheduleServerCollector({
    required String slot,
    required String token,
    required String baseUrl,
    required String apiKey,
    required String orderNumber,
    required String tracking,
    required String packageId,
    required int attempt,
  }) async {
    if (attempt > 90) return;
    final delay = attempt <= 4
        ? const Duration(seconds: 4)
        : attempt <= 12
            ? const Duration(seconds: 8)
            : const Duration(seconds: 15);

    await Workmanager().registerOneOffTask(
      'paqueteria-gmail-collect-$slot-$token-$attempt',
      gmailBackgroundCollectTask,
      inputData: {
        'slot': slot,
        'token': token,
        'baseUrl': baseUrl,
        'apiKey': apiKey,
        'orderNumber': orderNumber,
        'tracking': tracking,
        'packageId': packageId,
        'attempt': attempt,
      },
      initialDelay: delay,
      constraints: Constraints(networkType: NetworkType.connected),
      existingWorkPolicy: ExistingWorkPolicy.keep,
      tag: 'gmail-background-collector',
    );
  }

  static Future<bool> _finishBackgroundSnapshot({
    required String slot,
    required String token,
    required String baseUrl,
    required String apiKey,
    required String packageId,
    required String tracking,
    required Map<String, dynamic> rawResult,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.reload();
    final pendingRaw = prefs.getString(_pendingKey(slot)) ?? '';
    if (!pendingRaw.contains('"token":"$token"')) return true;

    final result = await _processPackagePhotosInBackground(
      result: rawResult,
      baseUrl: baseUrl,
      apiKey: apiKey,
      packageId: packageId,
      tracking: tracking,
    );

    await prefs.reload();
    final latest = prefs.getString(_pendingKey(slot)) ?? '';
    if (!latest.contains('"token":"$token"')) return true;

    await prefs.setString(
      _resultKey(slot),
      jsonEncode({
        'token': token,
        'completedAt': DateTime.now().toIso8601String(),
        'data': result,
      }),
    );
    await prefs.remove(_errorKey(slot));

    await _queueOriginalPhotoUpgrade(
      slot: slot,
      token: token,
      baseUrl: baseUrl,
      apiKey: apiKey,
      packageId: packageId,
      tracking: tracking,
      result: result,
    );

    await NotificationService.publishGmailReconstruction(
      slot: slot,
      tracking: tracking,
      photoCount: (result['_backgroundPhotoCount'] as num?)?.toInt() ?? 0,
    );
    return true;
  }

  static Future<void> _persistBackgroundError({
    required String slot,
    required String token,
    required String tracking,
    required Object error,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.reload();
    final pendingRaw = prefs.getString(_pendingKey(slot)) ?? '';
    if (!pendingRaw.contains('"token":"$token"')) return;
    await prefs.setString(
      _errorKey(slot),
      jsonEncode({
        'token': token,
        'completedAt': DateTime.now().toIso8601String(),
        'error': friendlyError(error),
      }),
    );
    try {
      await NotificationService.publishGmailReconstruction(
        slot: slot,
        tracking: tracking,
        failed: true,
      );
    } catch (_) {}
  }

'''
if 'static Future<Map<String, dynamic>> _serverJobSnapshot({' not in bs:
    bs = replace_once(
        bs,
        helper_anchor,
        snapshot_helpers + helper_anchor,
        'short server snapshot helpers',
    )

# Replace the long-lived worker with one short request. If Railway is still
# working, Android receives a new persisted collector task and this isolate exits.
execute_start = bs.find("  @pragma('vm:entry-point')\n  static Future<bool> execute(")
execute_end = bs.find("\n  }\n}\n\nclass NotificationService", execute_start)
if execute_start < 0 or execute_end < 0:
    raise SystemExit('No se encontró GmailBackgroundSearch.execute para v18')

new_execute = r'''  @pragma('vm:entry-point')
  static Future<bool> execute(Map<String, dynamic>? inputData) async {
    final data = inputData ?? const <String, dynamic>{};
    final slot = '${data['slot'] ?? ''}'.trim();
    final token = '${data['token'] ?? ''}'.trim();
    if (slot.isEmpty || token.isEmpty) return true;

    final baseUrl = '${data['baseUrl'] ?? ''}';
    final apiKey = '${data['apiKey'] ?? ''}';
    final orderNumber = '${data['orderNumber'] ?? ''}';
    final tracking = '${data['tracking'] ?? ''}';
    final packageId = '${data['packageId'] ?? ''}';

    final prefs = await SharedPreferences.getInstance();
    await prefs.reload();
    final pendingBefore = prefs.getString(_pendingKey(slot)) ?? '';
    if (!pendingBefore.contains('"token":"$token"')) return true;

    try {
      await NotificationService.initialize(requestPermission: false);
      await NotificationService.publishGmailReconstruction(
        slot: slot,
        tracking: tracking,
        running: true,
      );

      final snapshot = await _serverJobSnapshot(
        baseUrl: baseUrl,
        apiKey: apiKey,
        orderNumber: orderNumber,
        tracking: tracking,
        token: token,
      );
      final status = '${snapshot['status'] ?? ''}'.toLowerCase();

      if (status == 'completed') {
        final raw = snapshot['result'];
        if (raw is! Map) throw Exception('Railway terminó sin resultado de Gmail.');
        return _finishBackgroundSnapshot(
          slot: slot,
          token: token,
          baseUrl: baseUrl,
          apiKey: apiKey,
          packageId: packageId,
          tracking: tracking,
          rawResult: Map<String, dynamic>.from(raw),
        );
      }

      if (status == 'failed') {
        await _persistBackgroundError(
          slot: slot,
          token: token,
          tracking: tracking,
          error: Exception('${snapshot['error'] ?? 'No se pudo reconstruir desde Gmail.'}'),
        );
        return true;
      }

      await _scheduleServerCollector(
        slot: slot,
        token: token,
        baseUrl: baseUrl,
        apiKey: apiKey,
        orderNumber: orderNumber,
        tracking: tracking,
        packageId: packageId,
        attempt: 1,
      );
      return true;
    } catch (_) {
      // Do not mark a temporary pause/network interruption as a permanent
      // failure. Persist another OS-managed collector and exit quickly.
      try {
        await _scheduleServerCollector(
          slot: slot,
          token: token,
          baseUrl: baseUrl,
          apiKey: apiKey,
          orderNumber: orderNumber,
          tracking: tracking,
          packageId: packageId,
          attempt: 1,
        );
      } catch (_) {}
      return true;
    }
  }

  @pragma('vm:entry-point')
  static Future<bool> collectServerJob(Map<String, dynamic>? inputData) async {
    final data = inputData ?? const <String, dynamic>{};
    final slot = '${data['slot'] ?? ''}'.trim();
    final token = '${data['token'] ?? ''}'.trim();
    if (slot.isEmpty || token.isEmpty) return true;

    final baseUrl = '${data['baseUrl'] ?? ''}';
    final apiKey = '${data['apiKey'] ?? ''}';
    final orderNumber = '${data['orderNumber'] ?? ''}';
    final tracking = '${data['tracking'] ?? ''}';
    final packageId = '${data['packageId'] ?? ''}';
    final attempt = ((data['attempt'] as num?)?.toInt() ?? 1).clamp(1, 90);

    final prefs = await SharedPreferences.getInstance();
    await prefs.reload();
    final pendingBefore = prefs.getString(_pendingKey(slot)) ?? '';
    if (!pendingBefore.contains('"token":"$token"')) return true;

    try {
      final snapshot = await _serverJobSnapshot(
        baseUrl: baseUrl,
        apiKey: apiKey,
        orderNumber: orderNumber,
        tracking: tracking,
        token: token,
      );
      final status = '${snapshot['status'] ?? ''}'.toLowerCase();

      if (status == 'completed') {
        final raw = snapshot['result'];
        if (raw is! Map) throw Exception('Railway terminó sin resultado de Gmail.');
        return _finishBackgroundSnapshot(
          slot: slot,
          token: token,
          baseUrl: baseUrl,
          apiKey: apiKey,
          packageId: packageId,
          tracking: tracking,
          rawResult: Map<String, dynamic>.from(raw),
        );
      }

      if (status == 'failed') {
        await _persistBackgroundError(
          slot: slot,
          token: token,
          tracking: tracking,
          error: Exception('${snapshot['error'] ?? 'No se pudo reconstruir desde Gmail.'}'),
        );
        return true;
      }
    } catch (_) {
      // Keep retrying as discrete WorkManager jobs.
    }

    try {
      await _scheduleServerCollector(
        slot: slot,
        token: token,
        baseUrl: baseUrl,
        apiKey: apiKey,
        orderNumber: orderNumber,
        tracking: tracking,
        packageId: packageId,
        attempt: attempt + 1,
      );
    } catch (_) {}
    return true;
  }
'''
bs = bs[:execute_start] + new_execute + bs[execute_end + 5:]

# In v16 the HTTP POST to Railway is awaited before WorkManager registration.
# Schedule the OS task first, so minimizing immediately after the tap cannot
# prevent Android from owning the work.
old_order = r'''      // This is deliberately before WorkManager. Tapping Buscar starts the
      // server job now instead of waiting for Android's scheduler.
      try {
        await _startServerJobNow(
          baseUrl: base,
          apiKey: key,
          orderNumber: order,
          tracking: track,
          token: token,
        );
      } catch (_) {
        // WorkManager/direct retry below remains the safety net.
      }

      if (backgroundAvailable) {
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
              'packageId': packageId.trim(),
            },
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

new_order = r'''      // Give Android ownership of the task first. This call is persisted by
      // WorkManager before any long HTTP operation begins.
      if (backgroundAvailable) {
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
              'packageId': packageId.trim(),
            },
            constraints: Constraints(networkType: NetworkType.connected),
            existingWorkPolicy: ExistingWorkPolicy.keep,
            tag: 'gmail-background-search',
          );
          backgroundScheduled = true;
        } catch (_) {
          // Foreground/server path below can still start the durable Railway job.
        }
      }

      // Also start Railway immediately while the app is visible. If Android
      // pauses this isolate a moment later, WorkManager already owns the task.
      try {
        await _startServerJobNow(
          baseUrl: base,
          apiKey: key,
          orderNumber: order,
          tracking: track,
          token: token,
        );
      } catch (_) {
        // The persisted WorkManager task will retry.
      }
'''

bs = replace_once(
    bs,
    old_order,
    new_order,
    'persist WorkManager before immediate Railway call',
)

bg_path.write_text(bs)

print('Gmail v18 applied: background work uses short OS-managed collectors and survives Activity minimization.')
