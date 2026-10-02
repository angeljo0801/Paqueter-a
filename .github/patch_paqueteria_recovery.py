from pathlib import Path

sync = Path('app/lib/whatsbot_sync.dart')
s = sync.read_text()
marker = "  static Future<int> syncSilently() async {"
if 'recoverFromServerOnly' not in s:
    method = r'''
  static Future<Map<String, int>> recoverFromServerOnly() async {
    if (!await enabled()) {
      throw Exception('La sincronización con WhatsBot está desactivada.');
    }
    final key = await apiKey();
    if (key.isEmpty) {
      throw Exception('Falta la APP_API_KEY de WhatsBot.');
    }
    final url = await backendUrl();

    final clientsResponse = await http
        .get(Uri.parse('$url/api/clients'), headers: {'x-api-key': key})
        .timeout(const Duration(seconds: 20));
    if (clientsResponse.statusCode != 200) {
      throw Exception('Clientes: servidor respondió ${clientsResponse.statusCode}.');
    }

    final purchasesResponse = await http
        .get(Uri.parse('$url/api/purchases'), headers: {'x-api-key': key})
        .timeout(const Duration(seconds: 20));
    if (purchasesResponse.statusCode != 200) {
      throw Exception('Compras: servidor respondió ${purchasesResponse.statusCode}.');
    }

    final clientsDecoded = jsonDecode(clientsResponse.body);
    final purchasesDecoded = jsonDecode(purchasesResponse.body);
    if (clientsDecoded is! List || purchasesDecoded is! List) {
      throw Exception('El servidor devolvió un formato inesperado.');
    }

    final remoteClients = clientsDecoded
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    final remotePurchases = purchasesDecoded
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();

    final clients = await Store.list('clients');
    var recoveredClients = 0;

    Map<String, dynamic>? findClient(String name, String phone) {
      final normalized = normalizePhone(phone);
      if (normalized.isNotEmpty) {
        for (final row in active(clients)) {
          if (normalizePhone(row['phone']) == normalized) return row;
        }
      }
      final target = name.trim().toLowerCase();
      if (target.isNotEmpty) {
        for (final row in active(clients)) {
          if ('${row['name'] ?? ''}'.trim().toLowerCase() == target) return row;
        }
      }
      return null;
    }

    for (final item in remoteClients.reversed) {
      final externalId = '${item['external_id'] ?? item['id'] ?? ''}'.trim();
      if (externalId.isEmpty) continue;
      final name = '${item['name'] ?? ''}'.trim();
      final phone = '${item['phone'] ?? ''}'.trim();

      Map<String, dynamic>? client;
      for (final row in active(clients)) {
        if ('${row['whatsbotClientSyncId'] ?? ''}'.trim() == externalId) {
          client = row;
          break;
        }
      }
      client ??= findClient(name, phone);

      if (client == null) {
        clients.add({
          'id': newId(),
          'name': name.isEmpty ? 'Cliente recuperado' : name,
          'phone': phone,
          'email': '',
          'notes': 'Recuperado desde Railway/WhatsBot',
          'whatsbotClientSyncId': externalId,
          'source': 'railway_recovery',
          'deleted': false,
        });
      } else {
        client['deleted'] = false;
        client.remove('deletedAt');
        client['whatsbotClientSyncId'] = externalId;
        if (name.isNotEmpty) client['name'] = name;
        if (phone.isNotEmpty) client['phone'] = phone;
      }
      recoveredClients++;
    }

    // Guardar los clientes antes de procesar compras o fotos.
    await Store.saveList('clients', clients);

    final purchases = await Store.list('purchases');
    final settings = await Store.settings();
    final defaultCommission = number(settings['purchaseCommissionPct']);
    var recoveredPurchases = 0;

    for (final item in remotePurchases.reversed) {
      final externalId = '${item['external_id'] ?? item['id'] ?? ''}'.trim();
      if (externalId.isEmpty) continue;

      final name = '${item['customer_name'] ?? ''}'.trim();
      final phone = '${item['customer_phone'] ?? ''}'.trim();
      var client = findClient(name, phone);
      if (client == null && (name.isNotEmpty || phone.isNotEmpty)) {
        client = {
          'id': newId(),
          'name': name.isEmpty ? 'Cliente recuperado' : name,
          'phone': phone,
          'email': '',
          'notes': 'Recuperado desde una compra en Railway/WhatsBot',
          'source': 'railway_recovery',
          'deleted': false,
        };
        clients.add(client);
      }

      final existingIndex = purchases.indexWhere(
        (p) => '${p['whatsbotSyncId'] ?? ''}'.trim() == externalId,
      );
      final existing = existingIndex >= 0 ? purchases[existingIndex] : null;
      final total = number(item['total']);
      final commission = existing == null
          ? defaultCommission
          : number(existing['commissionPct']);
      final clientId = client == null ? '' : '${client['id']}';
      final unassigned = clientId.isEmpty;

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
      final description = '${item['description'] ?? ''}'.trim();

      final incoming = <String, dynamic>{
        'id': existing?['id'] ?? newId(),
        'clientId': clientId,
        'type': existing?['type'] ?? 'Online',
        'store': '${item['store'] ?? ''}'.trim().isEmpty
            ? (title.isEmpty ? 'WhatsBot' : title)
            : '${item['store']}',
        'description': description.isEmpty ? title : description,
        'total': total,
        'commissionPct': commission,
        'clientTotal': unassigned ? 0.0 : total * (1 + commission / 100),
        'orderNumber': '${item['order_number'] ?? ''}'.trim(),
        'date': dateText,
        'status': existing?['status'] ?? 'Comprado',
        'receiptPath': existing?['receiptPath'] ?? '',
        'photoPath': existing?['photoPath'] ?? '',
        'photoPaths': existing == null
            ? <String>[]
            : ((existing['photoPaths'] as List?) ?? const <dynamic>[]),
        'ocrText': '${item['ocr_text'] ?? ''}',
        'ocrMeta': item['ocr_meta'] is Map
            ? Map<String, dynamic>.from(item['ocr_meta'] as Map)
            : <String, dynamic>{},
        'items': remoteItems,
        'allocations': unassigned
            ? const <Map<String, dynamic>>[]
            : [
                {
                  'clientId': clientId,
                  'subtotal': total,
                  'extras': 0.0,
                  'commissionPct': commission,
                  'total': total * (1 + commission / 100),
                  'itemIds': remoteItems
                      .map((e) => '${e['id'] ?? ''}')
                      .where((e) => e.isNotEmpty)
                      .toList(),
                }
              ],
        'unassigned': unassigned,
        'whatsbotSyncId': externalId,
        'whatsbotRemoteId': item['id'],
        'whatsbotRemoteUpdatedAt': '${item['updated_at'] ?? ''}',
        'source': 'railway_recovery',
        'deleted': false,
      };

      if (existingIndex >= 0) {
        purchases[existingIndex] = {...purchases[existingIndex], ...incoming};
      } else {
        purchases.add(incoming);
      }
      recoveredPurchases++;
    }

    // Guardar clientes creados desde compras y compras ANTES de fotos.
    await Store.saveList('clients', clients);
    await Store.saveList('purchases', purchases);

    var recoveredPhotos = 0;
    for (final item in remotePurchases) {
      final externalId = '${item['external_id'] ?? item['id'] ?? ''}'.trim();
      if (externalId.isEmpty) continue;
      final index = purchases.indexWhere(
        (p) => '${p['whatsbotSyncId'] ?? ''}'.trim() == externalId,
      );
      if (index < 0) continue;
      final rawUrls = item['photo_urls'];
      if (rawUrls is! List || rawUrls.isEmpty) continue;

      final paths = <String>[];
      for (var i = 0; i < rawUrls.length; i++) {
        final rawPath = '${rawUrls[i]}'.trim();
        if (rawPath.isEmpty) continue;
        try {
          final imageResponse = await http
              .get(Uri.parse(url).resolve(rawPath), headers: {'x-api-key': key})
              .timeout(const Duration(seconds: 20));
          if (imageResponse.statusCode != 200 || imageResponse.bodyBytes.isEmpty) {
            continue;
          }
          final docs = await getApplicationDocumentsDirectory();
          final contentType = imageResponse.headers['content-type']?.toLowerCase() ?? '';
          final ext = contentType.contains('png')
              ? 'png'
              : contentType.contains('webp')
                  ? 'webp'
                  : 'jpg';
          final safe = externalId.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');
          final file = File('${docs.path}/recovered_purchase_${safe}_$i.$ext');
          await file.writeAsBytes(imageResponse.bodyBytes, flush: true);
          paths.add(file.path);
          recoveredPhotos++;
        } catch (_) {}
      }

      if (paths.isNotEmpty) {
        purchases[index]['photoPaths'] = paths;
        purchases[index]['photoPath'] = paths.first;
        purchases[index]['receiptPath'] = paths.first;
        await Store.saveList('purchases', purchases);
      }
    }

    return {
      'serverClients': remoteClients.length,
      'serverPurchases': remotePurchases.length,
      'clients': recoveredClients,
      'purchases': recoveredPurchases,
      'photos': recoveredPhotos,
    };
  }

'''
    if marker not in s:
        raise SystemExit('No se encontró syncSilently() en whatsbot_sync.dart')
    s = s.replace(marker, method + marker, 1)
    sync.write_text(s)

extras = Path('app/lib/extras.dart')
e = extras.read_text()
recover_marker = '  Future<void>syncNow()async{'
if 'Future<void>recoverNow()async{' not in e:
    recover_method = r'''  Future<void>recoverNow()async{
    if(syncing)return;
    setState(()=>syncing=true);
    try{
      await save();
      final result=await WhatsBotPurchaseSyncService.recoverFromServerOnly();
      final localClients=active(await Store.list('clients')).length;
      final localPurchases=active(await Store.list('purchases')).length;
      if(!mounted)return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          duration:const Duration(seconds:10),
          content:Text(
            'Recuperación terminada. Servidor: ${result['serverClients']} clientes y '
            '${result['serverPurchases']} compras. Teléfono: $localClients clientes y '
            '$localPurchases compras. Fotos: ${result['photos']}.'
          ),
        ),
      );
    }catch(err){
      if(mounted){
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(duration:const Duration(seconds:10),content:Text('Error de recuperación: $err')),
        );
      }
    }finally{
      if(mounted)setState(()=>syncing=false);
    }
  }

'''
    if recover_marker not in e:
        raise SystemExit('No se encontró syncNow() en extras.dart')
    e = e.replace(recover_marker, recover_method + recover_marker, 1)

button_marker = "          OutlinedButton.icon(\n            onPressed:syncing?null:syncNow,"
if 'Recuperar desde Railway' not in e:
    recovery_button = """          FilledButton.icon(\n            onPressed:syncing?null:recoverNow,\n            icon:syncing\n              ? const SizedBox.square(dimension:18,child:CircularProgressIndicator(strokeWidth:2))\n              : const Icon(Icons.cloud_download),\n            label:const Text('Recuperar desde Railway (solo lectura)'),\n          ),\n          const SizedBox(height:12),\n"""
    if button_marker not in e:
        raise SystemExit('No se encontró el botón de sincronización')
    e = e.replace(button_marker, recovery_button + button_marker, 1)

extras.write_text(e)
