from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# Shared Gmail reconstruction helpers used by both purchases and packages.
main = Path('app/lib/main.dart')
ms = main.read_text()
if "part 'gmail_purchase_link.dart';" not in ms:
    ms = replace_once(
        ms,
        "part 'gmail_accounts.dart';\n",
        "part 'gmail_accounts.dart';\npart 'gmail_purchase_link.dart';\n",
        'gmail_purchase_link part',
    )
main.write_text(ms)

helper = r'''part of 'main.dart';

String gmailItemKey(dynamic raw) {
  final value = raw is Map ? '${raw['name'] ?? ''}' : '$raw';
  return value
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9áéíóúüñ]+'), ' ')
      .trim();
}

List<Map<String, dynamic>> mergeGmailDetectedItems(
  List<Map<String, dynamic>> current,
  dynamic incoming, {
  String? defaultClientId,
}) {
  final out = current.map((e) => Map<String, dynamic>.from(e)).toList();
  final index = <String, int>{};
  for (var i = 0; i < out.length; i++) {
    final key = gmailItemKey(out[i]);
    if (key.isNotEmpty) index[key] = i;
  }
  for (final raw in dynList(incoming)) {
    if (raw is! Map) continue;
    final row = Map<String, dynamic>.from(raw);
    final name = '${row['name'] ?? ''}'.trim();
    final key = gmailItemKey(name);
    if (key.isEmpty) continue;
    final qty = number(row['qty']) <= 0 ? 1.0 : number(row['qty']);
    final price = number(row['price']);
    final existingIndex = index[key];
    if (existingIndex != null) {
      final existing = out[existingIndex];
      if (number(existing['qty']) < qty) existing['qty'] = qty;
      if (number(existing['price']) <= 0 && price > 0) existing['price'] = price;
      existing.putIfAbsent('received', () => false);
      if ('${existing['clientId'] ?? ''}'.trim().isEmpty &&
          '${defaultClientId ?? ''}'.trim().isNotEmpty) {
        existing['clientId'] = defaultClientId;
      }
      existing['source'] = '${existing['source'] ?? 'gmail'}';
      continue;
    }
    out.add({
      'id': '${row['id'] ?? newId()}',
      'name': name,
      'price': price,
      'qty': qty,
      'received': row['received'] == true,
      'clientId': '${row['clientId'] ?? defaultClientId ?? ''}',
      'source': '${row['source'] ?? 'gmail'}',
    });
    index[key] = out.length - 1;
  }
  return out;
}

List<Map<String, dynamic>> gmailPhotoEntries(
  List<String> urls,
  List<Map<String, dynamic>> attachments,
  Set<String> hidden,
) {
  final out = <Map<String, dynamic>>[];
  for (final raw in urls) {
    final url = raw.trim();
    if (url.isEmpty || hidden.contains(url)) continue;
    out.add({'kind': 'remote', 'url': url, 'name': ''});
  }
  for (final raw in attachments) {
    final row = Map<String, dynamic>.from(raw);
    final url = '${row['url'] ?? ''}'.trim();
    if (url.isEmpty || hidden.contains(url)) continue;
    if (out.any((e) => '${e['url']}' == url)) continue;
    out.add({
      ...row,
      'kind': 'attachment',
      'url': url,
      'name': '${row['name'] ?? ''}',
    });
  }
  return out;
}

String gmailPhotoUrl(String baseUrl, Map<String, dynamic> image) {
  final raw = '${image['url'] ?? ''}'.trim();
  if (raw.startsWith('http://') || raw.startsWith('https://')) return raw;
  final base = baseUrl.trim().replaceAll(RegExp(r'/$'), '');
  return raw.startsWith('/') ? '$base$raw' : '$base/$raw';
}

Map<String, String>? gmailPhotoHeaders(
  String baseUrl,
  String apiKey,
  Map<String, dynamic> image,
) {
  final raw = '${image['url'] ?? ''}'.trim();
  final base = baseUrl.trim().replaceAll(RegExp(r'/$'), '');
  final isBackend = raw.startsWith('/') || (base.isNotEmpty && raw.startsWith(base));
  if (!isBackend || apiKey.trim().isEmpty) return null;
  return {'x-api-key': apiKey.trim()};
}

Future<void> openGmailPhotoPreview(
  BuildContext context, {
  required String baseUrl,
  required String apiKey,
  required Map<String, dynamic> image,
}) async {
  final url = gmailPhotoUrl(baseUrl, image);
  if (url.isEmpty) return;
  await showDialog<void>(
    context: context,
    builder: (_) => Dialog(
      insetPadding: EdgeInsets.zero,
      backgroundColor: Colors.black,
      child: SafeArea(
        child: Stack(
          children: [
            Positioned.fill(
              child: InteractiveViewer(
                minScale: 0.7,
                maxScale: 6,
                child: Center(
                  child: Image.network(
                    url,
                    headers: gmailPhotoHeaders(baseUrl, apiKey, image),
                    fit: BoxFit.contain,
                    loadingBuilder: (_, child, progress) => progress == null
                        ? child
                        : const Center(child: CircularProgressIndicator()),
                    errorBuilder: (_, __, ___) => const Center(
                      child: Icon(Icons.broken_image_outlined, size: 64),
                    ),
                  ),
                ),
              ),
            ),
            Positioned(
              right: 8,
              top: 8,
              child: IconButton.filled(
                tooltip: 'Cerrar',
                onPressed: () => Navigator.pop(context),
                icon: const Icon(Icons.close),
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

Future<Set<String>?> selectGmailPhotosToRemove(
  BuildContext context, {
  required List<Map<String, dynamic>> images,
  required String baseUrl,
  required String apiKey,
}) async {
  if (images.isEmpty) return <String>{};
  final selected = <String>{};
  return showDialog<Set<String>>(
    context: context,
    builder: (_) => StatefulBuilder(
      builder: (dialogContext, setDialog) => AlertDialog(
        title: const Text('Seleccionar fotos para quitar'),
        content: SizedBox(
          width: double.maxFinite,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  TextButton(
                    onPressed: () => setDialog(() {
                      selected
                        ..clear()
                        ..addAll(images.map((e) => '${e['url'] ?? ''}').where((e) => e.isNotEmpty));
                    }),
                    child: const Text('Todas'),
                  ),
                  TextButton(
                    onPressed: () => setDialog(selected.clear),
                    child: const Text('Ninguna'),
                  ),
                  const Spacer(),
                  Text('${selected.length} seleccionada(s)'),
                ],
              ),
              const SizedBox(height: 8),
              Flexible(
                child: GridView.builder(
                  shrinkWrap: true,
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 3,
                    crossAxisSpacing: 7,
                    mainAxisSpacing: 7,
                  ),
                  itemCount: images.length,
                  itemBuilder: (_, i) {
                    final image = images[i];
                    final raw = '${image['url'] ?? ''}'.trim();
                    final checked = selected.contains(raw);
                    return InkWell(
                      onTap: () => setDialog(() {
                        if (checked) {
                          selected.remove(raw);
                        } else if (raw.isNotEmpty) {
                          selected.add(raw);
                        }
                      }),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          ClipRRect(
                            borderRadius: BorderRadius.circular(9),
                            child: Image.network(
                              gmailPhotoUrl(baseUrl, image),
                              headers: gmailPhotoHeaders(baseUrl, apiKey, image),
                              fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => Container(
                                alignment: Alignment.center,
                                child: const Icon(Icons.broken_image_outlined),
                              ),
                            ),
                          ),
                          Positioned(
                            right: 3,
                            top: 3,
                            child: CircleAvatar(
                              radius: 15,
                              child: Icon(
                                checked ? Icons.check : Icons.circle_outlined,
                                size: 20,
                              ),
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cancelar'),
          ),
          FilledButton.icon(
            onPressed: selected.isEmpty
                ? null
                : () => Navigator.pop(dialogContext, Set<String>.from(selected)),
            icon: const Icon(Icons.delete_outline),
            label: Text('Quitar ${selected.length}'),
          ),
        ],
      ),
    ),
  );
}

class GmailPurchaseLinkService {
  static Future<Map<String, dynamic>> reconstruct({
    String orderNumber = '',
    String tracking = '',
  }) async {
    final order = orderNumber.trim();
    final track = tracking.trim();
    if (order.isEmpty && track.isEmpty) {
      throw Exception('Escribe un número de orden o tracking primero.');
    }
    final base = (await WhatsBotPurchaseSyncService.backendUrl())
        .trim()
        .replaceAll(RegExp(r'/$'), '');
    final key = (await WhatsBotPurchaseSyncService.apiKey()).trim();
    if (key.isEmpty) {
      throw Exception('Falta la APP_API_KEY de WhatsBot en Configuración.');
    }
    final uri = Uri.parse('$base/api/gmail/reconstruct').replace(
      queryParameters: order.isNotEmpty
          ? {'order_number': order}
          : {'tracking': track},
    );
    final response = await http.get(
      uri,
      headers: {'x-api-key': key},
    ).timeout(const Duration(seconds: 75));
    dynamic decoded;
    try {
      decoded = jsonDecode(response.body);
    } catch (_) {
      decoded = null;
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = decoded is Map && decoded['detail'] != null
          ? '${decoded['detail']}'
          : response.body;
      throw Exception(detail.isEmpty
          ? 'Servidor respondió ${response.statusCode}'
          : detail);
    }
    if (decoded is! Map) throw Exception('Respuesta inválida del servidor.');
    return Map<String, dynamic>.from(decoded);
  }
}
'''
Path('app/lib/gmail_purchase_link.dart').write_text(helper)


# ---------------- Package editor ----------------
packages = Path('app/lib/packages.dart')
ps = packages.read_text()

if 'List<Map<String, dynamic>> gmailItems = [];' not in ps:
    ps = replace_once(
        ps,
        "  List<Map<String, dynamic>> emailAttachmentImages = [];\n  List<String> gmailSourceEmails = [];\n",
        "  List<Map<String, dynamic>> emailAttachmentImages = [];\n  List<String> gmailSourceEmails = [];\n  List<Map<String, dynamic>> gmailItems = [];\n",
        'package gmailItems state',
    )

if "widget.existing?['gmailItems']" not in ps:
    ps = replace_once(
        ps,
        "    emailAttachmentImages = dynList(widget.existing?['emailAttachmentImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n",
        "    emailAttachmentImages = dynList(widget.existing?['emailAttachmentImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n    gmailItems = dynList(widget.existing?['gmailItems']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n",
        'package load gmailItems',
    )

if 'mergeGmailDetectedItems(gmailItems' not in ps:
    ps = replace_once(
        ps,
        "        gmailSourceEmails = dynList(data['sourceEmails']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();\n",
        "        gmailSourceEmails = dynList(data['sourceEmails']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();\n        gmailItems = mergeGmailDetectedItems(gmailItems, data['items']);\n        final detectedOrder = gmailOrder.text.trim().toLowerCase();\n        if (detectedOrder.isNotEmpty) {\n          final linked = purchases.where((p) => purchaseOrderNumbers(p).any((n) => n.trim().toLowerCase() == detectedOrder)).firstOrNull;\n          if (linked != null) {\n            purchaseId = '${linked['id']}';\n            final linkedClient = '${linked['clientId'] ?? ''}'.trim();\n            if (clientId == null && linkedClient.isNotEmpty) clientId = linkedClient;\n          }\n        }\n",
        'package merge gmail items and link purchase',
    )

if "'gmailItems': gmailItems," not in ps:
    ps = replace_once(
        ps,
        "      'gmailSourceEmails': gmailSourceEmails,\n",
        "      'gmailSourceEmails': gmailSourceEmails,\n      'gmailItems': gmailItems,\n",
        'package save gmailItems',
    )

package_methods = r'''
  Future<void> removeMultipleEmailPhotos() async {
    final selected = await selectGmailPhotosToRemove(
      context,
      images: _emailPhotoEntries(),
      baseUrl: gmailBackendUrl,
      apiKey: gmailApiKey,
    );
    if (selected == null || selected.isEmpty || !mounted) return;
    setState(() {
      hiddenEmailPhotoUrls.addAll(selected);
      emailPhotoUrls.removeWhere((e) => selected.contains(e.trim()));
      emailAttachmentImages.removeWhere(
        (e) => selected.contains('${e['url'] ?? ''}'.trim()),
      );
    });
  }

  Future<void> _propagateReceivedGmailItemsToPurchase() async {
    if (purchaseId == null || gmailItems.isEmpty) return;
    final receivedKeys = gmailItems
        .where((e) => e['received'] == true)
        .map(gmailItemKey)
        .where((e) => e.isNotEmpty)
        .toSet();
    if (receivedKeys.isEmpty) return;
    final purchaseRows = await Store.list('purchases');
    final index = purchaseRows.indexWhere((e) => '${e['id']}' == purchaseId);
    if (index < 0) return;
    final purchase = purchaseRows[index];
    final purchaseItemRows = purchaseItems(purchase);
    var changed = false;
    for (final item in purchaseItemRows) {
      if (receivedKeys.contains(gmailItemKey(item)) && item['received'] != true) {
        item['received'] = true;
        changed = true;
      }
    }
    if (!changed) return;
    purchaseRows[index] = {...purchase, 'items': purchaseItemRows};
    await Store.saveList('purchases', purchaseRows);
  }

'''
if 'Future<void> removeMultipleEmailPhotos()' not in ps:
    ps = replace_once(
        ps,
        "  Future<void> save() async {\n",
        package_methods + "  Future<void> save() async {\n",
        'package multi remove methods',
    )

if 'await _propagateReceivedGmailItemsToPurchase();' not in ps:
    ps = replace_once(
        ps,
        "    await Store.saveList('packages', rows);\n    if (mounted) Navigator.pop(context);\n",
        "    await Store.saveList('packages', rows);\n    await _propagateReceivedGmailItemsToPurchase();\n    if (mounted) Navigator.pop(context);\n",
        'package propagate received items',
    )

package_checklist = r'''
        if (gmailItems.isNotEmpty) ...[
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.checklist_outlined, size: 20),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Checklist de artículos del correo',
                          style: Theme.of(context).textTheme.titleSmall?.copyWith(
                                fontWeight: FontWeight.bold,
                              ),
                        ),
                      ),
                      Text('${gmailItems.where((e) => e['received'] == true).length}/${gmailItems.length}'),
                    ],
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Marca cada artículo cuando haya llegado. El nombre y la cantidad se obtienen de los correos relacionados.',
                    style: TextStyle(fontSize: 12),
                  ),
                  const Divider(),
                  for (var i = 0; i < gmailItems.length; i++)
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      dense: true,
                      value: gmailItems[i]['received'] == true,
                      onChanged: (value) => setState(
                        () => gmailItems[i]['received'] = value == true,
                      ),
                      title: Text('${gmailItems[i]['name'] ?? 'Artículo'}'),
                      subtitle: Text(
                        'Cantidad: ${number(gmailItems[i]['qty']) <= 0 ? 1 : number(gmailItems[i]['qty']).toStringAsFixed(number(gmailItems[i]['qty']) % 1 == 0 ? 0 : 2)}'
                        '${number(gmailItems[i]['price']) > 0 ? ' · ${money(number(gmailItems[i]['price']))} c/u' : ''}',
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
'''
if 'Checklist de artículos del correo' not in ps:
    ps = replace_once(
        ps,
        "        if (emailImages.isNotEmpty) ...[\n",
        package_checklist + "        if (emailImages.isNotEmpty) ...[\n",
        'package gmail checklist UI',
    )

if "label: const Text('Seleccionar varias fotos')" not in ps:
    ps = replace_once(
        ps,
        "                  const SizedBox(height: 10),\n                  GridView.builder(\n",
        "                  const SizedBox(height: 10),\n                  Align(\n                    alignment: Alignment.centerLeft,\n                    child: OutlinedButton.icon(\n                      onPressed: removeMultipleEmailPhotos,\n                      icon: const Icon(Icons.library_add_check_outlined),\n                      label: const Text('Seleccionar varias fotos'),\n                    ),\n                  ),\n                  const SizedBox(height: 8),\n                  GridView.builder(\n",
        'package multi photo button',
    )

ps = ps.replace(
    "'Toca una imagen para verla en grande y usa × para quitarla.',",
    "'Toca una imagen para verla en grande. Usa × para una sola o Seleccionar varias para quitar muchas a la vez.',",
    1,
)
packages.write_text(ps)


# ---------------- Purchase editor ----------------
purchases = Path('app/lib/purchases.dart')
us = purchases.read_text()

if 'List<String> gmailPurchasePhotoUrls = [];' not in us:
    us = replace_once(
        us,
        "  List<String> photoPaths = [];\n  List<String> orderNumbers = [];\n  bool loaded = false;\n",
        "  List<String> photoPaths = [];\n  List<String> orderNumbers = [];\n  List<String> gmailPurchasePhotoUrls = [];\n  List<Map<String, dynamic>> gmailPurchaseAttachmentImages = [];\n  final Set<String> hiddenGmailPurchasePhotoUrls = <String>{};\n  List<String> gmailPurchaseSourceEmails = [];\n  List<String> gmailLinkedOrderNumbers = [];\n  String gmailPurchaseStatus = '', gmailPurchaseEta = '';\n  String gmailPurchaseBackendUrl = '', gmailPurchaseApiKey = '';\n  bool gmailPurchaseLoading = false;\n  bool loaded = false;\n",
        'purchase Gmail state',
    )

if "widget.existing!['emailPhotoUrls']" not in us:
    us = replace_once(
        us,
        "      items = purchaseItems(widget.existing!);\n",
        "      items = purchaseItems(widget.existing!);\n      gmailPurchasePhotoUrls = dynList(widget.existing!['emailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();\n      gmailPurchaseAttachmentImages = dynList(widget.existing!['emailAttachmentImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n      hiddenGmailPurchasePhotoUrls.addAll(dynList(widget.existing!['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n      gmailPurchaseSourceEmails = dynList(widget.existing!['gmailSourceEmails']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();\n      gmailLinkedOrderNumbers = dynList(widget.existing!['gmailLinkedOrderNumbers']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();\n      gmailPurchaseStatus = '${widget.existing!['gmailStatus'] ?? ''}';\n      gmailPurchaseEta = '${widget.existing!['gmailEstimatedDelivery'] ?? ''}';\n",
        'purchase load Gmail state',
    )

if 'gmailPurchaseBackendUrl = await WhatsBotPurchaseSyncService.backendUrl();' not in us:
    us = replace_once(
        us,
        "    if (mounted) setState(() => loaded = true);\n",
        "    gmailPurchaseBackendUrl = await WhatsBotPurchaseSyncService.backendUrl();\n    gmailPurchaseApiKey = await WhatsBotPurchaseSyncService.apiKey();\n    if (mounted) setState(() => loaded = true);\n",
        'purchase load Gmail connection',
    )

purchase_methods = r'''
  List<Map<String, dynamic>> _purchaseEmailPhotoEntries() => gmailPhotoEntries(
        gmailPurchasePhotoUrls,
        gmailPurchaseAttachmentImages,
        hiddenGmailPurchasePhotoUrls,
      );

  Future<void> _openPurchaseEmailPhoto(Map<String, dynamic> image) =>
      openGmailPhotoPreview(
        context,
        baseUrl: gmailPurchaseBackendUrl,
        apiKey: gmailPurchaseApiKey,
        image: image,
      );

  Future<void> _removePurchaseEmailPhoto(Map<String, dynamic> image) async {
    final raw = '${image['url'] ?? ''}'.trim();
    if (raw.isEmpty) return;
    final ok = await showDialog<bool>(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('Quitar foto'),
            content: const Text(
              '¿Quitar esta foto de la compra? El correo original no se borra.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Cancelar'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Quitar'),
              ),
            ],
          ),
        ) ??
        false;
    if (!ok || !mounted) return;
    setState(() {
      hiddenGmailPurchasePhotoUrls.add(raw);
      gmailPurchasePhotoUrls.removeWhere((e) => e.trim() == raw);
      gmailPurchaseAttachmentImages.removeWhere(
        (e) => '${e['url'] ?? ''}'.trim() == raw,
      );
    });
  }

  Future<void> _removeMultiplePurchaseEmailPhotos() async {
    final selected = await selectGmailPhotosToRemove(
      context,
      images: _purchaseEmailPhotoEntries(),
      baseUrl: gmailPurchaseBackendUrl,
      apiKey: gmailPurchaseApiKey,
    );
    if (selected == null || selected.isEmpty || !mounted) return;
    setState(() {
      hiddenGmailPurchasePhotoUrls.addAll(selected);
      gmailPurchasePhotoUrls.removeWhere((e) => selected.contains(e.trim()));
      gmailPurchaseAttachmentImages.removeWhere(
        (e) => selected.contains('${e['url'] ?? ''}'.trim()),
      );
    });
  }

  Future<void> linkPurchaseWithGmail() async {
    final numbers = purchaseOrderNumbers({
      'orderNumbers': orderNumbers,
      'orderNumber': order.text,
    });
    if (numbers.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Añade al menos un número de orden para buscarlo en Gmail.'),
        ),
      );
      return;
    }
    gmailPurchaseBackendUrl = await WhatsBotPurchaseSyncService.backendUrl();
    gmailPurchaseApiKey = await WhatsBotPurchaseSyncService.apiKey();
    if (gmailPurchaseApiKey.trim().isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Falta la APP_API_KEY de WhatsBot.')),
        );
      }
      return;
    }
    setState(() => gmailPurchaseLoading = true);
    try {
      Future<Map<String, dynamic>> safeLookup(String value) async {
        try {
          return await GmailPurchaseLinkService.reconstruct(orderNumber: value);
        } catch (e) {
          return {'found': false, '_error': '$e'};
        }
      }

      final results = await Future.wait(numbers.take(8).map(safeLookup));
      final found = results.where((e) => e['found'] == true).toList();
      if (found.isEmpty) {
        final error = results
            .map((e) => '${e['_error'] ?? ''}'.replaceFirst('Exception: ', ''))
            .firstWhere((e) => e.isNotEmpty, orElse: () => '');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(error.isEmpty
                  ? 'No encontré correos para esos números de orden.'
                  : 'No pude vincular la compra: $error'),
            ),
          );
        }
        return;
      }
      if (!mounted) return;
      setState(() {
        for (var i = 0; i < found.length; i++) {
          final data = found[i];
          final queryOrder = i < numbers.length ? numbers[i] : '';
          if (queryOrder.isNotEmpty && !gmailLinkedOrderNumbers.contains(queryOrder)) {
            gmailLinkedOrderNumbers.add(queryOrder);
          }
          final detectedStore = '${data['store'] ?? ''}'.trim();
          if (detectedStore.isNotEmpty &&
              (store.text.trim().isEmpty || store.text.trim() == 'Otra tienda')) {
            store.text = detectedStore;
          }
          final detectedTotal = number(data['total']);
          if (number(total.text) <= 0 && detectedTotal > 0) {
            total.text = detectedTotal.toStringAsFixed(2);
          }
          final detectedStatus = '${data['status'] ?? ''}'.trim();
          if (detectedStatus.isNotEmpty) gmailPurchaseStatus = detectedStatus;
          final detectedEta = '${data['estimatedDelivery'] ?? ''}'.trim();
          if (detectedEta.isNotEmpty) gmailPurchaseEta = detectedEta;
          for (final raw in dynList(data['sourceEmails'])) {
            final email = '$raw'.trim();
            if (email.isNotEmpty && !gmailPurchaseSourceEmails.contains(email)) {
              gmailPurchaseSourceEmails.add(email);
            }
          }
          for (final raw in dynList(data['emailPhotoUrls'])) {
            final url = '$raw'.trim();
            if (url.isNotEmpty &&
                !hiddenGmailPurchasePhotoUrls.contains(url) &&
                !gmailPurchasePhotoUrls.contains(url)) {
              gmailPurchasePhotoUrls.add(url);
            }
          }
          for (final raw in dynList(data['emailAttachmentImages'])) {
            if (raw is! Map) continue;
            final row = Map<String, dynamic>.from(raw);
            final url = '${row['url'] ?? ''}'.trim();
            if (url.isEmpty || hiddenGmailPurchasePhotoUrls.contains(url)) continue;
            if (!gmailPurchaseAttachmentImages.any((e) => '${e['url'] ?? ''}' == url)) {
              gmailPurchaseAttachmentImages.add(row);
            }
          }
          items = mergeGmailDetectedItems(
            items,
            data['items'],
            defaultClientId: clientId,
          );
        }
        if (desc.text.trim().isEmpty && items.isNotEmpty) {
          desc.text = items.take(4).map((e) => '${e['name']}').join(', ');
        }
        if (status == 'Pendiente de comprar') status = 'Comprado';
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Compra vinculada con Gmail: ${items.length} artículo(s), ${_purchaseEmailPhotoEntries().length} foto(s).',
            ),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => gmailPurchaseLoading = false);
    }
  }

'''
if 'Future<void> linkPurchaseWithGmail()' not in us:
    us = replace_once(
        us,
        "  Future<void> importReceipt() async {\n",
        purchase_methods + "  Future<void> importReceipt() async {\n",
        'purchase Gmail methods',
    )

us = us.replace(
    "    if (ok != true || name.text.trim().isEmpty || number(price.text) == 0) return;",
    "    if (ok != true || name.text.trim().isEmpty) return;",
    1,
)

if "'received': item?['received'] == true," not in us:
    us = replace_once(
        us,
        "      'clientId': assigned ?? '',\n    };\n",
        "      'clientId': assigned ?? '',\n      'received': item?['received'] == true,\n      'source': '${item?['source'] ?? 'manual'}',\n    };\n",
        'purchase preserve checklist fields on edit',
    )

if "'gmailLinkedOrderNumbers': gmailLinkedOrderNumbers," not in us:
    us = replace_once(
        us,
        "      'receiptPath': receiptPath,\n",
        "      'gmailLinkedOrderNumbers': gmailLinkedOrderNumbers,\n      'gmailSourceEmails': gmailPurchaseSourceEmails,\n      'gmailStatus': gmailPurchaseStatus,\n      'gmailEstimatedDelivery': gmailPurchaseEta,\n      'emailPhotoUrls': gmailPurchasePhotoUrls,\n      'emailAttachmentImages': gmailPurchaseAttachmentImages,\n      'hiddenEmailPhotoUrls': hiddenGmailPurchasePhotoUrls.toList(),\n      'receiptPath': receiptPath,\n",
        'purchase save Gmail data',
    )

if 'final gmailPurchaseImages = _purchaseEmailPhotoEntries();' not in us:
    us = replace_once(
        us,
        "    if (!loaded) return const Scaffold(body: Center(child: CircularProgressIndicator()));\n    return Scaffold(\n",
        "    if (!loaded) return const Scaffold(body: Center(child: CircularProgressIndicator()));\n    final gmailPurchaseImages = _purchaseEmailPhotoEntries();\n    return Scaffold(\n",
        'purchase Gmail images build state',
    )

purchase_gmail_ui = r'''
        FilledButton.tonalIcon(
          onPressed: gmailPurchaseLoading ? null : linkPurchaseWithGmail,
          icon: gmailPurchaseLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.mark_email_read_outlined),
          label: const Text('Vincular con correo usando número de orden'),
        ),
        if (gmailPurchaseSourceEmails.isNotEmpty ||
            gmailPurchaseStatus.isNotEmpty ||
            gmailPurchaseEta.isNotEmpty) ...[
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (gmailPurchaseSourceEmails.isNotEmpty)
                    Text('Encontrado en: ${gmailPurchaseSourceEmails.join(', ')}'),
                  if (gmailPurchaseStatus.isNotEmpty)
                    Text('Estado del correo: $gmailPurchaseStatus'),
                  if (gmailPurchaseEta.isNotEmpty)
                    Text('Entrega estimada: $gmailPurchaseEta'),
                ],
              ),
            ),
          ),
        ],
        if (gmailPurchaseImages.isNotEmpty) ...[
          const SizedBox(height: 10),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.email_outlined, size: 20),
                      const SizedBox(width: 8),
                      const Expanded(
                        child: Text(
                          'Fotos obtenidas del correo',
                          style: TextStyle(fontWeight: FontWeight.bold),
                        ),
                      ),
                      Text('${gmailPurchaseImages.length}'),
                    ],
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: _removeMultiplePurchaseEmailPhotos,
                    icon: const Icon(Icons.library_add_check_outlined),
                    label: const Text('Seleccionar varias para quitar'),
                  ),
                  const SizedBox(height: 8),
                  GridView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: gmailPurchaseImages.length,
                    gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 3,
                      crossAxisSpacing: 7,
                      mainAxisSpacing: 7,
                    ),
                    itemBuilder: (_, index) {
                      final image = gmailPurchaseImages[index];
                      return Stack(
                        fit: StackFit.expand,
                        children: [
                          Material(
                            color: Theme.of(context).colorScheme.surfaceContainerHighest,
                            borderRadius: BorderRadius.circular(9),
                            clipBehavior: Clip.antiAlias,
                            child: InkWell(
                              onTap: () => _openPurchaseEmailPhoto(image),
                              child: Image.network(
                                gmailPhotoUrl(gmailPurchaseBackendUrl, image),
                                headers: gmailPhotoHeaders(
                                  gmailPurchaseBackendUrl,
                                  gmailPurchaseApiKey,
                                  image,
                                ),
                                fit: BoxFit.cover,
                                errorBuilder: (_, __, ___) => const Center(
                                  child: Icon(Icons.broken_image_outlined),
                                ),
                              ),
                            ),
                          ),
                          Positioned(
                            right: 2,
                            top: 2,
                            child: IconButton.filled(
                              visualDensity: VisualDensity.compact,
                              tooltip: 'Quitar foto',
                              onPressed: () => _removePurchaseEmailPhoto(image),
                              icon: const Icon(Icons.close, size: 17),
                            ),
                          ),
                        ],
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
        ],
'''
if 'Vincular con correo usando número de orden' not in us:
    us = replace_once(
        us,
        "        const SizedBox(height: 12),\n        TextField(controller: date, decoration: const InputDecoration(labelText: 'Fecha (AAAA-MM-DD)')),\n",
        "        const SizedBox(height: 12),\n" + purchase_gmail_ui + "        const SizedBox(height: 12),\n        TextField(controller: date, decoration: const InputDecoration(labelText: 'Fecha (AAAA-MM-DD)')),\n",
        'purchase Gmail link UI',
    )

us = us.replace(
    "Expanded(child: Text('Artículos del ticket', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold))),",
    "Expanded(child: Text('Checklist de artículos', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold))),",
    1,
)
us = us.replace(
    "if (items.isEmpty) const Text('No hay artículos separados. Puedes añadirlos manualmente o leer un ticket.'),",
    "if (items.isEmpty) const Text('No hay artículos todavía. Puedes añadirlos, leer un ticket o vincular la compra con Gmail por número de orden.'),",
    1,
)

if "value: e['received'] == true" not in us:
    us = replace_once(
        us,
        "            child: ListTile(\n              title: Text('${e['name']}'),\n",
        "            child: ListTile(\n              leading: Checkbox(\n                value: e['received'] == true,\n                onChanged: (value) => setState(() => e['received'] = value == true),\n              ),\n              title: Text('${e['name']}'),\n",
        'purchase checklist checkbox',
    )

us = us.replace(
    "                Text(money(number(e['price']) * number(e['qty'] ?? 1))),",
    "                if (number(e['price']) > 0)\n                  Text(money(number(e['price']) * number(e['qty'] ?? 1)))\n                else\n                  const Text('Sin precio'),",
    1,
)

if "'Marca el cuadrito cuando el artículo haya llegado.'" not in us:
    us = replace_once(
        us,
        "        if (items.isNotEmpty) ...[\n          const SizedBox(height: 8),\n          Text('Puedes asignar cada artículo a un cliente diferente. El impuesto/descuento restante del ticket se reparte proporcionalmente.'),\n",
        "        if (items.isNotEmpty) ...[\n          const SizedBox(height: 8),\n          const Text('Marca el cuadrito cuando el artículo haya llegado.'),\n          const SizedBox(height: 4),\n          Text('Puedes asignar cada artículo a un cliente diferente. El impuesto/descuento restante del ticket se reparte proporcionalmente.'),\n",
        'purchase checklist help',
    )

purchases.write_text(us)

print('Gmail product names, quantities, checklist linking and multi-photo removal applied.')
