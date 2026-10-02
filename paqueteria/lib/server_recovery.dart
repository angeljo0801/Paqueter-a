part of 'main.dart';

class PaqueteriaServerRecoveryService {
  static const _markerKey = 'server_recovery_v252_completed';
  static const _statusKey = 'server_recovery_v252_status';

  static Future<Map<String, int>> restoreIfLocalEmpty() async {
    final prefs = await SharedPreferences.getInstance();
    if (prefs.getBool(_markerKey) == true) {
      return _localCounts();
    }

    if (!await WhatsBotPurchaseSyncService.enabled()) {
      return _localCounts();
    }

    final existingClients = active(await Store.list('clients'));
    final existingPurchases = active(await Store.list('purchases'));
    if (existingClients.isNotEmpty || existingPurchases.isNotEmpty) {
      return _localCounts();
    }

    final result = await restoreCoreData();
    final recovered = (result['clients'] ?? 0) +
        (result['purchases'] ?? 0) +
        (result['packages'] ?? 0);
    if (recovered > 0) {
      await prefs.setBool(_markerKey, true);
      await prefs.setString(
        _statusKey,
        jsonEncode({
          ...result,
          'completedAt': DateTime.now().toUtc().toIso8601String(),
        }),
      );
    }
    return result;
  }

  static Future<Map<String, int>> restoreCoreData() async {
    final key = await WhatsBotPurchaseSyncService.apiKey();
    if (key.trim().isEmpty) return _localCounts();

    final url = await WhatsBotPurchaseSyncService.backendUrl();
    final headers = {'x-api-key': key};

    // 1) Recover the full Paqueteria snapshot first when it is still available.
    // This preserves original fields such as allocations, commissions, payments,
    // trips, agents, recipients and other business data.
    try {
      final snapshotResponse = await http
          .get(Uri.parse('$url/api/paqueteria/snapshot'), headers: headers)
          .timeout(const Duration(seconds: 15));
      if (snapshotResponse.statusCode == 200) {
        final decoded = jsonDecode(snapshotResponse.body);
        if (decoded is Map) {
          final payloadRaw = decoded['payload'];
          if (payloadRaw is Map) {
            final payload = Map<String, dynamic>.from(payloadRaw);
            for (final listKey in const [
              'clients',
              'recipients',
              'purchases',
              'packages',
              'payments',
              'trips',
              'expenses',
              'agencyShipments',
              'agents',
              'agentReports',
            ]) {
              await _mergeSnapshotList(listKey, payload[listKey]);
            }
          }
        }
      }
    } catch (_) {}

    // 2) Recover the independent sync tables. These survive even if the latest
    // business snapshot was replaced or became empty.
    final remoteClients = await _getList(url, headers, '/api/clients');
    var clients = await Store.list('clients');
    var clientsChanged = false;

    for (final item in remoteClients) {
      final externalId = '${item['external_id'] ?? item['id'] ?? ''}'.trim();
      if (externalId.isEmpty) continue;
      final candidateId = _idFromExternal('paqueteria-client-', externalId);
      final phone = '${item['phone'] ?? ''}'.trim();
      final name = '${item['name'] ?? ''}'.trim();

      var index = clients.indexWhere(
        (row) => '${row['whatsbotClientSyncId'] ?? ''}'.trim() == externalId,
      );
      if (index < 0 && candidateId.isNotEmpty) {
        index = clients.indexWhere((row) => '${row['id'] ?? ''}' == candidateId);
      }
      if (index < 0 && phone.isNotEmpty) {
        final normalized = WhatsBotPurchaseSyncService.normalizePhone(phone);
        index = clients.indexWhere(
          (row) =>
              WhatsBotPurchaseSyncService.normalizePhone(row['phone']) == normalized,
        );
      }

      if (index >= 0) {
        final row = clients[index];
        if ('${row['whatsbotClientSyncId'] ?? ''}'.trim().isEmpty) {
          row['whatsbotClientSyncId'] = externalId;
          clientsChanged = true;
        }
        if ('${row['name'] ?? ''}'.trim().isEmpty && name.isNotEmpty) {
          row['name'] = name;
          clientsChanged = true;
        }
        if ('${row['phone'] ?? ''}'.trim().isEmpty && phone.isNotEmpty) {
          row['phone'] = phone;
          clientsChanged = true;
        }
        if (row['deleted'] == true) {
          row['deleted'] = false;
          row.remove('deletedAt');
          clientsChanged = true;
        }
      } else {
        clients.add({
          'id': candidateId.isEmpty ? newId() : candidateId,
          'name': name.isEmpty ? 'Cliente recuperado' : name,
          'phone': phone,
          'email': '',
          'notes': 'Recuperado desde Railway/WhatsBot',
          'whatsbotClientSyncId': externalId,
          'source': 'server_recovery',
          'deleted': false,
        });
        clientsChanged = true;
      }
    }

    if (clientsChanged) {
      await Store.saveList('clients', clients);
    }

    final remotePurchases = await _getList(url, headers, '/api/purchases');
    clients = await Store.list('clients');
    var purchases = await Store.list('purchases');
    final settings = await Store.settings();
    final defaultCommission = number(settings['purchaseCommissionPct']);
    var purchasesChanged = false;

    for (final item in remotePurchases) {
      final externalId = '${item['external_id'] ?? item['id'] ?? ''}'.trim();
      if (externalId.isEmpty) continue;
      final candidateId = _idFromExternal('paqueteria-purchase-', externalId);

      var index = purchases.indexWhere(
        (row) => '${row['whatsbotSyncId'] ?? ''}'.trim() == externalId,
      );
      if (index < 0 && candidateId.isNotEmpty) {
        index = purchases.indexWhere((row) => '${row['id'] ?? ''}' == candidateId);
      }

      if (index >= 0) {
        final row = purchases[index];
        if ('${row['whatsbotSyncId'] ?? ''}'.trim().isEmpty) {
          row['whatsbotSyncId'] = externalId;
          purchasesChanged = true;
        }
        if (row['whatsbotRemoteId'] == null && item['id'] != null) {
          row['whatsbotRemoteId'] = item['id'];
          purchasesChanged = true;
        }
        if (row['deleted'] == true) {
          row['deleted'] = false;
          row.remove('deletedAt');
          purchasesChanged = true;
        }
        continue;
      }

      final customerName = '${item['customer_name'] ?? ''}'.trim();
      final customerPhone = '${item['customer_phone'] ?? ''}'.trim();
      final client = _findClient(clients, customerName, customerPhone);
      final clientId = client == null ? '' : '${client['id'] ?? ''}';
      final total = number(item['total']);
      final commission = defaultCommission;
      final clientTotal = clientId.isEmpty
          ? 0.0
          : total * (1 + commission / 100.0);

      final remoteItems = <Map<String, dynamic>>[];
      final rawItems = item['items'];
      if (rawItems is List) {
        for (final raw in rawItems) {
          if (raw is! Map) continue;
          final row = Map<String, dynamic>.from(raw);
          row['id'] = '${row['id'] ?? newId()}';
          if (clientId.isNotEmpty && '${row['clientId'] ?? ''}'.trim().isEmpty) {
            row['clientId'] = clientId;
          }
          remoteItems.add(row);
        }
      }

      final created = DateTime.tryParse('${item['created_at'] ?? ''}')?.toLocal();
      final dateText = created == null
          ? today()
          : '${created.year}-${created.month.toString().padLeft(2, '0')}-${created.day.toString().padLeft(2, '0')}';
      final title = '${item['title'] ?? ''}'.trim();
      final store = '${item['store'] ?? ''}'.trim();
      final description = '${item['description'] ?? ''}'.trim();
      final ocrMeta = item['ocr_meta'] is Map
          ? Map<String, dynamic>.from(item['ocr_meta'] as Map)
          : <String, dynamic>{};

      purchases.add({
        'id': candidateId.isEmpty ? newId() : candidateId,
        'clientId': clientId,
        'type': 'Online',
        'store': store.isEmpty ? (title.isEmpty ? 'WhatsBot' : title) : store,
        'description': description.isEmpty ? title : description,
        'total': total,
        'commissionPct': commission,
        'clientTotal': clientTotal,
        'orderNumber': '${item['order_number'] ?? ''}'.trim(),
        'date': dateText,
        'status': 'Comprado',
        'receiptPath': '',
        'photoPath': '',
        'photoPaths': <String>[],
        'ocrText': '${item['ocr_text'] ?? ''}',
        'ocrMeta': ocrMeta,
        'items': remoteItems,
        'allocations': clientId.isEmpty
            ? <Map<String, dynamic>>[]
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
        'unassigned': clientId.isEmpty,
        'whatsbotSyncId': externalId,
        'whatsbotRemoteId': item['id'],
        // Deliberately do not set whatsbotRemoteUpdatedAt here. The normal
        // sync can then make a second pass and download any server photos.
        'source': 'server_recovery',
        'deleted': false,
      });
      purchasesChanged = true;
    }

    if (purchasesChanged) {
      await Store.saveList('purchases', purchases);
    }

    final remotePackages = await _getList(url, headers, '/api/packages');
    clients = await Store.list('clients');
    purchases = await Store.list('purchases');
    var packages = await Store.list('packages');
    var packagesChanged = false;

    for (final item in remotePackages) {
      final externalId = '${item['external_id'] ?? item['id'] ?? ''}'.trim();
      final tracking = '${item['tracking'] ?? ''}'.trim();
      if (externalId.isEmpty || tracking.isEmpty) continue;
      final candidateId = _idFromExternal('paqueteria-package-', externalId);

      var index = packages.indexWhere(
        (row) => '${row['whatsbotPackageSyncId'] ?? ''}'.trim() == externalId,
      );
      if (index < 0 && candidateId.isNotEmpty) {
        index = packages.indexWhere((row) => '${row['id'] ?? ''}' == candidateId);
      }
      if (index < 0) {
        final normalizedTracking = tracking.replaceAll(RegExp(r'\s+'), '').toUpperCase();
        index = packages.indexWhere(
          (row) => '${row['tracking'] ?? ''}'
                  .replaceAll(RegExp(r'\s+'), '')
                  .toUpperCase() ==
              normalizedTracking,
        );
      }

      if (index >= 0) {
        final row = packages[index];
        if ('${row['whatsbotPackageSyncId'] ?? ''}'.trim().isEmpty) {
          row['whatsbotPackageSyncId'] = externalId;
          packagesChanged = true;
        }
        if (row['whatsbotPackageRemoteId'] == null && item['id'] != null) {
          row['whatsbotPackageRemoteId'] = item['id'];
          packagesChanged = true;
        }
        if (row['deleted'] == true) {
          row['deleted'] = false;
          row.remove('deletedAt');
          packagesChanged = true;
        }
        continue;
      }

      final clientExternal = '${item['client_external_id'] ?? ''}'.trim();
      final clientName = '${item['client_name'] ?? ''}'.trim();
      final clientPhone = '${item['client_phone'] ?? ''}'.trim();
      final client = _findClient(
        clients,
        clientName,
        clientPhone,
        externalId: clientExternal,
      );

      final purchaseExternal = '${item['purchase_external_id'] ?? ''}'.trim();
      Map<String, dynamic>? purchase;
      if (purchaseExternal.isNotEmpty) {
        for (final row in active(purchases)) {
          final localId = '${row['id'] ?? ''}';
          final synced = '${row['whatsbotSyncId'] ?? ''}'.trim();
          if (synced == purchaseExternal ||
              localId == purchaseExternal ||
              'paqueteria-purchase-$localId' == purchaseExternal) {
            purchase = row;
            break;
          }
        }
      }

      packages.add({
        'id': candidateId.isEmpty ? newId() : candidateId,
        'tracking': tracking,
        'carrier': '${item['carrier'] ?? 'Auto / Otro'}',
        'clientId': client?['id']?.toString(),
        'purchaseId': purchase?['id']?.toString(),
        'recipientId': '${item['recipient_id'] ?? ''}'.trim().isEmpty
            ? null
            : '${item['recipient_id']}',
        'weightUs': number(item['weight_us']),
        'weightCu': number(item['weight_cu']),
        'billWeight': number(item['bill_weight']),
        'status': '${item['status'] ?? 'Tracking creado'}',
        'notes': '${item['notes'] ?? ''}',
        'photoPaths': <String>[],
        'photoPath': '',
        'receivedAt': '${item['received_at'] ?? ''}'.trim().isEmpty
            ? null
            : '${item['received_at']}',
        'whatsbotPackageSyncId': externalId,
        'whatsbotPackageRemoteId': item['id'],
        'source': 'server_recovery',
        'deleted': false,
      });
      packagesChanged = true;
    }

    if (packagesChanged) {
      await Store.saveList('packages', packages);
    }

    return _localCounts();
  }

  static Future<void> _mergeSnapshotList(String key, dynamic remote) async {
    final rows = _mapList(remote);
    if (rows.isEmpty) return;

    final local = await Store.list(key);
    var changed = false;
    for (final row in rows) {
      final id = '${row['id'] ?? ''}'.trim();
      final index = id.isEmpty
          ? -1
          : local.indexWhere((existing) => '${existing['id'] ?? ''}' == id);
      if (index < 0) {
        local.add(Map<String, dynamic>.from(row));
        changed = true;
      }
    }
    if (changed) await Store.saveList(key, local);
  }

  static Future<List<Map<String, dynamic>>> _getList(
    String url,
    Map<String, String> headers,
    String path,
  ) async {
    try {
      final response = await http
          .get(Uri.parse('$url$path'), headers: headers)
          .timeout(const Duration(seconds: 20));
      if (response.statusCode != 200) return <Map<String, dynamic>>[];
      return _mapList(jsonDecode(response.body));
    } catch (_) {
      return <Map<String, dynamic>>[];
    }
  }

  static List<Map<String, dynamic>> _mapList(dynamic value) {
    if (value is! List) return <Map<String, dynamic>>[];
    return value
        .whereType<Map>()
        .map((row) => Map<String, dynamic>.from(row))
        .toList();
  }

  static String _idFromExternal(String prefix, String externalId) {
    if (!externalId.startsWith(prefix)) return '';
    final id = externalId.substring(prefix.length).trim();
    return id;
  }

  static Map<String, dynamic>? _findClient(
    List<Map<String, dynamic>> clients,
    String name,
    String phone, {
    String externalId = '',
  }) {
    if (externalId.isNotEmpty) {
      for (final row in active(clients)) {
        final localId = '${row['id'] ?? ''}';
        final synced = '${row['whatsbotClientSyncId'] ?? ''}'.trim();
        if (synced == externalId ||
            localId == externalId ||
            'paqueteria-client-$localId' == externalId) {
          return row;
        }
      }
    }

    if (phone.isNotEmpty) {
      final normalized = WhatsBotPurchaseSyncService.normalizePhone(phone);
      for (final row in active(clients)) {
        if (WhatsBotPurchaseSyncService.normalizePhone(row['phone']) == normalized) {
          return row;
        }
      }
    }

    if (name.isNotEmpty) {
      final target = name.trim().toLowerCase();
      final matches = active(clients)
          .where(
            (row) => '${row['name'] ?? ''}'.trim().toLowerCase() == target,
          )
          .toList();
      if (matches.length == 1) return matches.first;
    }

    return null;
  }

  static Future<Map<String, int>> _localCounts() async {
    final values = await Future.wait([
      Store.list('clients'),
      Store.list('purchases'),
      Store.list('packages'),
    ]);
    return {
      'clients': active(values[0]).length,
      'purchases': active(values[1]).length,
      'packages': active(values[2]).length,
    };
  }
}
