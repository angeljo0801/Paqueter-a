from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# The smart-photo layer runs after the existing Gmail reconstruction patches.
# It keeps product-like images, rejects obvious banners/promos/logos, deduplicates
# by image bytes, and persists accepted photos inside the app for offline viewing.
main = Path('app/lib/main.dart')
ms = main.read_text()
if "import 'dart:ui' as ui;" not in ms:
    ms = replace_once(
        ms,
        "import 'dart:io';\n",
        "import 'dart:io';\nimport 'dart:ui' as ui;\n",
        'dart ui import',
    )
main.write_text(ms)

helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()
if 'Future<Map<String, dynamic>> gmailPrepareProductPhotos(' not in hs:
    hs += r'''

String _gmailPhotoExt(String url, String contentType) {
  final lower = '$url $contentType'.toLowerCase();
  if (lower.contains('.png') || lower.contains('image/png')) return 'png';
  if (lower.contains('.webp') || lower.contains('image/webp')) return 'webp';
  if (lower.contains('.gif') || lower.contains('image/gif')) return 'gif';
  return 'jpg';
}

String _gmailPhotoDigest(List<int> bytes) {
  var hash = 1469598103934665603;
  for (final value in bytes) {
    hash ^= value;
    hash = (hash * 1099511628211) & 0x7fffffffffffffff;
  }
  return hash.toRadixString(16);
}

bool _gmailPromoText(String text) {
  final lower = text.toLowerCase().replaceAll(RegExp(r'\s+'), ' ').trim();
  if (lower.isEmpty) return false;
  final patterns = <RegExp>[
    RegExp(r'\bfrom\s*(?:usd\s*)?\$\s*\d', caseSensitive: false),
    RegExp(r'\bstarting\s+(?:from|at)\s*(?:usd\s*)?\$?', caseSensitive: false),
    RegExp(r'\bas\s+low\s+as\s*(?:usd\s*)?\$?', caseSensitive: false),
    RegExp(r'\bup\s+to\s+\d{1,3}%\s+off\b', caseSensitive: false),
  ];
  if (patterns.any((p) => p.hasMatch(lower))) return true;
  const blocked = <String>[
    'shop now',
    'buy now',
    'limited time',
    'recommended for you',
    'you may also like',
    'similar items',
    'download the app',
    'get the app',
    'app store',
    'google play',
    'flash sale',
    'special offer',
    'coupon',
    'promo code',
  ];
  return blocked.any(lower.contains);
}

bool _gmailUrlClearlyNotProduct(String url) {
  final lower = url.toLowerCase();
  const blocked = <String>[
    'logo', 'icon', 'sprite', 'pixel', 'beacon', 'tracking', 'spacer',
    'header', 'footer', 'social', 'facebook', 'instagram', 'tiktok',
    'youtube', 'twitter', 'appstore', 'googleplay', 'play-store',
    'badge', 'avatar', 'separator', 'divider', 'marketing-banner',
    'promo-banner', 'email-banner', 'newsletter-banner',
  ];
  return blocked.any(lower.contains);
}

String _gmailMatchedItem(String text, List<Map<String, dynamic>> items) {
  final lower = text.toLowerCase();
  for (final item in items) {
    final name = '${item['name'] ?? ''}'.trim();
    if (name.length < 3) continue;
    final normalized = name.toLowerCase().replaceAll(RegExp(r'[^a-z0-9áéíóúüñ ]+'), ' ');
    final compact = normalized.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (compact.length >= 5 && lower.contains(compact)) return name;
    final tokens = compact
        .split(' ')
        .where((e) => e.length >= 4)
        .toSet();
    if (tokens.length < 2) continue;
    final matches = tokens.where(lower.contains).length;
    if (matches >= 2 && matches / tokens.length >= 0.45) return name;
  }
  return '';
}

Future<String> _gmailOcrFile(String path) async {
  final recognizer = TextRecognizer(script: TextRecognitionScript.latin);
  try {
    final result = await recognizer.processImage(InputImage.fromFilePath(path));
    return result.text.trim();
  } catch (_) {
    return '';
  } finally {
    recognizer.close();
  }
}

Future<Map<String, dynamic>> gmailPrepareProductPhotos({
  required String baseUrl,
  required String apiKey,
  required List<Map<String, dynamic>> images,
  required List<Map<String, dynamic>> items,
}) async {
  final accepted = <Map<String, dynamic>>[];
  final rejected = <Map<String, dynamic>>[];
  final offlinePaths = <String, String>{};
  final seenDigests = <String>{};
  final documents = await getApplicationDocumentsDirectory();
  final dir = Directory('${documents.path}/gmail_product_photos');
  if (!await dir.exists()) await dir.create(recursive: true);
  var ocrBudget = 20;

  for (final original in images.take(80)) {
    final image = Map<String, dynamic>.from(original);
    final rawUrl = '${image['url'] ?? ''}'.trim();
    if (rawUrl.isEmpty) continue;
    if (_gmailUrlClearlyNotProduct(rawUrl)) {
      rejected.add({...image, 'rejectReason': 'logo/banner/icono'});
      continue;
    }

    try {
      final resolved = gmailPhotoUrl(baseUrl, image);
      final response = await http.get(
        Uri.parse(resolved),
        headers: gmailPhotoHeaders(baseUrl, apiKey, image) ?? const <String, String>{},
      ).timeout(const Duration(seconds: 18));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        rejected.add({...image, 'rejectReason': 'imagen no disponible'});
        continue;
      }
      final bytes = response.bodyBytes;
      if (bytes.length < 3500 || bytes.length > 10 * 1024 * 1024) {
        rejected.add({...image, 'rejectReason': 'imagen demasiado pequeña/grande'});
        continue;
      }

      final digest = _gmailPhotoDigest(bytes);
      if (!seenDigests.add(digest)) {
        rejected.add({...image, 'rejectReason': 'duplicada'});
        continue;
      }

      var width = 0;
      var height = 0;
      try {
        final codec = await ui.instantiateImageCodec(bytes);
        final frame = await codec.getNextFrame();
        width = frame.image.width;
        height = frame.image.height;
        frame.image.dispose();
        codec.dispose();
      } catch (_) {}

      if (width > 0 && height > 0 && (width < 90 || height < 90)) {
        rejected.add({...image, 'width': width, 'height': height, 'rejectReason': 'icono pequeño'});
        continue;
      }

      final ratio = width > 0 && height > 0 ? width / height : 1.0;
      var score = 0;
      if (width >= 180 && height >= 180 && ratio >= 0.55 && ratio <= 1.80) {
        score += 3; // pure product photos, including the sandal example, pass here
      } else if (width >= 150 && height >= 150 && ratio >= 0.40 && ratio <= 2.20) {
        score += 2;
      }
      if (width >= 500 && height >= 500) score += 1;
      if (RegExp(r'(product|products|item|items|goods|sku|variant)', caseSensitive: false).hasMatch(rawUrl)) {
        score += 2;
      }

      final ext = _gmailPhotoExt(rawUrl, response.headers['content-type'] ?? '');
      final temp = File('${dir.path}/.$digest.$ext.tmp');
      await temp.writeAsBytes(bytes, flush: true);

      String ocr = '';
      final suspiciousShape = ratio > 1.75 || ratio < 0.52;
      if (ocrBudget > 0 && (suspiciousShape || score < 3)) {
        ocrBudget--;
        ocr = await _gmailOcrFile(temp.path);
      }

      if (_gmailPromoText(ocr)) {
        await temp.delete().catchError((_) => temp);
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'ocrText': ocr,
          'rejectReason': 'publicidad/promoción',
        });
        continue;
      }

      final matchedItem = _gmailMatchedItem(ocr, items);
      if (matchedItem.isNotEmpty) score += 4;
      final lowerOcr = ocr.toLowerCase();
      if (RegExp(r'\b(size|talla|color|qty|quantity|cantidad|label size)\b').hasMatch(lowerOcr)) score += 1;
      if (RegExp(r'(?:usd\s*)?\$\s*\d+[\.,]\d{2}').hasMatch(lowerOcr)) score += 1;
      if (lowerOcr.contains('after credit applied') || lowerOcr.contains('unit price')) score += 1;
      if (ratio > 2.20 && ocr.split(RegExp(r'\s+')).length >= 4 && matchedItem.isEmpty) score -= 3;

      if (score < 2) {
        await temp.delete().catchError((_) => temp);
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'ocrText': ocr,
          'rejectReason': 'sin señales suficientes de producto',
        });
        continue;
      }

      final permanent = File('${dir.path}/$digest.$ext');
      if (!await permanent.exists()) {
        await temp.rename(permanent.path);
      } else if (await temp.exists()) {
        await temp.delete();
      }
      offlinePaths[rawUrl] = permanent.path;
      accepted.add({
        ...image,
        'localPath': permanent.path,
        'width': width,
        'height': height,
        'ocrText': ocr,
        'matchedItem': matchedItem,
        'photoClass': score >= 5 ? 'confirmed_product' : 'probable_product',
        'productScore': score,
      });
    } catch (_) {
      rejected.add({...image, 'rejectReason': 'no se pudo analizar'});
    }
  }

  return {
    'accepted': accepted,
    'rejected': rejected,
    'offlinePaths': offlinePaths,
  };
}

Widget gmailSmartPhotoImage(
  String baseUrl,
  String apiKey,
  Map<String, dynamic> image, {
  BoxFit fit = BoxFit.cover,
}) {
  final local = '${image['localPath'] ?? ''}'.trim();
  if (local.isNotEmpty && File(local).existsSync()) {
    return Image.file(File(local), fit: fit);
  }
  return Image.network(
    gmailPhotoUrl(baseUrl, image),
    headers: gmailPhotoHeaders(baseUrl, apiKey, image),
    fit: fit,
    loadingBuilder: (_, child, progress) => progress == null
        ? child
        : const Center(child: CircularProgressIndicator()),
    errorBuilder: (_, __, ___) => const Center(
      child: Icon(Icons.broken_image_outlined),
    ),
  );
}
'''
    helper_path.write_text(hs)


# Shared full-screen gallery: prefer the persistent local copy so photos remain
# visible offline after Gmail reconstruction.
hs = helper_path.read_text()
old_gallery_image = r'''                        child: Image.network(
                          url,
                          headers: gmailPhotoHeaders(baseUrl, apiKey, image),
                          fit: BoxFit.contain,
                          loadingBuilder: (_, child, progress) => progress == null
                              ? child
                              : const Center(child: CircularProgressIndicator()),
                          errorBuilder: (_, __, ___) => const Center(
                            child: Icon(Icons.broken_image_outlined, size: 64),
                          ),
                        ),'''
new_gallery_image = r'''                        child: gmailSmartPhotoImage(
                          baseUrl,
                          apiKey,
                          image,
                          fit: BoxFit.contain,
                        ),'''
if old_gallery_image in hs:
    hs = hs.replace(old_gallery_image, new_gallery_image, 1)
helper_path.write_text(hs)


# ---------------- Packages ----------------
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()

if 'Map<String, String> gmailOfflinePhotoPaths' not in ps:
    ps = replace_once(
        ps,
        "  final Set<String> hiddenEmailPhotoUrls = <String>{};\n",
        "  final Set<String> hiddenEmailPhotoUrls = <String>{};\n"
        "  Map<String, String> gmailOfflinePhotoPaths = <String, String>{};\n"
        "  List<Map<String, dynamic>> gmailRejectedImages = [];\n",
        'package Gmail offline state',
    )

if "widget.existing?['gmailOfflinePhotoPaths']" not in ps:
    ps = replace_once(
        ps,
        "    hiddenEmailPhotoUrls.addAll(dynList(widget.existing?['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n",
        "    hiddenEmailPhotoUrls.addAll(dynList(widget.existing?['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n"
        "    final offlineRaw = widget.existing?['gmailOfflinePhotoPaths'];\n"
        "    if (offlineRaw is Map) gmailOfflinePhotoPaths = offlineRaw.map((k, v) => MapEntry('$k', '$v'));\n"
        "    gmailRejectedImages = dynList(widget.existing?['gmailRejectedImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n",
        'package Gmail offline load',
    )

# Put localPath into every gallery/thumb entry.
ps = ps.replace(
    "      out.add({'kind': 'remote', 'url': url, 'name': ''});",
    "      out.add({'kind': 'remote', 'url': url, 'name': '', 'localPath': gmailOfflinePhotoPaths[url] ?? ''});",
    1,
)
ps = ps.replace(
    "      out.add({'kind': 'attachment', 'url': url, 'name': '${row['name'] ?? ''}'});",
    "      out.add({...row, 'kind': 'attachment', 'url': url, 'name': '${row['name'] ?? ''}', 'localPath': gmailOfflinePhotoPaths[url] ?? ''});",
    1,
)

package_methods = r'''
  Future<void> _smartFilterAndCacheGmailPhotos() async {
    final allImages = _emailPhotoEntries();
    if (allImages.isEmpty) return;
    final result = await gmailPrepareProductPhotos(
      baseUrl: gmailBackendUrl,
      apiKey: gmailApiKey,
      images: allImages,
      items: gmailItems,
    );
    final accepted = dynList(result['accepted'])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    final rejected = dynList(result['rejected'])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    final offline = result['offlinePaths'];
    if (!mounted) return;
    setState(() {
      gmailRejectedImages = rejected;
      if (offline is Map) {
        gmailOfflinePhotoPaths.addAll(offline.map((k, v) => MapEntry('$k', '$v')));
      }
      emailPhotoUrls = accepted
          .where((e) => '${e['kind']}' == 'remote')
          .map((e) => '${e['url'] ?? ''}'.trim())
          .where((e) => e.isNotEmpty)
          .toList();
      emailAttachmentImages = accepted
          .where((e) => '${e['kind']}' == 'attachment')
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
    });
  }

  Future<void> _showRejectedGmailPhotos() async {
    if (gmailRejectedImages.isEmpty) return;
    await openGmailPhotoGallery(
      context,
      baseUrl: gmailBackendUrl,
      apiKey: gmailApiKey,
      images: gmailRejectedImages,
    );
  }

'''
if 'Future<void> _smartFilterAndCacheGmailPhotos()' not in ps:
    ps = replace_once(
        ps,
        "  Future<void> removeMultipleEmailPhotos() async {\n",
        package_methods + "  Future<void> removeMultipleEmailPhotos() async {\n",
        'package smart photo methods',
    )

if 'await _smartFilterAndCacheGmailPhotos();' not in ps:
    ps = replace_once(
        ps,
        "      await _mergeItemsFromEmailImageOcr();\n",
        "      await _smartFilterAndCacheGmailPhotos();\n      await _mergeItemsFromEmailImageOcr();\n",
        'package smart filter after reconstruction',
    )

if "'gmailOfflinePhotoPaths': gmailOfflinePhotoPaths," not in ps:
    ps = replace_once(
        ps,
        "      'hiddenEmailPhotoUrls': hiddenEmailPhotoUrls.toList(),\n",
        "      'hiddenEmailPhotoUrls': hiddenEmailPhotoUrls.toList(),\n"
        "      'gmailOfflinePhotoPaths': gmailOfflinePhotoPaths,\n"
        "      'gmailRejectedImages': gmailRejectedImages,\n",
        'package save offline Gmail photos',
    )

old_package_thumb = r'''                              child: Image.network(
                                _fullEmailPhotoUrl(image),
                                headers: _emailPhotoHeaders(image),
                                fit: BoxFit.cover,
                                errorBuilder: (_, __, ___) => Container(
                                  alignment: Alignment.center,
                                  child: const Icon(Icons.broken_image_outlined),
                                ),
                              ),'''
new_package_thumb = r'''                              child: gmailSmartPhotoImage(
                                gmailBackendUrl,
                                gmailApiKey,
                                image,
                                fit: BoxFit.cover,
                              ),'''
if old_package_thumb in ps:
    ps = ps.replace(old_package_thumb, new_package_thumb, 1)

if "Ver imágenes descartadas" not in ps:
    anchor = "                  const SizedBox(height: 8),\n                  GridView.builder(\n"
    if anchor in ps:
        ps = ps.replace(
            anchor,
            "                  if (gmailRejectedImages.isNotEmpty)\n"
            "                    Align(\n"
            "                      alignment: Alignment.centerLeft,\n"
            "                      child: TextButton.icon(\n"
            "                        onPressed: _showRejectedGmailPhotos,\n"
            "                        icon: const Icon(Icons.filter_alt_off_outlined),\n"
            "                        label: Text('Ver imágenes descartadas (${gmailRejectedImages.length})'),\n"
            "                      ),\n"
            "                    ),\n"
            "                  const SizedBox(height: 8),\n"
            "                  GridView.builder(\n",
            1,
        )
packages_path.write_text(ps)


# ---------------- Purchases / orders ----------------
purchases_path = Path('app/lib/purchases.dart')
us = purchases_path.read_text()

if 'Map<String, String> gmailPurchaseOfflinePhotoPaths' not in us:
    us = replace_once(
        us,
        "  final Set<String> hiddenGmailPurchasePhotoUrls = <String>{};\n",
        "  final Set<String> hiddenGmailPurchasePhotoUrls = <String>{};\n"
        "  Map<String, String> gmailPurchaseOfflinePhotoPaths = <String, String>{};\n"
        "  List<Map<String, dynamic>> gmailPurchaseRejectedImages = [];\n",
        'purchase Gmail offline state',
    )

if "widget.existing!['gmailOfflinePhotoPaths']" not in us:
    us = replace_once(
        us,
        "      hiddenGmailPurchasePhotoUrls.addAll(dynList(widget.existing!['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n",
        "      hiddenGmailPurchasePhotoUrls.addAll(dynList(widget.existing!['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n"
        "      final offlineRaw = widget.existing!['gmailOfflinePhotoPaths'];\n"
        "      if (offlineRaw is Map) gmailPurchaseOfflinePhotoPaths = offlineRaw.map((k, v) => MapEntry('$k', '$v'));\n"
        "      gmailPurchaseRejectedImages = dynList(widget.existing!['gmailRejectedImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n",
        'purchase Gmail offline load',
    )

old_purchase_entries = r'''  List<Map<String, dynamic>> _purchaseEmailPhotoEntries() => gmailPhotoEntries(
        gmailPurchasePhotoUrls,
        gmailPurchaseAttachmentImages,
        hiddenGmailPurchasePhotoUrls,
      );
'''
new_purchase_entries = r'''  List<Map<String, dynamic>> _purchaseEmailPhotoEntries() => gmailPhotoEntries(
        gmailPurchasePhotoUrls,
        gmailPurchaseAttachmentImages,
        hiddenGmailPurchasePhotoUrls,
      ).map((image) {
        final url = '${image['url'] ?? ''}'.trim();
        return {
          ...image,
          'localPath': gmailPurchaseOfflinePhotoPaths[url] ?? '${image['localPath'] ?? ''}',
        };
      }).toList();
'''
if old_purchase_entries in us:
    us = us.replace(old_purchase_entries, new_purchase_entries, 1)

purchase_methods = r'''
  Future<void> _smartFilterAndCachePurchaseGmailPhotos() async {
    final allImages = _purchaseEmailPhotoEntries();
    if (allImages.isEmpty) return;
    final result = await gmailPrepareProductPhotos(
      baseUrl: gmailPurchaseBackendUrl,
      apiKey: gmailPurchaseApiKey,
      images: allImages,
      items: items,
    );
    final accepted = dynList(result['accepted'])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    final rejected = dynList(result['rejected'])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    final offline = result['offlinePaths'];
    if (!mounted) return;
    setState(() {
      gmailPurchaseRejectedImages = rejected;
      if (offline is Map) {
        gmailPurchaseOfflinePhotoPaths.addAll(
          offline.map((k, v) => MapEntry('$k', '$v')),
        );
      }
      gmailPurchasePhotoUrls = accepted
          .where((e) => '${e['kind']}' == 'remote')
          .map((e) => '${e['url'] ?? ''}'.trim())
          .where((e) => e.isNotEmpty)
          .toList();
      gmailPurchaseAttachmentImages = accepted
          .where((e) => '${e['kind']}' == 'attachment')
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
    });
  }

  Future<void> _showRejectedPurchaseGmailPhotos() async {
    if (gmailPurchaseRejectedImages.isEmpty) return;
    await openGmailPhotoGallery(
      context,
      baseUrl: gmailPurchaseBackendUrl,
      apiKey: gmailPurchaseApiKey,
      images: gmailPurchaseRejectedImages,
    );
  }

'''
if 'Future<void> _smartFilterAndCachePurchaseGmailPhotos()' not in us:
    us = replace_once(
        us,
        "  Future<void> _removeMultiplePurchaseEmailPhotos() async {\n",
        purchase_methods + "  Future<void> _removeMultiplePurchaseEmailPhotos() async {\n",
        'purchase smart photo methods',
    )

if 'await _smartFilterAndCachePurchaseGmailPhotos();' not in us:
    snackbar_anchor = """      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Compra vinculada con Gmail: ${items.length} artículo(s), ${_purchaseEmailPhotoEntries().length} foto(s).',
            ),
          ),
        );
      }
"""
    us = replace_once(
        us,
        snackbar_anchor,
        "      await _smartFilterAndCachePurchaseGmailPhotos();\n" + snackbar_anchor,
        'purchase smart filter after Gmail link',
    )

if "'gmailOfflinePhotoPaths': gmailPurchaseOfflinePhotoPaths," not in us:
    us = replace_once(
        us,
        "      'hiddenEmailPhotoUrls': hiddenGmailPurchasePhotoUrls.toList(),\n",
        "      'hiddenEmailPhotoUrls': hiddenGmailPurchasePhotoUrls.toList(),\n"
        "      'gmailOfflinePhotoPaths': gmailPurchaseOfflinePhotoPaths,\n"
        "      'gmailRejectedImages': gmailPurchaseRejectedImages,\n",
        'purchase save offline Gmail photos',
    )

old_purchase_thumb = r'''                              child: Image.network(
                                gmailPhotoUrl(gmailPurchaseBackendUrl, image),
                                headers: gmailPhotoHeaders(
                                  gmailPurchaseBackendUrl,
                                  gmailPurchaseApiKey,
                                  image,
                                ),
                                fit: BoxFit.cover,
                                errorBuilder: (_, __, ___) => Container(
                                  alignment: Alignment.center,
                                  child: const Icon(Icons.broken_image_outlined),
                                ),
                              ),'''
new_purchase_thumb = r'''                              child: gmailSmartPhotoImage(
                                gmailPurchaseBackendUrl,
                                gmailPurchaseApiKey,
                                image,
                                fit: BoxFit.cover,
                              ),'''
if old_purchase_thumb in us:
    us = us.replace(old_purchase_thumb, new_purchase_thumb, 1)

if "Ver imágenes descartadas" not in us:
    purchase_grid_anchor = "                  const SizedBox(height: 8),\n                  GridView.builder(\n"
    # The first matching grid in the Gmail purchase card is safe after canonical patches.
    if purchase_grid_anchor in us:
        us = us.replace(
            purchase_grid_anchor,
            "                  if (gmailPurchaseRejectedImages.isNotEmpty)\n"
            "                    Align(\n"
            "                      alignment: Alignment.centerLeft,\n"
            "                      child: TextButton.icon(\n"
            "                        onPressed: _showRejectedPurchaseGmailPhotos,\n"
            "                        icon: const Icon(Icons.filter_alt_off_outlined),\n"
            "                        label: Text('Ver imágenes descartadas (${gmailPurchaseRejectedImages.length})'),\n"
            "                      ),\n"
            "                    ),\n"
            "                  const SizedBox(height: 8),\n"
            "                  GridView.builder(\n",
            1,
        )
purchases_path.write_text(us)

print('Smart Gmail product-photo filtering and offline caching applied.')
