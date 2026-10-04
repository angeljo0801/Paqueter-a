from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# This patch runs after patch_gmail_product_checklists.py. It adds three layers:
# 1) validation to reject common email boilerplate that was being mistaken for products;
# 2) on-device ML Kit OCR for prices/product text rendered inside Gmail images;
# 3) edit/delete controls for the package Gmail checklist, with persisted suppression
#    so deleted detections do not immediately return on the next reconstruction.

helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()

validation_and_ocr = r'''
String _gmailNormalizeLine(String value) =>
    value.replaceAll(RegExp(r'\s+'), ' ').trim();

bool gmailDetectedItemLooksValid(dynamic raw) {
  final name = raw is Map ? '${raw['name'] ?? ''}' : '$raw';
  final clean = _gmailNormalizeLine(name);
  final lower = clean.toLowerCase();
  if (clean.length < 3 || clean.length > 180) return false;
  if (!RegExp(r'[A-Za-zÀ-ÿ]').hasMatch(clean)) return false;
  if (RegExp(r'^(hi|hello|hola)\b.*[,!]?$' , caseSensitive: false).hasMatch(clean)) {
    return false;
  }
  const blockedExact = <String>{
    'privacy & cookie policy',
    'privacy policy',
    'cookie policy',
    'track your order',
    'track your package',
    'view order',
    'view your order',
    'order summary',
    'subtotal',
    'tax',
    'sales tax',
    'shipping',
    'delivery',
    'discount',
    'total',
    'order total',
    'grand total',
    'payment method',
    'customer service',
    'contact us',
    'unsubscribe',
  };
  if (blockedExact.contains(lower)) return false;
  const blockedFragments = <String>[
    'privacy policy',
    'cookie policy',
    'terms of use',
    'manage preferences',
    'all rights reserved',
    'unsubscribe',
    'view in browser',
    'track your order',
    'track your package',
    'tracking number',
    'order number',
    'shipping address',
    'billing address',
    'payment method',
    'customer service',
    'contact us',
    'download the app',
    'download our app',
    'google play',
    'app store',
    'get a credit within',
    'credit within 48 hours',
    'if delivered after',
    'business days',
    'estimated delivery',
    'delivery date',
    'returns policy',
    'return policy',
  ];
  if (blockedFragments.any(lower.contains)) return false;
  if (RegExp(r'^(after credit applied|credit applied|sale price|your price|unit price|price|precio|total)\b', caseSensitive: false).hasMatch(clean)) {
    return false;
  }
  return true;
}

final RegExp _gmailOcrPricePattern = RegExp(
  r'(?:US\$|USD\s*\$?|\$)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)|([0-9][0-9,]*\.[0-9]{2})\s*(?:USD|US\$)',
  caseSensitive: false,
);
final RegExp _gmailOcrQtyPattern = RegExp(
  r'(?:\bqty\.?|\bquantity|\bcantidad)\s*[:#-]?\s*(\d{1,3})\b|\b[x×]\s*(\d{1,3})\b|\b(\d{1,3})\s*[x×]\b',
  caseSensitive: false,
);

num _gmailOcrPrice(String line) {
  final match = _gmailOcrPricePattern.firstMatch(line);
  if (match == null) return 0;
  String raw = '';
  for (var i = 1; i <= match.groupCount; i++) {
    final value = match.group(i);
    if (value != null && value.trim().isNotEmpty) {
      raw = value;
      break;
    }
  }
  return number(raw);
}

int _gmailOcrQty(String text) {
  final match = _gmailOcrQtyPattern.firstMatch(text);
  if (match == null) return 1;
  for (var i = 1; i <= match.groupCount; i++) {
    final value = int.tryParse('${match.group(i) ?? ''}');
    if (value != null) return value.clamp(1, 999);
  }
  return 1;
}

String _gmailOcrCandidateName(String value) {
  var out = value.replaceAll(_gmailOcrPricePattern, ' ');
  out = out.replaceAll(_gmailOcrQtyPattern, ' ');
  out = out.replaceAll(
    RegExp(
      r'\b(?:after\s+credit\s+applied|credit\s+applied|price\s+after\s+(?:credit|discount)|sale\s+price|discounted\s+price|your\s+price|unit\s+price|item\s+price|price|precio)\s*[:\-]?\s*',
      caseSensitive: false,
    ),
    ' ',
  );
  return _gmailNormalizeLine(out).replaceAll(RegExp(r'^[\-:|•·–—]+|[\-:|•·–—]+$'), '').trim();
}

List<Map<String, dynamic>> gmailItemsFromOcrText(String text) {
  final lines = text
      .split(RegExp(r'[\r\n]+'))
      .map(_gmailNormalizeLine)
      .where((e) => e.isNotEmpty)
      .toList();
  final found = <String, Map<String, dynamic>>{};
  final order = <String>[];

  void add(String rawName, num price, int qty, {bool preferredPrice = false}) {
    final name = _gmailOcrCandidateName(rawName);
    if (!gmailDetectedItemLooksValid({'name': name})) return;
    final key = gmailItemKey(name);
    if (key.isEmpty) return;
    final normalizedPrice = price > 0 ? price.toDouble() : 0.0;
    if (!found.containsKey(key)) {
      found[key] = {
        'id': newId(),
        'name': name,
        'price': normalizedPrice,
        'qty': qty.clamp(1, 999),
        'received': false,
        'source': 'gmail-image-ocr',
        'confidence': 0.82,
      };
      order.add(key);
      return;
    }
    final row = found[key]!;
    if (qty > number(row['qty'])) row['qty'] = qty;
    if (normalizedPrice > 0 &&
        (number(row['price']) <= 0 || preferredPrice)) {
      row['price'] = normalizedPrice;
    }
  }

  for (var i = 0; i < lines.length; i++) {
    final line = lines[i];
    final price = _gmailOcrPrice(line);
    if (price <= 0) continue;
    final lower = line.toLowerCase();
    final preferredPrice = lower.contains('after credit applied') ||
        lower.contains('credit applied') ||
        lower.contains('sale price') ||
        lower.contains('discounted price') ||
        lower.contains('your price');
    final windowStart = (i - 4).clamp(0, lines.length);
    final windowEnd = (i + 3).clamp(0, lines.length);
    final nearby = lines.sublist(windowStart, windowEnd).join(' ');
    final qty = _gmailOcrQty(nearby);

    final sameLine = _gmailOcrCandidateName(line);
    if (gmailDetectedItemLooksValid({'name': sameLine})) {
      add(sameLine, price, qty, preferredPrice: preferredPrice);
      continue;
    }

    String candidate = '';
    for (final distance in <int>[1, 2, 3, 4]) {
      final before = i - distance;
      if (before >= 0) {
        final value = _gmailOcrCandidateName(lines[before]);
        if (gmailDetectedItemLooksValid({'name': value})) {
          candidate = value;
          break;
        }
      }
    }
    if (candidate.isEmpty) {
      for (final distance in <int>[1, 2]) {
        final after = i + distance;
        if (after < lines.length) {
          final value = _gmailOcrCandidateName(lines[after]);
          if (gmailDetectedItemLooksValid({'name': value})) {
            candidate = value;
            break;
          }
        }
      }
    }
    if (candidate.isNotEmpty) {
      add(candidate, price, qty, preferredPrice: preferredPrice);
    }
  }

  return order.map((key) => found[key]!).take(40).toList();
}

bool gmailImageWorthOcr(Map<String, dynamic> image) {
  final raw = '${image['url'] ?? ''}'.toLowerCase();
  if (raw.isEmpty) return false;
  const skip = <String>[
    'logo', 'icon', 'sprite', 'spacer', 'pixel', 'tracking', 'beacon',
    'facebook', 'instagram', 'twitter', 'tiktok', 'youtube', 'linkedin',
    'appstore', 'googleplay', 'google-play', 'footer', 'header-logo',
  ];
  if (skip.any(raw.contains)) return false;
  if (raw.endsWith('.gif')) return false;
  return true;
}

Future<String?> gmailReadTextFromImage(
  String baseUrl,
  String apiKey,
  Map<String, dynamic> image,
) async {
  final url = gmailPhotoUrl(baseUrl, image);
  if (url.isEmpty) return null;
  try {
    final response = await http
        .get(
          Uri.parse(url),
          headers: gmailPhotoHeaders(baseUrl, apiKey, image),
        )
        .timeout(const Duration(seconds: 18));
    if (response.statusCode < 200 || response.statusCode >= 300) return null;
    if (response.bodyBytes.isEmpty || response.bodyBytes.length > 8 * 1024 * 1024) {
      return null;
    }
    final dir = await getTemporaryDirectory();
    final lower = Uri.tryParse(url)?.path.toLowerCase() ?? '';
    final ext = lower.endsWith('.png')
        ? 'png'
        : lower.endsWith('.webp')
            ? 'webp'
            : 'jpg';
    final path = '${dir.path}/gmail_image_ocr_${newId()}.$ext';
    final file = File(path);
    await file.writeAsBytes(response.bodyBytes, flush: true);
    final recognizer = TextRecognizer(script: TextRecognitionScript.latin);
    try {
      final recognized = await recognizer.processImage(InputImage.fromFilePath(path));
      return recognized.text;
    } finally {
      recognizer.close();
      try {
        if (await file.exists()) await file.delete();
      } catch (_) {}
    }
  } catch (_) {
    return null;
  }
}

'''

if 'bool gmailDetectedItemLooksValid(dynamic raw)' not in hs:
    hs = replace_once(
        hs,
        'List<Map<String, dynamic>> mergeGmailDetectedItems(\n',
        validation_and_ocr + 'List<Map<String, dynamic>> mergeGmailDetectedItems(\n',
        'gmail item validation + image OCR helpers',
    )

if "if (!gmailDetectedItemLooksValid(row)) continue;" not in hs:
    hs = replace_once(
        hs,
        "    final row = Map<String, dynamic>.from(raw);\n    final name = '${row['name'] ?? ''}'.trim();\n",
        "    final row = Map<String, dynamic>.from(raw);\n    if (!gmailDetectedItemLooksValid(row)) continue;\n    final name = '${row['name'] ?? ''}'.trim();\n",
        'reject boilerplate Gmail items',
    )

if "existing['manuallyEdited'] != true" not in hs:
    hs = replace_once(
        hs,
        "      if (number(existing['qty']) < qty) existing['qty'] = qty;\n      if (number(existing['price']) <= 0 && price > 0) existing['price'] = price;\n",
        "      if (existing['manuallyEdited'] != true) {\n        if (number(existing['qty']) < qty) existing['qty'] = qty;\n        if (number(existing['price']) <= 0 && price > 0) existing['price'] = price;\n      }\n",
        'respect manually edited Gmail item values',
    )

helper_path.write_text(hs)


packages = Path('app/lib/packages.dart')
ps = packages.read_text()

if 'final Set<String> hiddenGmailItemKeys = <String>{};' not in ps:
    ps = replace_once(
        ps,
        '  List<Map<String, dynamic>> gmailItems = [];\n',
        '  List<Map<String, dynamic>> gmailItems = [];\n  final Set<String> hiddenGmailItemKeys = <String>{};\n  final Set<String> gmailOcrScannedUrls = <String>{};\n',
        'package hidden Gmail item + OCR state',
    )

if "widget.existing?['hiddenGmailItemKeys']" not in ps:
    ps = replace_once(
        ps,
        "    gmailItems = dynList(widget.existing?['gmailItems']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n",
        "    gmailItems = dynList(widget.existing?['gmailItems']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n    hiddenGmailItemKeys.addAll(dynList(widget.existing?['hiddenGmailItemKeys']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n    gmailOcrScannedUrls.addAll(dynList(widget.existing?['gmailOcrScannedUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n    gmailItems.removeWhere((e) => !gmailDetectedItemLooksValid(e) || hiddenGmailItemKeys.contains(gmailItemKey(e)));\n",
        'package load hidden items and OCR state',
    )

if "'hiddenGmailItemKeys': hiddenGmailItemKeys.toList()," not in ps:
    ps = replace_once(
        ps,
        "      'gmailItems': gmailItems,\n",
        "      'gmailItems': gmailItems,\n      'hiddenGmailItemKeys': hiddenGmailItemKeys.toList(),\n      'gmailOcrScannedUrls': gmailOcrScannedUrls.toList(),\n",
        'package save hidden items and OCR state',
    )

if 'hiddenGmailItemKeys.contains(gmailItemKey(e))' not in ps.split('mergeGmailDetectedItems(gmailItems', 1)[-1][:600]:
    ps = replace_once(
        ps,
        "        gmailItems = mergeGmailDetectedItems(gmailItems, data['items']);\n",
        "        gmailItems = mergeGmailDetectedItems(gmailItems, data['items']);\n        gmailItems.removeWhere((e) => !gmailDetectedItemLooksValid(e) || hiddenGmailItemKeys.contains(gmailItemKey(e)));\n",
        'package filter reconstructed Gmail items',
    )

package_item_methods = r'''
  Future<void> _editGmailItem(int index) async {
    if (index < 0 || index >= gmailItems.length) return;
    final item = Map<String, dynamic>.from(gmailItems[index]);
    final oldKey = gmailItemKey(item);
    final name = TextEditingController(text: '${item['name'] ?? ''}');
    final qty = TextEditingController(
      text: (number(item['qty']) <= 0 ? 1 : number(item['qty']))
          .toStringAsFixed(number(item['qty']) % 1 == 0 ? 0 : 2),
    );
    final price = TextEditingController(
      text: number(item['price']) > 0 ? number(item['price']).toStringAsFixed(2) : '',
    );
    final saveEdit = await showDialog<bool>(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('Editar artículo'),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: name,
                    autofocus: true,
                    decoration: const InputDecoration(labelText: 'Artículo'),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: qty,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Cantidad'),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: price,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Precio por unidad'),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Cancelar'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Guardar'),
              ),
            ],
          ),
        ) ??
        false;
    if (!saveEdit || !mounted) return;
    final newName = name.text.trim();
    if (newName.isEmpty) return;
    final newQty = number(qty.text) <= 0 ? 1.0 : number(qty.text);
    final newPrice = number(price.text).clamp(0, double.infinity);
    final updated = <String, dynamic>{
      ...item,
      'name': newName,
      'qty': newQty,
      'price': newPrice,
      'manuallyEdited': true,
      'source': item['source'] == 'gmail-image-ocr' ? 'gmail-image-ocr-edited' : 'gmail-edited',
    };
    final newKey = gmailItemKey(updated);
    final duplicate = gmailItems.asMap().entries.any(
          (entry) => entry.key != index && gmailItemKey(entry.value) == newKey,
        );
    if (duplicate) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Ya existe otro artículo con ese nombre.')),
      );
      return;
    }
    setState(() {
      if (oldKey.isNotEmpty && oldKey != newKey) hiddenGmailItemKeys.add(oldKey);
      hiddenGmailItemKeys.remove(newKey);
      gmailItems[index] = updated;
    });
  }

  Future<void> _deleteGmailItem(int index) async {
    if (index < 0 || index >= gmailItems.length) return;
    final item = gmailItems[index];
    final ok = await showDialog<bool>(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('Eliminar artículo'),
            content: Text('¿Quitar “${item['name'] ?? 'Artículo'}” de este paquete? No se modifica el correo original.'),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Cancelar'),
              ),
              FilledButton.icon(
                onPressed: () => Navigator.pop(context, true),
                icon: const Icon(Icons.delete_outline),
                label: const Text('Eliminar'),
              ),
            ],
          ),
        ) ??
        false;
    if (!ok || !mounted) return;
    setState(() {
      final key = gmailItemKey(item);
      if (key.isNotEmpty) hiddenGmailItemKeys.add(key);
      gmailItems.removeAt(index);
    });
  }

  Future<void> _mergeItemsFromEmailImageOcr() async {
    final candidates = _emailPhotoEntries()
        .where(gmailImageWorthOcr)
        .where((image) => !gmailOcrScannedUrls.contains('${image['url'] ?? ''}'.trim()))
        .take(12)
        .toList();
    if (candidates.isEmpty) return;
    var merged = gmailItems;
    var added = 0;
    for (final image in candidates) {
      final rawUrl = '${image['url'] ?? ''}'.trim();
      final text = await gmailReadTextFromImage(
        gmailBackendUrl,
        gmailApiKey,
        image,
      );
      if (text == null) continue;
      if (rawUrl.isNotEmpty) gmailOcrScannedUrls.add(rawUrl);
      final detected = gmailItemsFromOcrText(text);
      if (detected.isEmpty) continue;
      final before = merged.length;
      merged = mergeGmailDetectedItems(merged, detected);
      merged.removeWhere((e) =>
          !gmailDetectedItemLooksValid(e) ||
          hiddenGmailItemKeys.contains(gmailItemKey(e)));
      added += (merged.length - before).clamp(0, 999);
    }
    if (!mounted) return;
    setState(() => gmailItems = merged);
    if (added > 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'OCR de imágenes del correo encontró $added artículo(s) adicional(es).',
          ),
        ),
      );
    }
  }

'''

if 'Future<void> _editGmailItem(int index)' not in ps:
    ps = replace_once(
        ps,
        '  Future<void> removeMultipleEmailPhotos() async {\n',
        package_item_methods + '  Future<void> removeMultipleEmailPhotos() async {\n',
        'package Gmail item edit/delete/OCR methods',
    )

if 'await _mergeItemsFromEmailImageOcr();' not in ps:
    ps = replace_once(
        ps,
        "      if (mounted) {\n        ScaffoldMessenger.of(context).showSnackBar(\n          SnackBar(content: Text('Compra reconstruida desde Gmail${gmailStore.text.isEmpty ? '' : ' · ${gmailStore.text}'}')),\n        );\n      }\n",
        "      await _mergeItemsFromEmailImageOcr();\n      if (mounted) {\n        ScaffoldMessenger.of(context).showSnackBar(\n          SnackBar(content: Text('Compra reconstruida desde Gmail${gmailStore.text.isEmpty ? '' : ' · ${gmailStore.text}'}')),\n        );\n      }\n",
        'run image OCR after Gmail reconstruction',
    )

old_checklist_tile = r'''                  for (var i = 0; i < gmailItems.length; i++)
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
'''
new_checklist_tile = r'''                  for (var i = 0; i < gmailItems.length; i++)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      dense: true,
                      leading: Checkbox(
                        value: gmailItems[i]['received'] == true,
                        onChanged: (value) => setState(
                          () => gmailItems[i]['received'] = value == true,
                        ),
                      ),
                      title: Text('${gmailItems[i]['name'] ?? 'Artículo'}'),
                      subtitle: Text(
                        'Cantidad: ${number(gmailItems[i]['qty']) <= 0 ? 1 : number(gmailItems[i]['qty']).toStringAsFixed(number(gmailItems[i]['qty']) % 1 == 0 ? 0 : 2)}'
                        '${number(gmailItems[i]['price']) > 0 ? ' · ${money(number(gmailItems[i]['price']))} c/u' : ' · Sin precio'}'
                        '${'${gmailItems[i]['source'] ?? ''}'.contains('image-ocr') ? ' · OCR imagen' : ''}',
                      ),
                      trailing: Wrap(
                        spacing: 0,
                        children: [
                          IconButton(
                            tooltip: 'Editar artículo',
                            visualDensity: VisualDensity.compact,
                            onPressed: () => _editGmailItem(i),
                            icon: const Icon(Icons.edit_outlined),
                          ),
                          IconButton(
                            tooltip: 'Eliminar artículo',
                            visualDensity: VisualDensity.compact,
                            onPressed: () => _deleteGmailItem(i),
                            icon: const Icon(Icons.delete_outline),
                          ),
                        ],
                      ),
                    ),
'''

if "tooltip: 'Editar artículo'" not in ps:
    ps = replace_once(
        ps,
        old_checklist_tile,
        new_checklist_tile,
        'package editable Gmail checklist rows',
    )

ps = ps.replace(
    'Marca cada artículo cuando haya llegado. El nombre y la cantidad se obtienen de los correos relacionados.',
    'Marca cada artículo cuando llegue. Puedes editar o eliminar detecciones incorrectas. También se revisa el texto dentro de las imágenes del correo con OCR.',
    1,
)

packages.write_text(ps)

print('Editable Gmail checklist + image OCR fallback applied.')
