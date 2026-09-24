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
          'notes': 'Creado desde un contacto aprobado en WhatsBot',
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
      if (client == null) {
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
      } else if ('${client['phone'] ?? ''}'.trim().isEmpty &&
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
      final clientTotal = total * (1 + commission / 100);
      final clientId = '${client['id']}';
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
        'orderNumber': '',
        'date': dateText,
        'status': 'Comprado',
        'receiptPath': photos.isEmpty ? '' : photos.first,
        'photoPath': photos.isEmpty ? '' : photos.first,
        'photoPaths': photos,
        'ocrText': '',
        'ocrMeta': const <String, dynamic>{},
        'items': const <Map<String, dynamic>>[],
        'allocations': [
          {
            'clientId': clientId,
            'subtotal': total,
            'extras': 0.0,
            'commissionPct': commission,
            'total': clientTotal,
            'itemIds': const <String>[],
          }
        ],
        'unassigned': false,
        'whatsbotSyncId': externalId,
        'whatsbotRemoteId': item['id'],
        'source': 'whatsbot',
        'deleted': false,
      });
      imported++;
    }

    if (clientsChanged) await Store.saveList('clients', clients);
    if (imported > 0) await Store.saveList('purchases', purchases);

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      'whatsbot_purchase_last_sync',
      DateTime.now().toIso8601String(),
    );
    return imported + importedClients;
  }
}
