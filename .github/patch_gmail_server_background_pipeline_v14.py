from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Smart photo pipeline: use Railway thumbnails for analysis, then cache only the
# accepted original. This cuts mobile data and makes slow connections usable.
# ---------------------------------------------------------------------------
helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()

hs = replace_once(
    hs,
    """    final rawUrl = '${image['url'] ?? ''}'.trim();
    if (rawUrl.isEmpty) continue;
    if (_gmailUrlClearlyNotProduct(rawUrl)) {
""",
    """    final rawUrl = '${image['url'] ?? ''}'.trim();
    if (rawUrl.isEmpty) continue;
    final thumbnailRaw = '${image['thumbnailUrl'] ?? ''}'.trim();
    final analysisRaw = thumbnailRaw.isNotEmpty ? thumbnailRaw : rawUrl;
    final analysisImage = <String, dynamic>{...image, 'url': analysisRaw};
    if (_gmailUrlClearlyNotProduct('${image['originalUrl'] ?? rawUrl}')) {
""",
    'thumbnail analysis URL',
)

hs = replace_once(
    hs,
    """      final resolved = gmailPhotoUrl(baseUrl, image);
      final response = await http.get(
        Uri.parse(resolved),
        headers: gmailPhotoHeaders(baseUrl, apiKey, image) ?? const <String, String>{},
      ).timeout(const Duration(seconds: 18));
""",
    """      final resolved = gmailPhotoUrl(baseUrl, analysisImage);
      final response = await http.get(
        Uri.parse(resolved),
        headers: gmailPhotoHeaders(baseUrl, apiKey, analysisImage) ?? const <String, String>{},
      ).timeout(const Duration(seconds: 18));
""",
    'download compact analysis image first',
)

old_final = r'''      final permanent = File('${dir.path}/$digest.$ext');
      if (!await permanent.exists()) {
        await temp.rename(permanent.path);
      } else if (await temp.exists()) {
        await temp.delete();
      }
      offlinePaths[rawUrl] = permanent.path;
      accepted.add({
        ...image,
        'localPath': permanent.path,
'''
new_final = r'''      var permanent = File('${dir.path}/$digest.$ext');
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
hs = replace_once(hs, old_final, new_final, 'cache accepted original after thumbnail OCR')
helper_path.write_text(hs)


# ---------------------------------------------------------------------------
# WorkManager: Railway owns the durable job; Android performs the compact photo
# analysis/cache and writes the final package while the UI is not running.
# NetworkType.connected remains intentionally unrestricted: Wi-Fi is NOT needed.
# ---------------------------------------------------------------------------
bg_path = Path('app/lib/background_sync.dart')
bs = bg_path.read_text()

retry_anchor = r'''  static Future<Map<String, dynamic>> _requestWithRetry({
'''
server_job_helpers = r'''  static Future<Map<String, dynamic>> _requestServerJob({
    required String baseUrl,
    required String apiKey,
    required String orderNumber,
    required String tracking,
    required String token,
  }) async {
    final base = baseUrl.trim().replaceAll(RegExp(r'/$'), '');
    if (base.isEmpty || apiKey.trim().isEmpty) {
      return _requestWithRetry(
        baseUrl: baseUrl,
        apiKey: apiKey,
        orderNumber: orderNumber,
        tracking: tracking,
      );
    }
    final params = <String, String>{
      if (tracking.trim().isNotEmpty) 'tracking': tracking.trim(),
      if (tracking.trim().isEmpty && orderNumber.trim().isNotEmpty)
        'order_number': orderNumber.trim(),
      'client_token': token,
    };
    try {
      final startUri = Uri.parse('$base/api/gmail/reconstruct/jobs')
          .replace(queryParameters: params);
      final start = await http.post(
        startUri,
        headers: {'x-api-key': apiKey.trim()},
      ).timeout(const Duration(seconds: 40));
      if (start.statusCode == 404 || start.statusCode == 405) {
        return _requestWithRetry(
          baseUrl: baseUrl,
          apiKey: apiKey,
          orderNumber: orderNumber,
          tracking: tracking,
        );
      }
      if (start.statusCode < 200 || start.statusCode >= 300) {
        throw Exception(start.body);
      }
      final started = jsonDecode(start.body);
      if (started is! Map) throw Exception('Respuesta inválida del servidor.');
      final jobId = '${started['jobId'] ?? ''}'.trim();
      if (jobId.isEmpty) throw Exception('Railway no devolvió el trabajo de Gmail.');

      // The server keeps working even if this request is interrupted. Repeated
      // WorkManager attempts use the same client_token and resume the same job.
      for (var i = 0; i < 150; i++) {
        final statusUri = Uri.parse(
          '$base/api/gmail/reconstruct/jobs/${Uri.encodeComponent(jobId)}',
        );
        final response = await http.get(
          statusUri,
          headers: {'x-api-key': apiKey.trim()},
        ).timeout(const Duration(seconds: 35));
        if (response.statusCode < 200 || response.statusCode >= 300) {
          throw Exception(response.body);
        }
        final decoded = jsonDecode(response.body);
        if (decoded is! Map) throw Exception('Respuesta inválida del servidor.');
        final status = '${decoded['status'] ?? ''}'.toLowerCase();
        if (status == 'completed') {
          final result = decoded['result'];
          if (result is Map) return Map<String, dynamic>.from(result);
          throw Exception('Railway terminó sin resultado de Gmail.');
        }
        if (status == 'failed') {
          throw Exception('${decoded['error'] ?? 'No se pudo reconstruir desde Gmail.'}');
        }
        await Future<void>.delayed(const Duration(seconds: 2));
      }
      throw TimeoutException('Railway continúa procesando la reconstrucción.');
    } catch (e) {
      // Old backend / temporary job-endpoint failures fall back to the proven
      // direct endpoint. WorkManager can retry the job later if Android stops us.
      if (_transientNetworkError(e) || '$e'.contains('404') || '$e'.contains('405')) {
        return _requestWithRetry(
          baseUrl: baseUrl,
          apiKey: apiKey,
          orderNumber: orderNumber,
          tracking: tracking,
        );
      }
      rethrow;
    }
  }

  static List<Map<String, dynamic>> _backgroundPhotoCandidates(
    Map<String, dynamic> result,
    Set<String> hidden,
  ) {
    final prepared = dynList(result['emailPhotoCandidates'])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .where((e) {
          final url = '${e['url'] ?? ''}'.trim();
          return url.isNotEmpty && !hidden.contains(url);
        })
        .toList();
    if (prepared.isNotEmpty) return prepared;
    return gmailPhotoEntries(
      dynList(result['emailPhotoUrls']).map((e) => '$e').toList(),
      dynList(result['emailAttachmentImages'])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList(),
      hidden,
    );
  }

  static Future<Map<String, dynamic>> _processPackagePhotosInBackground({
    required Map<String, dynamic> result,
    required String baseUrl,
    required String apiKey,
    required String packageId,
    required String tracking,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.reload();
    final rawPackages = prefs.getString('packages') ?? '[]';
    List<Map<String, dynamic>> packages = <Map<String, dynamic>>[];
    try {
      packages = (jsonDecode(rawPackages) as List)
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
    } catch (_) {}

    var index = -1;
    if (packageId.trim().isNotEmpty) {
      index = packages.indexWhere((e) => '${e['id'] ?? ''}' == packageId.trim());
    }
    if (index < 0 && tracking.trim().isNotEmpty) {
      final target = tracking.trim().toLowerCase();
      index = packages.indexWhere(
        (e) => '${e['tracking'] ?? ''}'.trim().toLowerCase() == target,
      );
    }

    final current = index >= 0
        ? Map<String, dynamic>.from(packages[index])
        : <String, dynamic>{};
    final hidden = dynList(current['hiddenEmailPhotoUrls'])
        .map((e) => '$e'.trim())
        .where((e) => e.isNotEmpty)
        .toSet();
    final candidates = _backgroundPhotoCandidates(result, hidden);
    final itemRows = dynList(result['items'])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();

    if (candidates.isEmpty) {
      final processed = <String, dynamic>{
        ...result,
        '_backgroundProcessed': true,
        'gmailOfflinePhotoPaths': <String, String>{},
        'gmailRejectedImages': <Map<String, dynamic>>[],
      };
      if (index >= 0) {
        packages[index] = {
          ...current,
          'gmailStore': '${result['store'] ?? ''}'.trim(),
          'gmailOrderNumber': '${result['orderNumber'] ?? ''}'.trim(),
          'gmailStatus': '${result['status'] ?? ''}'.trim(),
          'gmailEstimatedDelivery': '${result['estimatedDelivery'] ?? ''}'.trim(),
          'emailPhotoUrls': <String>[],
          'emailAttachmentImages': <Map<String, dynamic>>[],
          'gmailOfflinePhotoPaths': <String, String>{},
          'gmailRejectedImages': <Map<String, dynamic>>[],
          'gmailSourceEmails': dynList(result['sourceEmails']).map((e) => '$e').toList(),
          'gmailItems': itemRows,
          'gmailLinkedAt': DateTime.now().toIso8601String(),
        };
        await prefs.setString('packages', jsonEncode(packages));
      }
      return processed;
    }

    try {
      final photoResult = await gmailPrepareProductPhotos(
        baseUrl: baseUrl,
        apiKey: apiKey,
        images: candidates,
        items: itemRows,
      );
      final accepted = dynList(photoResult['accepted'])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      final rejected = dynList(photoResult['rejected'])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      final allAnalysisFailed = accepted.isEmpty &&
          rejected.isNotEmpty &&
          rejected.every((e) => '${e['rejectReason'] ?? ''}' == 'no se pudo analizar');
      if (allAnalysisFailed) {
        return <String, dynamic>{
          ...result,
          '_backgroundProcessed': false,
          '_backgroundPhotoFallback': true,
        };
      }

      final offline = <String, String>{};
      final offlineRaw = photoResult['offlinePaths'];
      if (offlineRaw is Map) {
        offline.addAll(offlineRaw.map((k, v) => MapEntry('$k', '$v')));
      }
      final acceptedUrls = accepted
          .where((e) => '${e['kind']}' == 'remote')
          .map((e) => '${e['url'] ?? ''}'.trim())
          .where((e) => e.isNotEmpty)
          .toList();
      final acceptedAttachments = accepted
          .where((e) => '${e['kind']}' == 'attachment')
          .map((e) => Map<String, dynamic>.from(e))
          .toList();

      final processed = <String, dynamic>{
        ...result,
        'emailPhotoUrls': acceptedUrls,
        'emailAttachmentImages': acceptedAttachments,
        'gmailOfflinePhotoPaths': offline,
        'gmailRejectedImages': rejected,
        '_backgroundProcessed': true,
        '_backgroundPhotoCount': accepted.length,
      };

      if (index >= 0) {
        packages[index] = {
          ...current,
          'gmailStore': '${result['store'] ?? ''}'.trim(),
          'gmailOrderNumber': '${result['orderNumber'] ?? ''}'.trim(),
          'gmailStatus': '${result['status'] ?? ''}'.trim(),
          'gmailEstimatedDelivery': '${result['estimatedDelivery'] ?? ''}'.trim(),
          'emailPhotoUrls': acceptedUrls,
          'emailAttachmentImages': acceptedAttachments,
          'gmailOfflinePhotoPaths': offline,
          'gmailRejectedImages': rejected,
          'gmailSourceEmails': dynList(result['sourceEmails']).map((e) => '$e').toList(),
          'gmailItems': itemRows,
          'gmailLinkedAt': DateTime.now().toIso8601String(),
          'gmailBackgroundProcessedAt': DateTime.now().toIso8601String(),
        };
        await prefs.setString('packages', jsonEncode(packages));
      }
      return processed;
    } catch (_) {
      return <String, dynamic>{
        ...result,
        '_backgroundProcessed': false,
        '_backgroundPhotoFallback': true,
      };
    }
  }

'''
if 'static Future<Map<String, dynamic>> _requestServerJob({' not in bs:
    bs = replace_once(bs, retry_anchor, server_job_helpers + retry_anchor, 'Railway durable job helpers')

# Add packageId to the public reconstruction call.
bs = replace_once(
    bs,
    r'''    String orderNumber = '',
    String tracking = '',
    bool autoAcknowledge = true,
  }) async {
''',
    r'''    String orderNumber = '',
    String tracking = '',
    String packageId = '',
    bool autoAcknowledge = true,
  }) async {
''',
    'package id in Gmail background API',
)

bs = replace_once(
    bs,
    r'''          'orderNumber': order,
          'tracking': track,
        }),
''',
    r'''          'orderNumber': order,
          'tracking': track,
          'packageId': packageId.trim(),
        }),
''',
    'persist package id in pending Gmail job',
)

bs = replace_once(
    bs,
    r'''              'orderNumber': order,
              'tracking': track,
            },
''',
    r'''              'orderNumber': order,
              'tracking': track,
              'packageId': packageId.trim(),
            },
''',
    'pass package id to WorkManager',
)

# Worker uses Railway job endpoint and completes the photo pipeline itself.
execute_start = bs.find("  @pragma('vm:entry-point')\n  static Future<bool> execute(")
if execute_start < 0:
    raise SystemExit('No se encontró GmailBackgroundSearch.execute')
execute_end = bs.find('\n  }\n}\n\nclass NotificationService', execute_start)
if execute_end < 0:
    raise SystemExit('No se encontró cierre de GmailBackgroundSearch.execute')
execute_block = bs[execute_start:execute_end + 5]
execute_block = replace_once(
    execute_block,
    r'''      final result = await _requestWithRetry(
        baseUrl: '${data['baseUrl'] ?? ''}',
        apiKey: '${data['apiKey'] ?? ''}',
        orderNumber: '${data['orderNumber'] ?? ''}',
        tracking: '${data['tracking'] ?? ''}',
      );
''',
    r'''      await NotificationService.initialize(requestPermission: false);
      await NotificationService.publishGmailReconstruction(
        slot: slot,
        tracking: '${data['tracking'] ?? ''}',
        running: true,
      );
      final rawResult = await _requestServerJob(
        baseUrl: '${data['baseUrl'] ?? ''}',
        apiKey: '${data['apiKey'] ?? ''}',
        orderNumber: '${data['orderNumber'] ?? ''}',
        tracking: '${data['tracking'] ?? ''}',
        token: token,
      );
      final result = await _processPackagePhotosInBackground(
        result: rawResult,
        baseUrl: '${data['baseUrl'] ?? ''}',
        apiKey: '${data['apiKey'] ?? ''}',
        packageId: '${data['packageId'] ?? ''}',
        tracking: '${data['tracking'] ?? ''}',
      );
''',
    'worker Railway job + background photo processing',
)
execute_block = replace_once(
    execute_block,
    r'''      await prefs.setString(
        _resultKey(slot),
        jsonEncode({
          'token': token,
          'completedAt': DateTime.now().toIso8601String(),
          'data': result,
        }),
      );
      return true;
''',
    r'''      await prefs.setString(
        _resultKey(slot),
        jsonEncode({
          'token': token,
          'completedAt': DateTime.now().toIso8601String(),
          'data': result,
        }),
      );
      await NotificationService.publishGmailReconstruction(
        slot: slot,
        tracking: '${data['tracking'] ?? ''}',
        photoCount: (result['_backgroundPhotoCount'] as num?)?.toInt() ?? 0,
      );
      return true;
''',
    'background completion notification',
)
execute_block = replace_once(
    execute_block,
    r'''      await prefs.setString(
        _errorKey(slot),
        jsonEncode({
          'token': token,
          'completedAt': DateTime.now().toIso8601String(),
          'error': friendlyError(e),
        }),
      );
      return true;
''',
    r'''      await prefs.setString(
        _errorKey(slot),
        jsonEncode({
          'token': token,
          'completedAt': DateTime.now().toIso8601String(),
          'error': friendlyError(e),
        }),
      );
      try {
        await NotificationService.publishGmailReconstruction(
          slot: slot,
          tracking: '${data['tracking'] ?? ''}',
          failed: true,
        );
      } catch (_) {}
      return true;
''',
    'background failure notification',
)
bs = bs[:execute_start] + execute_block + bs[execute_end + 5:]

# Notification helper.
notification_anchor = r'''  static Future<void> publishPendingCourierChanges() async {
'''
notification_method = r'''  static Future<void> publishGmailReconstruction({
    required String slot,
    String tracking = '',
    int photoCount = 0,
    bool running = false,
    bool failed = false,
  }) async {
    await initialize(requestPermission: false);
    var id = 1700000000;
    for (final code in slot.codeUnits) {
      id = ((id * 31) + code) & 0x7fffffff;
    }
    const android = AndroidNotificationDetails(
      'gmail_reconstruction',
      'Reconstrucciones de Gmail',
      channelDescription: 'Búsquedas y fotos reconstruidas en segundo plano',
      importance: Importance.low,
      priority: Priority.low,
      onlyAlertOnce: true,
    );
    const details = NotificationDetails(android: android);
    final suffix = tracking.trim().isEmpty ? '' : ' · ${tracking.trim()}';
    if (running) {
      await _plugin.show(
        id: id,
        title: 'Paquetería · Reconstruyendo compra',
        body: 'Buscando correos y preparando fotos$suffix',
        notificationDetails: details,
      );
      return;
    }
    await _plugin.show(
      id: id,
      title: failed
          ? 'Paquetería · No se pudo terminar'
          : 'Paquetería · Reconstrucción terminada',
      body: failed
          ? 'Se reintentará cuando vuelva una conexión estable$suffix'
          : '$photoCount foto(s) preparada(s)$suffix',
      notificationDetails: details,
    );
  }

'''
if 'static Future<void> publishGmailReconstruction({' not in bs:
    bs = replace_once(bs, notification_anchor, notification_method + notification_anchor, 'Gmail background notifications')

bg_path.write_text(bs)


# ---------------------------------------------------------------------------
# Package editor: identify the package for WorkManager. If the worker already
# performed the complete photo pipeline, simply hydrate those final values and
# acknowledge; do not OCR/download them a second time.
# ---------------------------------------------------------------------------
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()

ps = replace_once(
    ps,
    r'''        orderNumber: order,
        tracking: track,
        autoAcknowledge: false,
''',
    r'''        orderNumber: order,
        tracking: track,
        packageId: '${widget.existing?['id'] ?? ''}',
        autoAcknowledge: false,
''',
    'package id passed to Gmail background search',
)

processing_anchor = r'''      await _mergeItemsFromEmailImageOcr();
      if (WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) {
'''
processed_guard = r'''      if (data['_backgroundProcessed'] == true) {
        final offlineRaw = data['gmailOfflinePhotoPaths'];
        final rejectedRaw = data['gmailRejectedImages'];
        if (mounted) {
          setState(() {
            emailPhotoUrls = dynList(data['emailPhotoUrls'])
                .map((e) => '$e'.trim())
                .where((e) => e.isNotEmpty)
                .toList();
            emailAttachmentImages = dynList(data['emailAttachmentImages'])
                .whereType<Map>()
                .map((e) => Map<String, dynamic>.from(e))
                .toList();
            if (offlineRaw is Map) {
              gmailOfflinePhotoPaths = offlineRaw.map(
                (k, v) => MapEntry('$k', '$v'),
              );
            }
            gmailRejectedImages = dynList(rejectedRaw)
                .whereType<Map>()
                .map((e) => Map<String, dynamic>.from(e))
                .toList();
            gmailItems = dynList(data['items'])
                .whereType<Map>()
                .map((e) => Map<String, dynamic>.from(e))
                .toList();
          });
        }
        Store.clearListCache('packages');
        await _persistRecoveredGmailSnapshot();
        await GmailBackgroundSearch.acknowledgeFinished(
          orderNumber: gmailOrder.text.trim(),
          tracking: tracking.text.trim(),
        );
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                'Reconstrucción terminada en segundo plano · ${emailPhotoUrls.length + emailAttachmentImages.length} foto(s)',
              ),
            ),
          );
        }
        return;
      }

      await _mergeItemsFromEmailImageOcr();
      if (WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) {
'''
ps = replace_once(ps, processing_anchor, processed_guard, 'hydrate background-processed photos')
packages_path.write_text(ps)

print('Gmail v14 applied: Railway durable jobs + adaptive thumbnails + full WorkManager photo processing on any connected network.')
