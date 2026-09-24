part of 'main.dart';

class WhatsBotPurchaseSyncService {
  static const _secure = FlutterSecureStorage();
  static const _apiKeyName = 'whatsbot_sync_api_key';
  static const _defaultUrl =
      'https://wasbot-backend-production.up.railway.app';

  static String normalizePhone(dynamic value) {
    final digits = '${value ?? ''}'.replaceAll(RegExp(r'[^0-9]'), '');
    return digits;
  }

  static Future<String> apiKey() async =>
      (await _secure.read(key: _apiKeyName) ?? '').trim();

  static Future<void> saveApiKey(String value) async {
    final key = value.trim();
    if (key.isEmpty) {
      await _secure.delete(key: _apiKeyName);
    } else {
      await _secure.write(key: _apiKeyName, value: key);
    }
  }

  static Future<String> backendUrl() async {
    final settings = await Store.settings();
    final raw = '${settings['whatsBotBackendUrl'] ?? ''}'.trim();
    return (raw.isEmpty ? _defaultUrl : raw)
        .replaceAll(RegExp(r'/$'), '');
  }

  static Future<bool> enabled() async {
    final settings = await Store.settings();
    return settings['whatsBotSyncEnabled'] != false;
  }

  static Future<void> configure({
    required bool enabled,
    required String url,
    required String key,
  }) async {
    final settings = await Store.settings();
    settings['whatsBotSyncEnabled'] = enabled;
    settings['whatsBotBackendUrl'] =
        url.trim().isEmpty ? _defaultUrl : url.trim().replaceAll(RegExp(r'/$'), '');
    await Store.saveSettings(settings);
    await saveApiKey(key);
  }

  static String _stableHash(String input) {
    var hash = 2166136261;
    for (final unit in utf8.encode(input)) {
      hash ^= unit;
      hash = (hash * 16777619) & 0x7fffffff;
    }
    return hash.toRadixString(16);
  }

  static Future<int> _pushClients(
    String url,
    String key,
    List<Map<String, dynamic>> clients,
  ) async {
    var pushed = 0;
    var changed = false;
    for (final client in active(clients)) {
      final id = (client['id'] ?? '').toString();
      if (id.isEmpty) continue;
      final external = (client['whatsbotClientSyncId'] ?? '').toString().trim();
      final externalId = external.isEmpty ? 'paqueteria-client-' + id : external;
      final payload = <String, dynamic>{
        'external_id': externalId,
        'name': (client['name'] ?? '').toString().trim(),
        'phone': (client['phone'] ?? '').toString().trim(),
        'source': 'paqueteria',
      };
      final fingerprint = _stableHash(jsonEncode(payload));
      if ((client['whatsbotClientPushHash'] ?? '').toString() == fingerprint) {
        continue;
      }
      try {
        final response = await http
            .post(
              Uri.parse(url + '/api/clients'),
              headers: {
                'Content-Type': 'application/json',
                'x-api-key': key,
              },
              body: jsonEncode(payload),
            )
            .timeout(const Duration(seconds: 20));
        if (response.statusCode == 200 || response.statusCode == 201) {
          try {
            final decoded = jsonDecode(response.body);
            if (decoded is Map && decoded['external_id'] != null) {
              client['whatsbotClientSyncId'] = decoded['external_id'].toString();
            } else {
              client['whatsbotClientSyncId'] = externalId;
            }
          } catch (_) {
            client['whatsbotClientSyncId'] = externalId;
          }
          client['whatsbotClientPushHash'] = fingerprint;
          changed = true;
          pushed++;
        }
      } catch (_) {}
    }
    if (changed) await Store.saveList('clients', clients);
    return pushed;
  }

  static Future<int> _pushPurchases(
    String url,
    String key,
    List<Map<String, dynamic>> purchases,
    List<Map<String, dynamic>> clients,
  ) async {
    var pushed = 0;
    var changed = false;
    final clientsById = <String, Map<String, dynamic>>{
      for (final c in active(clients)) (c['id'] ?? '').toString(): c,
    };

    for (final purchase in active(purchases)) {
      final id = (purchase['id'] ?? '').toString();
      if (id.isEmpty) continue;
      final existingExternal = (purchase['whatsbotSyncId'] ?? '').toString().trim();
      final externalId = existingExternal.isEmpty
          ? 'paqueteria-purchase-' + id
          : existingExternal;
      final client = clientsById[(purchase['clientId'] ?? '').toString()];
      final paths = purchasePhotoPaths(purchase);
      final photoStamp = <String>[];
      for (final path in paths) {
        try {
          final file = File(path);
          if (await file.exists()) {
            final stat = await file.stat();
            photoStamp.add(path + ':' + stat.modified.millisecondsSinceEpoch.toString());
          }
        } catch (_) {}
      }

      final fingerprintPayload = <String, dynamic>{
        'external_id': externalId,
        'client': (client?['id'] ?? '').toString(),
        'name': (client?['name'] ?? '').toString(),
        'phone': (client?['phone'] ?? '').toString(),
        'store': (purchase['store'] ?? '').toString(),
        'description': (purchase['description'] ?? '').toString(),
        'total': number(purchase['total']),
        'orderNumber': (purchase['orderNumber'] ?? '').toString(),
        'items': purchase['items'] ?? const <Map<String, dynamic>>[],
        'ocrText': (purchase['ocrText'] ?? '').toString(),
        'ocrMeta': purchase['ocrMeta'] ?? const <String, dynamic>{},
        'status': (purchase['status'] ?? '').toString(),
        'photos': photoStamp,
      };
      final fingerprint = _stableHash(jsonEncode(fingerprintPayload));
      if ((purchase['whatsbotPurchasePushHash'] ?? '').toString() == fingerprint) {
        continue;
      }

      final photos = <Map<String, String>>[];
      for (final path in paths) {
        try {
          final file = File(path);
          if (!await file.exists()) continue;
          final bytes = await file.readAsBytes();
          if (bytes.length > 8 * 1024 * 1024) continue;
          photos.add({
            'name': file.uri.pathSegments.isEmpty
                ? 'purchase.jpg'
                : file.uri.pathSegments.last,
            'data': base64Encode(bytes),
          });
        } catch (_) {}
      }

      final date = (purchase['date'] ?? '').toString().trim();
      final payload = <String, dynamic>{
        'external_id': externalId,
        'customer_name': (client?['name'] ?? '').toString().trim(),
        'customer_phone': (client?['phone'] ?? '').toString().trim(),
        'title': (purchase['store'] ?? 'Compra').toString(),
        'description': (purchase['description'] ?? '').toString(),
        'store': (purchase['store'] ?? 'Paquetería').toString(),
        'total': number(purchase['total']),
        'order_number': (purchase['orderNumber'] ?? '').toString(),
        'items': purchase['items'] ?? const <Map<String, dynamic>>[],
        'ocr_text': (purchase['ocrText'] ?? '').toString(),
        'ocr_meta': purchase['ocrMeta'] ?? const <String, dynamic>{},
        'created_at': date.isEmpty ? DateTime.now().toUtc().toIso8601String() : date + 'T00:00:00Z',
        'photos': photos,
      };

      try {
        final response = await http
            .post(
              Uri.parse(url + '/api/purchases'),
              headers: {
                'Content-Type': 'application/json',
                'x-api-key': key,
              },
              body: jsonEncode(payload),
            )
            .timeout(const Duration(seconds: 45));
        if (response.statusCode == 200 || response.statusCode == 201) {
          purchase['whatsbotSyncId'] = externalId;
          purchase['whatsbotPurchasePushHash'] = fingerprint;
          changed = true;
          pushed++;
        }
      } catch (_) {}
    }

    if (changed) await Store.saveList('purchases', purchases);
    return pushed;
  }

  static Future<void> _uploadSnapshot(String url, String key) async {
    try {
      final values = await Future.wait([
        Store.list('clients'),
        Store.list('recipients'),
        Store.list('purchases'),
        Store.list('packages'),
        Store.list('payments'),
        Store.list('trips'),
        Store.list('expenses'),
        Store.list('agencyShipments'),
        Store.list('agents'),
        Store.list('agentReports'),
      ]);
      final payload = <String, dynamic>{
        'clients': active(values[0]),
        'recipients': active(values[1]),
        'purchases': active(values[2]),
        'packages': active(values[3]),
        'payments': active(values[4]),
        'trips': active(values[5]),
        'expenses': active(values[6]),
        'agencyShipments': active(values[7]),
        'agents': active(values[8]),
        'agentReports': active(values[9]),
        'updatedAt': DateTime.now().toUtc().toIso8601String(),
      };
      await http
          .put(
            Uri.parse(url + '/api/paqueteria/snapshot'),
            headers: {
              'Content-Type': 'application/json',
              'x-api-key': key,
            },
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 30));
    } catch (_) {}
  }

  static Future<int> _applyRemoteActions(String url, String key) async {
    try {
      final response = await http
          .get(
            Uri.parse(url + '/api/paqueteria/actions'),
            headers: {'x-api-key': key},
          )
          .timeout(const Duration(seconds: 15));
      if (response.statusCode != 200) return 0;
      final decoded = jsonDecode(response.body);
      if (decoded is! List) return 0;

      final packages = await Store.list('packages');
      final payments = await Store.list('payments');
      var packagesChanged = false;
      var paymentsChanged = false;
      var applied = 0;

      for (final raw in decoded) {
        if (raw is! Map) continue;
        final action = Map<String, dynamic>.from(raw);
        final actionId = (action['id'] ?? '').toString();
        final actionType = (action['action_type'] ?? '').toString();
        final payloadRaw = action['payload'];
        if (actionId.isEmpty || payloadRaw is! Map) continue;
        final payload = Map<String, dynamic>.from(payloadRaw);
        var success = false;

        if (actionType == 'package_status') {
          final tracking = (payload['tracking'] ?? '')
              .toString()
              .replaceAll(RegExp(r'\s+'), '')
              .toUpperCase();
          final status = (payload['status'] ?? '').toString().trim();
          if (tracking.isNotEmpty && status.isNotEmpty) {
            final index = packages.indexWhere(
              (p) => (p['tracking'] ?? '')
                  .toString()
                  .replaceAll(RegExp(r'\s+'), '')
                  .toUpperCase() == tracking,
            );
            if (index >= 0) {
              packages[index]['status'] = status;
              packages[index]['whatsbotActionId'] = actionId;
              packages[index]['whatsbotActionAt'] =
                  DateTime.now().toUtc().toIso8601String();
              packagesChanged = true;
              success = true;
            }
          }
        } else if (actionType == 'payment') {
          final clientId = (payload['clientId'] ?? '').toString();
          final amount = number(payload['amount']);
          final duplicate = payments.any(
            (p) => (p['whatsbotActionId'] ?? '').toString() == actionId,
          );
          if (duplicate) {
            success = true;
          } else if (clientId.isNotEmpty && amount > 0) {
            payments.add({
              'id': newId(),
              'clientId': clientId,
              'amount': amount,
              'date': today(),
              'notes': 'Registrado desde WhatsBot',
              'whatsbotActionId': actionId,
              'whatsbotActionAt': DateTime.now().toUtc().toIso8601String(),
              'deleted': false,
            });
            paymentsChanged = true;
            success = true;
          }
        }

        if (success) {
          try {
            final ack = await http
                .post(
                  Uri.parse(url + '/api/paqueteria/actions/' + actionId + '/complete'),
                  headers: {'x-api-key': key},
                )
                .timeout(const Duration(seconds: 10));
            if (ack.statusCode == 200) applied++;
          } catch (_) {}
        }
      }

      if (packagesChanged) await Store.saveList('packages', packages);
      if (paymentsChanged) await Store.saveList('payments', payments);
      return applied;
    } catch (_) {
      return 0;
    }
  }

  static Future<int> syncSilently() async {
    try {
      return await sync();
    } catch (_) {
      return 0;
    }
  }

  static Future<int> sync() async {
    if (!await enabled()) return 0;
    final key = await apiKey();
    if (key.isEmpty) return 0;
    final url = await backendUrl();

    List<Map<String, dynamic>> remoteClients = [];
    try {
      final clientResponse = await http
          .get(
            Uri.parse('$url/api/clients'),
            headers: {'x-api-key': key},
          )
          .timeout(const Duration(seconds: 15));
      if (clientResponse.statusCode == 200) {
        final clientDecoded = jsonDecode(clientResponse.body);
        if (clientDecoded is List) {
          remoteClients = clientDecoded
              .whereType<Map>()
              .map((e) => Map<String, dynamic>.from(e))
              .toList();
        }
      }
    } catch (_) {}

    final response = await http
        .get(
          Uri.parse('$url/api/purchases'),
          headers: {'x-api-key': key},
        )
        .timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('WhatsBot respondió ${response.statusCode}');
    }

    final decoded = jsonDecode(response.body);
    if (decoded is! List) return 0;
    final remote = decoded
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();

    final clients = await Store.list('clients');
    final purchases = await Store.list('purchases');
    final settings = await Store.settings();
    final commission = number(settings['purchaseCommissionPct']);
    var imported = 0;
    var importedClients = 0;
    var clientsChanged = false;

    for (final item in remoteClients.reversed) {
      final externalId = '${item['external_id'] ?? item['id'] ?? ''}'.trim();
      if (externalId.isEmpty) continue;

      final name = '${item['name'] ?? ''}'.trim();
      final phone = '${item['phone'] ?? ''}'.trim();
      final normalized = normalizePhone(phone);

      Map<String, dynamic>? client;
      for (final c in active(clients)) {
        if ('${c['whatsbotClientSyncId'] ?? ''}' == externalId) {
          client = c;
          break;
        }
      }
      if (client == null && normalized.isNotEmpty) {
        for (final c in active(clients)) {
          if (normalizePhone(c['phone']) == normalized) {
            client = c;
            break;
          }
        }
      }
      if (client == null && name.isNotEmpty) {
        final target = name.toLowerCase();
        for (final c in active(clients)) {
          if ('${c['name'] ?? ''}'.trim().toLowerCase() == target) {
            client = c;
            break;
          }
        }
      }

      if (client == null) {
        clients.add({
          'id': newId(),
          'name': name.isEmpty ? 'Cliente WhatsApp' : name,
          'phone': phone,
          'email': '',
          'notes': 'Creado automáticamente desde un contacto de WhatsApp',
          'whatsbotClientSyncId': externalId,
          'source': 'whatsbot',
          'deleted': false,
        });
        clientsChanged = true;
        importedClients++;
      } else {
        var changed = false;
        if ('${client['whatsbotClientSyncId'] ?? ''}' != externalId) {
          client['whatsbotClientSyncId'] = externalId;
          changed = true;
        }
        if (name.isNotEmpty && '${client['name'] ?? ''}'.trim().isEmpty) {
          client['name'] = name;
          changed = true;
        }
        if (phone.isNotEmpty && '${client['phone'] ?? ''}'.trim().isEmpty) {
          client['phone'] = phone;
          changed = true;
        }
        if (changed) {
          clientsChanged = true;
          importedClients++;
        }
      }
    }

    for (final item in remote.reversed) {
      final externalId = '${item['external_id'] ?? item['id'] ?? ''}'.trim();
      if (externalId.isEmpty) continue;
      final already = purchases.any(
        (p) => '${p['whatsbotSyncId'] ?? ''}' == externalId,
      );
      if (already) continue;

      final name = '${item['customer_name'] ?? ''}'.trim();
      final phone = '${item['customer_phone'] ?? ''}'.trim();
      final normalized = normalizePhone(phone);

      Map<String, dynamic>? client;
      if (normalized.isNotEmpty) {
        for (final c in active(clients)) {
          if (normalizePhone(c['phone']) == normalized) {
            client = c;
            break;
          }
        }
      }
      if (client == null && name.isNotEmpty) {
        final target = name.toLowerCase();
        for (final c in active(clients)) {
          if ('${c['name'] ?? ''}'.trim().toLowerCase() == target) {
            client = c;
            break;
          }
        }
      }
      final unassigned = client == null && name.isEmpty && normalized.isEmpty;
      if (client == null && !unassigned) {
        client = {
          'id': newId(),
          'name': name.isEmpty ? 'Cliente WhatsBot' : name,
          'phone': phone,
          'email': '',
          'notes': 'Creado automáticamente desde WhatsBot',
          'deleted': false,
        };
        clients.add(client);
        clientsChanged = true;
      } else if (client != null &&
          '${client['phone'] ?? ''}'.trim().isEmpty &&
          phone.isNotEmpty) {
        client['phone'] = phone;
        clientsChanged = true;
      }

      final photos = <String>[];
      final photoUrls = item['photo_urls'];
      if (photoUrls is List) {
        for (var i = 0; i < photoUrls.length; i++) {
          final rawPath = '${photoUrls[i]}'.trim();
          if (rawPath.isEmpty) continue;
          try {
            final photoUri = Uri.parse(url).resolve(rawPath);
            final imageResponse = await http
                .get(photoUri, headers: {'x-api-key': key})
                .timeout(const Duration(seconds: 20));
            if (imageResponse.statusCode != 200 ||
                imageResponse.bodyBytes.isEmpty) {
              continue;
            }
            final docs = await getApplicationDocumentsDirectory();
            final contentType =
                imageResponse.headers['content-type']?.toLowerCase() ?? '';
            final ext = contentType.contains('png')
                ? 'png'
                : contentType.contains('webp')
                    ? 'webp'
                    : 'jpg';
            final safe = externalId.replaceAll(
              RegExp(r'[^A-Za-z0-9_-]'),
              '_',
            );
            final file = File(
              '${docs.path}/whatsbot_purchase_${safe}_$i.$ext',
            );
            await file.writeAsBytes(imageResponse.bodyBytes, flush: true);
            photos.add(file.path);
          } catch (_) {}
        }
      }

      final total = number(item['total']);
      final clientTotal = unassigned ? 0.0 : total * (1 + commission / 100);
      final clientId = client == null ? '' : '${client['id']}';

      final remoteItems = <Map<String, dynamic>>[];
      final rawItems = item['items'];
      if (rawItems is List) {
        for (final raw in rawItems) {
          if (raw is! Map) continue;
          final row = Map<String, dynamic>.from(raw);
          row['id'] = '${row['id'] ?? newId()}';
          row['name'] = '${row['name'] ?? ''}'.trim();
          row['price'] = number(row['price']);
          row['qty'] = number(row['qty']) <= 0 ? 1.0 : number(row['qty']);
          if (clientId.isNotEmpty &&
              '${row['clientId'] ?? ''}'.trim().isEmpty) {
            row['clientId'] = clientId;
          }
          remoteItems.add(row);
        }
      }

      final remoteOcrMeta = item['ocr_meta'] is Map
          ? Map<String, dynamic>.from(item['ocr_meta'] as Map)
          : <String, dynamic>{};

      final created =
          DateTime.tryParse('${item['created_at'] ?? ''}')?.toLocal();
      final dateText = created == null
          ? today()
          : '${created.year}-${created.month.toString().padLeft(2, '0')}-${created.day.toString().padLeft(2, '0')}';
      final title = '${item['title'] ?? ''}'.trim();
      final description = '${item['description'] ?? ''}'.trim();

      purchases.add({
        'id': newId(),
        'clientId': clientId,
        'type': 'Online',
        'store': '${item['store'] ?? ''}'.trim().isEmpty
            ? (title.isEmpty ? 'WhatsBot' : title)
            : '${item['store']}',
        'description': description.isEmpty ? title : description,
        'total': total,
        'commissionPct': commission,
        'clientTotal': clientTotal,
        'orderNumber': '${item['order_number'] ?? ''}'.trim(),
        'date': dateText,
        'status': 'Comprado',
        'receiptPath': photos.isEmpty ? '' : photos.first,
        'photoPath': photos.isEmpty ? '' : photos.first,
        'photoPaths': photos,
        'ocrText': '${item['ocr_text'] ?? ''}',
        'ocrMeta': remoteOcrMeta,
        'items': remoteItems,
        'allocations': unassigned
            ? const <Map<String, dynamic>>[]
            : [
                {
                  'clientId': clientId,
                  'subtotal': total,
                  'extras': 0.0,
                  'commissionPct': commission,
                  'total': clientTotal,
                  'itemIds': remoteItems
                      .map((e) => '${e['id'] ?? ''}')
                      .where((e) => e.isNotEmpty)
                      .toList(),
                }
              ],
        'unassigned': unassigned,
        'whatsbotSyncId': externalId,
        'whatsbotRemoteId': item['id'],
        'source': 'whatsbot',
        'deleted': false,
      });
      imported++;
    }

    if (clientsChanged) await Store.saveList('clients', clients);
    if (imported > 0) await Store.saveList('purchases', purchases);

    final pushedClients = await _pushClients(url, key, clients);
    final pushedPurchases = await _pushPurchases(url, key, purchases, clients);
    final appliedActions = await _applyRemoteActions(url, key);
    await _uploadSnapshot(url, key);

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      'whatsbot_purchase_last_sync',
      DateTime.now().toIso8601String(),
    );
    await prefs.setString(
      'whatsbot_combo_last_sync',
      DateTime.now().toIso8601String(),
    );
    return imported + importedClients + pushedClients + pushedPurchases + appliedActions;
  }
}
