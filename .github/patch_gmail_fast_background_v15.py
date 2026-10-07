from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# v15: reconstruction finishes with usable thumbnails/data. Full originals
# continue in a second WorkManager job over any connected network.
helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()

old_cache = r'''      var permanent = File('${dir.path}/$digest.$ext');
      var usedOriginal = analysisRaw == rawUrl;
      if (analysisRaw != rawUrl) {
        try {
          final originalResponse = await http.get(
            Uri.parse(gmailPhotoUrl(baseUrl, image)),
            headers: gmailPhotoHeaders(baseUrl, apiKey, image) ??
                const <String, String>{},
          ).timeout(const Duration(seconds: 35));
          if (originalResponse.statusCode >= 200 &&
              originalResponse.statusCode < 300 &&
              originalResponse.bodyBytes.length >= 3500 &&
              originalResponse.bodyBytes.length <= 12 * 1024 * 1024) {
            final originalBytes = originalResponse.bodyBytes;
            final originalDigest = _gmailPhotoDigest(originalBytes);
            final originalExt = _gmailPhotoExt(
              rawUrl,
              originalResponse.headers['content-type'] ?? '',
            );
            permanent = File('${dir.path}/$originalDigest.$originalExt');
            if (!await permanent.exists()) {
              await permanent.writeAsBytes(originalBytes, flush: true);
            }
            usedOriginal = true;
          }
        } catch (_) {
          // Keep the Railway thumbnail as an offline fallback. The original can
          // be retried later without losing the reconstruction.
        }
      }
      if (!usedOriginal) {
        if (!await permanent.exists()) {
          await temp.rename(permanent.path);
        } else if (await temp.exists()) {
          await temp.delete();
        }
      } else if (await temp.exists()) {
        await temp.delete();
      }
      offlinePaths[rawUrl] = permanent.path;
      accepted.add({
        ...image,
        'localPath': permanent.path,
        'cachedOriginal': usedOriginal,
'''
new_cache = r'''      final permanent = File('${dir.path}/$digest.$ext');
      if (!await permanent.exists()) {
        await temp.rename(permanent.path);
      } else if (await temp.exists()) {
        await temp.delete();
      }
      final usedOriginal = analysisRaw == rawUrl;
      offlinePaths[rawUrl] = permanent.path;
      accepted.add({
        ...image,
        'localPath': permanent.path,
        'cachedOriginal': usedOriginal,
'''
hs = replace_once(
    hs,
    old_cache,
    new_cache,
    'finish with thumbnail before original download',
)
helper_path.write_text(hs)


bg_path = Path('app/lib/background_sync.dart')
bs = bg_path.read_text()

bs = replace_once(
    bs,
    "const String gmailBackgroundTask = 'gmailBackgroundReconstruct';\n",
    "const String gmailBackgroundTask = 'gmailBackgroundReconstruct';\n"
    "const String gmailPhotoUpgradeTask = 'gmailBackgroundPhotoUpgrade';\n",
    'photo upgrade task constant',
)

bs = replace_once(
    bs,
    r'''    if (taskName == gmailBackgroundTask) {
      return GmailBackgroundSearch.execute(inputData);
    }
    if (taskName != courierBackgroundTask) return true;
''',
    r'''    if (taskName == gmailBackgroundTask) {
      return GmailBackgroundSearch.execute(inputData);
    }
    if (taskName == gmailPhotoUpgradeTask) {
      return GmailBackgroundSearch.upgradeOriginalPhotos(inputData);
    }
    if (taskName != courierBackgroundTask) return true;
''',
    'photo upgrade dispatcher',
)

bs = replace_once(
    bs,
    r'''        'gmailRejectedImages': rejected,
        '_backgroundProcessed': true,
        '_backgroundPhotoCount': accepted.length,
''',
    r'''        'gmailRejectedImages': rejected,
        'gmailAcceptedPhotoCandidates': accepted,
        'gmailOriginalPhotosPending':
            accepted.any((e) => e['cachedOriginal'] != true),
        '_backgroundProcessed': true,
        '_backgroundPhotoCount': accepted.length,
''',
    'accepted candidate metadata in result',
)

bs = replace_once(
    bs,
    r'''          'gmailRejectedImages': rejected,
          'gmailSourceEmails': dynList(result['sourceEmails']).map((e) => '$e').toList(),
''',
    r'''          'gmailRejectedImages': rejected,
          'gmailAcceptedPhotoCandidates': accepted,
          'gmailOriginalPhotosPending':
              accepted.any((e) => e['cachedOriginal'] != true),
          'gmailSourceEmails': dynList(result['sourceEmails']).map((e) => '$e').toList(),
''',
    'accepted candidate metadata in package',
)

execute_anchor = r'''  @pragma('vm:entry-point')
  static Future<bool> execute(Map<String, dynamic>? inputData) async {
'''
upgrade_helpers = r'''  static String _upgradeKey(String slot, String token) =>
      'gmailPhotoUpgrade_${slot}_$token';

  static Future<void> _queueOriginalPhotoUpgrade({
    required String slot,
    required String token,
    required String baseUrl,
    required String apiKey,
    required String packageId,
    required String tracking,
    required Map<String, dynamic> result,
  }) async {
    final accepted = dynList(result['gmailAcceptedPhotoCandidates'])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .where((e) => e['cachedOriginal'] != true)
        .toList();
    if (accepted.isEmpty) return;

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _upgradeKey(slot, token),
      jsonEncode({
        'baseUrl': baseUrl,
        'apiKey': apiKey,
        'packageId': packageId,
        'tracking': tracking,
        'accepted': accepted,
      }),
    );
    await Workmanager().registerOneOffTask(
      'paqueteria-gmail-originals-$slot-$token',
      gmailPhotoUpgradeTask,
      inputData: {'slot': slot, 'token': token},
      constraints: Constraints(networkType: NetworkType.connected),
      existingWorkPolicy: ExistingWorkPolicy.keep,
      tag: 'gmail-photo-upgrade',
    );
  }

  @pragma('vm:entry-point')
  static Future<bool> upgradeOriginalPhotos(
    Map<String, dynamic>? inputData,
  ) async {
    final data = inputData ?? const <String, dynamic>{};
    final slot = '${data['slot'] ?? ''}'.trim();
    final token = '${data['token'] ?? ''}'.trim();
    if (slot.isEmpty || token.isEmpty) return true;

    final prefs = await SharedPreferences.getInstance();
    await prefs.reload();
    final raw = prefs.getString(_upgradeKey(slot, token));
    if (raw == null || raw.isEmpty) return true;

    Map<String, dynamic> job;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return true;
      job = Map<String, dynamic>.from(decoded);
    } catch (_) {
      return true;
    }

    final baseUrl = '${job['baseUrl'] ?? ''}'.trim();
    final apiKey = '${job['apiKey'] ?? ''}'.trim();
    final packageId = '${job['packageId'] ?? ''}'.trim();
    final tracking = '${job['tracking'] ?? ''}'.trim();
    final accepted = dynList(job['accepted'])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    if (accepted.isEmpty) {
      await prefs.remove(_upgradeKey(slot, token));
      return true;
    }

    final documents = await getApplicationDocumentsDirectory();
    final dir = Directory('${documents.path}/gmail_product_photos');
    if (!await dir.exists()) await dir.create(recursive: true);

    Future<MapEntry<String, String>?> downloadOne(
      Map<String, dynamic> image,
    ) async {
      final rawUrl = '${image['url'] ?? ''}'.trim();
      if (rawUrl.isEmpty) return null;
      try {
        final response = await http.get(
          Uri.parse(gmailPhotoUrl(baseUrl, image)),
          headers: gmailPhotoHeaders(baseUrl, apiKey, image) ??
              const <String, String>{},
        ).timeout(const Duration(seconds: 35));
        if (response.statusCode < 200 ||
            response.statusCode >= 300 ||
            response.bodyBytes.length < 3500 ||
            response.bodyBytes.length > 12 * 1024 * 1024) {
          return null;
        }
        final digest = _gmailPhotoDigest(response.bodyBytes);
        final ext = _gmailPhotoExt(
          rawUrl,
          response.headers['content-type'] ?? '',
        );
        final file = File('${dir.path}/$digest.$ext');
        if (!await file.exists()) {
          await file.writeAsBytes(response.bodyBytes, flush: true);
        }
        return MapEntry(rawUrl, file.path);
      } catch (_) {
        return null;
      }
    }

    final upgraded = <String, String>{};
    final pending = <Map<String, dynamic>>[];
    for (var i = 0; i < accepted.length; i += 3) {
      final batch = accepted.skip(i).take(3).toList();
      final rows = await Future.wait(batch.map(downloadOne));
      for (var j = 0; j < batch.length; j++) {
        final entry = rows[j];
        if (entry == null) {
          pending.add(batch[j]);
        } else {
          upgraded[entry.key] = entry.value;
        }
      }
    }

    if (upgraded.isNotEmpty) {
      await prefs.reload();
      List<Map<String, dynamic>> packages = <Map<String, dynamic>>[];
      try {
        packages = (jsonDecode(prefs.getString('packages') ?? '[]') as List)
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
      } catch (_) {}

      var index = -1;
      if (packageId.isNotEmpty) {
        index = packages.indexWhere((e) => '${e['id'] ?? ''}' == packageId);
      }
      if (index < 0 && tracking.isNotEmpty) {
        final target = tracking.toLowerCase();
        index = packages.indexWhere(
          (e) => '${e['tracking'] ?? ''}'.trim().toLowerCase() == target,
        );
      }
      if (index >= 0) {
        final current = Map<String, dynamic>.from(packages[index]);
        final offline = <String, String>{};
        final oldOffline = current['gmailOfflinePhotoPaths'];
        if (oldOffline is Map) {
          offline.addAll(oldOffline.map((k, v) => MapEntry('$k', '$v')));
        }
        offline.addAll(upgraded);
        packages[index] = {
          ...current,
          'gmailOfflinePhotoPaths': offline,
          'gmailOriginalPhotosPending': pending.isNotEmpty,
          'gmailOriginalPhotosUpdatedAt': DateTime.now().toIso8601String(),
        };
        await prefs.setString('packages', jsonEncode(packages));
        Store.clearListCache('packages');
      }
    }

    if (pending.isEmpty) {
      await prefs.remove(_upgradeKey(slot, token));
      return true;
    }

    await prefs.setString(
      _upgradeKey(slot, token),
      jsonEncode({...job, 'accepted': pending}),
    );
    return false;
  }

'''
bs = replace_once(
    bs,
    execute_anchor,
    upgrade_helpers + execute_anchor,
    'deferred original photo upgrade helpers',
)

result_saved = r'''      await prefs.setString(
        _resultKey(slot),
        jsonEncode({
          'token': token,
          'completedAt': DateTime.now().toIso8601String(),
          'data': result,
        }),
      );
      await NotificationService.publishGmailReconstruction(
'''
result_saved_new = r'''      await prefs.setString(
        _resultKey(slot),
        jsonEncode({
          'token': token,
          'completedAt': DateTime.now().toIso8601String(),
          'data': result,
        }),
      );
      await _queueOriginalPhotoUpgrade(
        slot: slot,
        token: token,
        baseUrl: '${data['baseUrl'] ?? ''}',
        apiKey: '${data['apiKey'] ?? ''}',
        packageId: '${data['packageId'] ?? ''}',
        tracking: '${data['tracking'] ?? ''}',
        result: result,
      );
      await NotificationService.publishGmailReconstruction(
'''
bs = replace_once(
    bs,
    result_saved,
    result_saved_new,
    'queue originals after fast result',
)

bg_path.write_text(bs)

print('Gmail v15 applied: parallel fast reconstruction + deferred originals.')
