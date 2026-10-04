from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# Refine the smart Gmail photo filter using real-world order-line vs catalog-card
# signals, keep item OCR/checklists intact, and make discarded photos open as a
# thumbnail grid before entering the swipe/zoom/delete viewer.
helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()

if 'bool gmailOrderItemPhotoSignals(String text)' not in hs:
    helpers = r'''
bool gmailOrderItemPhotoSignals(String text) {
  final lower = text.toLowerCase().replaceAll(RegExp(r'\s+'), ' ').trim();
  if (lower.isEmpty) return false;
  const strong = <String>[
    'after credit applied',
    'credit applied',
    'label size',
    'item subtotal',
    'unit price',
    'sold by',
    'fulfilled by',
  ];
  if (strong.any(lower.contains)) return true;
  if (RegExp(r'\b(qty|quantity|cantidad)\s*[:#-]?\s*\d{1,3}\b').hasMatch(lower)) {
    return true;
  }
  if (RegExp(r'(?:^|\s)[x×]\s*\d{1,3}(?:\s|$)').hasMatch(lower)) return true;
  if (RegExp(r'\b(size|talla|color)\s*[:#-]\s*[a-z0-9]').hasMatch(lower)) return true;
  return false;
}

bool gmailCatalogRecommendationCard(String text) {
  final lower = text.toLowerCase().replaceAll(RegExp(r'\s+'), ' ').trim();
  if (lower.isEmpty || gmailOrderItemPhotoSignals(lower)) return false;
  if (_gmailPromoText(lower)) return true;
  final priceCount = RegExp(
    r'(?:us\$|usd\s*\$?|\$)\s*[0-9][0-9,]*(?:[\.,][0-9]{1,2})?',
    caseSensitive: false,
  ).allMatches(lower).length;
  final ratingCue = RegExp(
    r'(?:★|☆|⭐){2,}|\b(?:rating|ratings|review|reviews)\b',
    caseSensitive: false,
  ).hasMatch(text);
  final catalogCue = <String>[
    'add to cart',
    'add to bag',
    'similar items',
    'recommended',
    'you may also like',
    'customers also',
  ].any(lower.contains);
  // Recommendation tiles very often contain both the current and crossed-out
  // price. Real order-line screenshots usually contain quantity/size/color or
  // an "after credit applied" label, which is handled above and remains valid.
  return catalogCue || ratingCue && priceCount >= 1 || priceCount >= 2;
}

'''
    hs = replace_once(
        hs,
        'bool _gmailUrlClearlyNotProduct(String url) {\n',
        helpers + 'bool _gmailUrlClearlyNotProduct(String url) {\n',
        'Gmail catalog/order photo helpers',
    )

if "if (gmailCatalogRecommendationCard(text) && !gmailOrderItemPhotoSignals(text))" not in hs:
    hs = replace_once(
        hs,
        "List<Map<String, dynamic>> gmailItemsFromOcrText(String text) {\n  final lines = text\n",
        "List<Map<String, dynamic>> gmailItemsFromOcrText(String text) {\n  if (gmailCatalogRecommendationCard(text) && !gmailOrderItemPhotoSignals(text)) {\n    return <Map<String, dynamic>>[];\n  }\n  final lines = text\n",
        'skip recommendation cards during item OCR',
    )

hs = hs.replace('  var ocrBudget = 20;\n', '  var ocrBudget = 80;\n', 1)
hs = hs.replace(
    "      final suspiciousShape = ratio > 1.75 || ratio < 0.52;\n      if (ocrBudget > 0 && (suspiciousShape || score < 3)) {\n",
    "      if (ocrBudget > 0) {\n",
    1,
)

old_scoring = r'''      final matchedItem = _gmailMatchedItem(ocr, items);
      if (matchedItem.isNotEmpty) score += 4;
      final lowerOcr = ocr.toLowerCase();
      if (RegExp(r'\b(size|talla|color|qty|quantity|cantidad|label size)\b').hasMatch(lowerOcr)) score += 1;
      if (RegExp(r'(?:usd\s*)?\$\s*\d+[\.,]\d{2}').hasMatch(lowerOcr)) score += 1;
      if (lowerOcr.contains('after credit applied') || lowerOcr.contains('unit price')) score += 1;
      if (ratio > 2.20 && ocr.split(RegExp(r'\s+')).length >= 4 && matchedItem.isEmpty) score -= 3;
'''
new_scoring = r'''      final matchedItem = _gmailMatchedItem(ocr, items);
      final orderItemSignals = gmailOrderItemPhotoSignals(ocr);
      final catalogCard = gmailCatalogRecommendationCard(ocr);
      if (catalogCard && !orderItemSignals) {
        await temp.delete().catchError((_) => temp);
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'ocrText': ocr,
          'rejectReason': 'tarjeta de catálogo/recomendación',
        });
        continue;
      }
      if (orderItemSignals) score += 6;
      if (matchedItem.isNotEmpty) score += 4;
      final lowerOcr = ocr.toLowerCase();
      if (RegExp(r'\b(size|talla|color|qty|quantity|cantidad|label size)\b').hasMatch(lowerOcr)) score += 1;
      if (RegExp(r'(?:usd\s*)?\$\s*\d+[\.,]\d{2}').hasMatch(lowerOcr)) score += 1;
      if (lowerOcr.contains('after credit applied') || lowerOcr.contains('unit price')) score += 2;
      if (ratio > 2.20 && ocr.split(RegExp(r'\s+')).length >= 4 && matchedItem.isEmpty && !orderItemSignals) score -= 3;
'''
if old_scoring in hs:
    hs = hs.replace(old_scoring, new_scoring, 1)
else:
    raise SystemExit('No se encontró bloque esperado: Gmail smart photo scoring')

if 'Future<Set<String>> showGmailRejectedPhotoGrid(' not in hs:
    grid_helper = r'''
Future<Set<String>> showGmailRejectedPhotoGrid(
  BuildContext context, {
  required String baseUrl,
  required String apiKey,
  required List<Map<String, dynamic>> images,
}) async {
  if (images.isEmpty) return <String>{};
  final working = images.map((e) => Map<String, dynamic>.from(e)).toList();
  final removed = <String>{};

  await showDialog<void>(
    context: context,
    builder: (_) => StatefulBuilder(
      builder: (gridContext, setGrid) => Dialog.fullscreen(
        child: Scaffold(
          appBar: AppBar(
            title: Text('Imágenes descartadas (${working.length})'),
            leading: IconButton(
              icon: const Icon(Icons.arrow_back),
              onPressed: () => Navigator.pop(gridContext),
            ),
          ),
          body: working.isEmpty
              ? const Center(child: Text('No quedan imágenes descartadas.'))
              : GridView.builder(
                  padding: const EdgeInsets.all(10),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 3,
                    crossAxisSpacing: 8,
                    mainAxisSpacing: 8,
                  ),
                  itemCount: working.length,
                  itemBuilder: (_, index) {
                    final image = working[index];
                    final reason = '${image['rejectReason'] ?? ''}'.trim();
                    return InkWell(
                      onTap: () async {
                        final removedNow = await openGmailPhotoGallery(
                          gridContext,
                          baseUrl: baseUrl,
                          apiKey: apiKey,
                          images: working,
                          initialIndex: index,
                        );
                        if (removedNow.isEmpty) return;
                        removed.addAll(removedNow);
                        setGrid(() {
                          working.removeWhere((e) =>
                              removedNow.contains('${e['url'] ?? ''}'.trim()));
                        });
                      },
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          ClipRRect(
                            borderRadius: BorderRadius.circular(10),
                            child: gmailSmartPhotoImage(
                              baseUrl,
                              apiKey,
                              image,
                              fit: BoxFit.cover,
                            ),
                          ),
                          if (reason.isNotEmpty)
                            Positioned(
                              left: 4,
                              right: 4,
                              bottom: 4,
                              child: DecoratedBox(
                                decoration: BoxDecoration(
                                  color: Colors.black.withValues(alpha: 0.68),
                                  borderRadius: BorderRadius.circular(7),
                                ),
                                child: Padding(
                                  padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 3),
                                  child: Text(
                                    reason,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(color: Colors.white, fontSize: 10),
                                  ),
                                ),
                              ),
                            ),
                        ],
                      ),
                    );
                  },
                ),
        ),
      ),
    ),
  );
  return removed;
}

'''
    hs = replace_once(
        hs,
        'Future<Set<String>?> selectGmailPhotosToRemove(\n',
        grid_helper + 'Future<Set<String>?> selectGmailPhotosToRemove(\n',
        'discarded Gmail thumbnail grid',
    )

helper_path.write_text(hs)


# Package editor: OCR all candidate images before filtering so genuine order
# screenshots (e.g. size/quantity/after-credit rows) can create checklist items
# and can then influence the product-photo decision.
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()
ps = ps.replace(
    '      await _smartFilterAndCacheGmailPhotos();\n      await _mergeItemsFromEmailImageOcr();\n',
    '      await _mergeItemsFromEmailImageOcr();\n      await _smartFilterAndCacheGmailPhotos();\n',
    1,
)

old_package_rejected = r'''  Future<void> _showRejectedGmailPhotos() async {
    if (gmailRejectedImages.isEmpty) return;
    await openGmailPhotoGallery(
      context,
      baseUrl: gmailBackendUrl,
      apiKey: gmailApiKey,
      images: gmailRejectedImages,
    );
  }
'''
new_package_rejected = r'''  Future<void> _showRejectedGmailPhotos() async {
    if (gmailRejectedImages.isEmpty) return;
    final removed = await showGmailRejectedPhotoGrid(
      context,
      baseUrl: gmailBackendUrl,
      apiKey: gmailApiKey,
      images: gmailRejectedImages,
    );
    if (!mounted || removed.isEmpty) return;
    setState(() {
      hiddenEmailPhotoUrls.addAll(removed);
      gmailRejectedImages.removeWhere(
        (e) => removed.contains('${e['url'] ?? ''}'.trim()),
      );
      emailPhotoUrls.removeWhere((e) => removed.contains(e.trim()));
      emailAttachmentImages.removeWhere(
        (e) => removed.contains('${e['url'] ?? ''}'.trim()),
      );
    });
  }
'''
if old_package_rejected in ps:
    ps = ps.replace(old_package_rejected, new_package_rejected, 1)
else:
    raise SystemExit('No se encontró bloque esperado: package rejected-photo viewer')
packages_path.write_text(ps)


# Purchase/order editor gets the same discarded-photo grid behavior. Existing
# article rows (checkbox + quantity + price + edit + delete) are deliberately
# left untouched.
purchases_path = Path('app/lib/purchases.dart')
us = purchases_path.read_text()
old_purchase_rejected = r'''  Future<void> _showRejectedPurchaseGmailPhotos() async {
    if (gmailPurchaseRejectedImages.isEmpty) return;
    await openGmailPhotoGallery(
      context,
      baseUrl: gmailPurchaseBackendUrl,
      apiKey: gmailPurchaseApiKey,
      images: gmailPurchaseRejectedImages,
    );
  }
'''
new_purchase_rejected = r'''  Future<void> _showRejectedPurchaseGmailPhotos() async {
    if (gmailPurchaseRejectedImages.isEmpty) return;
    final removed = await showGmailRejectedPhotoGrid(
      context,
      baseUrl: gmailPurchaseBackendUrl,
      apiKey: gmailPurchaseApiKey,
      images: gmailPurchaseRejectedImages,
    );
    if (!mounted || removed.isEmpty) return;
    setState(() {
      hiddenGmailPurchasePhotoUrls.addAll(removed);
      gmailPurchaseRejectedImages.removeWhere(
        (e) => removed.contains('${e['url'] ?? ''}'.trim()),
      );
      gmailPurchasePhotoUrls.removeWhere((e) => removed.contains(e.trim()));
      gmailPurchaseAttachmentImages.removeWhere(
        (e) => removed.contains('${e['url'] ?? ''}'.trim()),
      );
    });
  }
'''
if old_purchase_rejected in us:
    us = us.replace(old_purchase_rejected, new_purchase_rejected, 1)
else:
    raise SystemExit('No se encontró bloque esperado: purchase rejected-photo viewer')
purchases_path.write_text(us)

print('Gmail product-photo filter v2 + discarded thumbnail grid applied.')
