from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


def replace_dart_class(text: str, class_name: str, replacement: str) -> str:
    start = text.find(f'class {class_name} ')
    if start < 0:
        raise SystemExit(f'No se encontró clase {class_name}')
    brace = text.find('{', start)
    if brace < 0:
        raise SystemExit(f'No se encontró apertura de {class_name}')
    depth = 0
    end = -1
    for i in range(brace, len(text)):
        ch = text[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        raise SystemExit(f'No se encontró cierre de {class_name}')
    return text[:start] + replacement + text[end:]


# v5 is based on the screenshots reported from Temu: genuine compact order rows
# can be very wide and low-resolution, while recommendation cards often contain
# a sale price + crossed-out price + review/rating number. Geometry alone is no
# longer enough to reject the order row or accept the recommendation card.
helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()

start = hs.find('bool gmailCatalogRecommendationCard(String text) {')
end = hs.find('\n}\n\nbool _gmailUrlClearlyNotProduct', start)
if start < 0 or end < 0:
    raise SystemExit('No se encontró gmailCatalogRecommendationCard para aplicar v5')
end += 2

catalog_v5 = r'''bool gmailCatalogRecommendationCard(String text) {
  final lower = text.toLowerCase().replaceAll(RegExp(r'\s+'), ' ').trim();
  if (lower.isEmpty) return false;
  if (_gmailPromoText(lower)) return true;

  final orderSignals = gmailOrderItemPhotoSignals(lower);
  final priceCount = RegExp(
    r'(?:us\$|usd\s*\$?|\$)\s*[0-9][0-9,]*(?:[\.,][0-9]{1,2})?',
    caseSensitive: false,
  ).allMatches(lower).length;
  // OCR sometimes misses the dollar sign or the strikethrough. Two decimal
  // money-like values are still a strong sale-card signal (12.98 + 93.95).
  final decimalMoneyCount = RegExp(
    r'(?<!\d)[0-9]{1,5}[\.,][0-9]{2}(?!\d)',
  ).allMatches(lower).length;

  final starGlyphs = RegExp(r'(?:★|☆|⭐|✩|✭|✮|✯|✰){1,}').hasMatch(text);
  final ratingWords = RegExp(
    r'\b(?:rating|ratings|review|reviews|stars?|valoraci[oó]n|reseñas?)\b',
    caseSensitive: false,
  ).hasMatch(lower);
  final ratingNumber = RegExp(r'\b[0-5](?:[\.,][0-9])?\s*(?:/\s*5|stars?)\b').hasMatch(lower);
  final reviewCountLike = RegExp(r'\b[1-9][0-9]{0,2}(?:,[0-9]{3})+\b').hasMatch(lower);

  final cartUi = <String>[
    'add to cart', 'add to bag', 'shopping cart', 'shopping bag',
    'view cart', 'go to cart', 'in cart', 'my cart', 'your cart',
    'añadir al carrito', 'agregar al carrito', 'ver carrito', 'mi carrito',
    'buy it now', 'checkout', 'proceed to checkout',
  ].any(lower.contains);

  final catalogUi = <String>[
    'similar items', 'recommended', 'recommended for you',
    'you may also like', 'customers also', 'frequently bought',
    'shop similar', 'more like this', 'sponsored',
  ].any(lower.contains);

  final nonProductUi = <String>[
    'privacy', 'privacy policy', 'return package', 'return item',
    'return items', 'return or replace', 'refund', 'terms of use',
    'terms and conditions', 'manage preferences', 'unsubscribe',
  ].any(lower.contains);

  if (starGlyphs || ratingWords || ratingNumber || cartUi || catalogUi || nonProductUi) {
    return true;
  }
  if (!orderSignals && (priceCount >= 2 || decimalMoneyCount >= 2)) return true;
  if (!orderSignals && reviewCountLike && (priceCount >= 1 || decimalMoneyCount >= 1)) {
    return true;
  }
  return false;
}'''

hs = hs[:start] + catalog_v5 + hs[end:]

old_scoring = r'''      if (orderItemSignals) score += 6;
      if (matchedItem.isNotEmpty) score += 4;
      final lowerOcr = ocr.toLowerCase();
      if (RegExp(r'\b(size|talla|color|qty|quantity|cantidad|label size)\b').hasMatch(lowerOcr)) score += 1;
      if (RegExp(r'(?:usd\s*)?\$\s*\d+[\.,]\d{2}').hasMatch(lowerOcr)) score += 1;
      if (lowerOcr.contains('after credit applied') || lowerOcr.contains('unit price')) score += 2;
      if (ratio > 2.20 && ocr.split(RegExp(r'\s+')).length >= 4 && matchedItem.isEmpty && !orderItemSignals) score -= 3;
'''
new_scoring = r'''      if (orderItemSignals) score += 6;
      if (matchedItem.isNotEmpty) score += 4;
      final lowerOcr = ocr.toLowerCase();
      final alphaWords = RegExp(
        r'\b[a-záéíóúüñ]{3,}\b',
        caseSensitive: false,
      ).allMatches(lowerOcr).length;
      final decimalMoneyCount = RegExp(
        r'(?<!\d)[0-9]{1,5}[\.,][0-9]{2}(?!\d)',
      ).allMatches(lowerOcr).length;

      // Actual order rows from Temu/SHEIN can be short horizontal strips: one
      // product thumbnail + color/variant text + x1. They used to be penalized
      // purely because of their aspect ratio. Preserve them when OCR looks like
      // a compact item description and not a catalog/recommendation card.
      final compactOrderRow = width >= 220 &&
          height >= 70 &&
          ratio >= 1.60 &&
          ratio <= 8.50 &&
          alphaWords >= 2 &&
          alphaWords <= 20 &&
          decimalMoneyCount <= 1 &&
          !catalogCard;
      if (compactOrderRow) score += 4;

      // Small square/portrait product tiles should not fail only because one
      // dimension is just below the old 150px threshold.
      final smallDescriptiveProduct = width >= 90 &&
          height >= 90 &&
          ratio >= 0.45 &&
          ratio <= 2.50 &&
          alphaWords >= 2 &&
          decimalMoneyCount == 0 &&
          !catalogCard;
      if (smallDescriptiveProduct) score += 2;

      if (RegExp(r'\b(size|talla|color|qty|quantity|cantidad|label size)\b').hasMatch(lowerOcr)) score += 1;
      if (RegExp(r'(?:usd\s*)?\$\s*\d+[\.,]\d{2}').hasMatch(lowerOcr)) score += 1;
      if (lowerOcr.contains('after credit applied') || lowerOcr.contains('unit price')) score += 2;
      if (ratio > 2.20 &&
          ocr.split(RegExp(r'\s+')).length >= 4 &&
          matchedItem.isEmpty &&
          !orderItemSignals &&
          !compactOrderRow) {
        score -= 3;
      }
'''
if old_scoring not in hs:
    raise SystemExit('No se encontró scoring v2/v4 esperado para aplicar v5')
hs = hs.replace(old_scoring, new_scoring, 1)

# All purchase/order Gmail lookups now use the WorkManager-backed service. The
# service still performs the immediate request for speed, but Android also has a
# one-off background job that survives minimizing the app.
background_service_class = r'''class GmailPurchaseLinkService {
  static Future<Map<String, dynamic>> reconstruct({
    String orderNumber = '',
    String tracking = '',
  }) async {
    return GmailBackgroundSearch.reconstruct(
      orderNumber: orderNumber,
      tracking: tracking,
    );
  }
}'''
hs = replace_dart_class(hs, 'GmailPurchaseLinkService', background_service_class)
helper_path.write_text(hs)


# Package editor used to call http.get directly. Route that same lookup through
# GmailBackgroundSearch without changing the existing result/UI application.
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()
request_start = ps.find("      final uri = Uri.parse('$gmailBackendUrl/api/gmail/reconstruct').replace(")
result_line = "      final data = Map<String, dynamic>.from(decoded);\n"
request_end = ps.find(result_line, request_start)
if request_start < 0 or request_end < 0:
    raise SystemExit('No se encontró request directo de Gmail en packages.dart')
request_end += len(result_line)
ps = (
    ps[:request_start]
    + "      final data = await GmailBackgroundSearch.reconstruct(\n"
      "        baseUrl: gmailBackendUrl,\n"
      "        apiKey: gmailApiKey,\n"
      "        orderNumber: order,\n"
      "        tracking: track,\n"
      "      );\n"
    + ps[request_end:]
)

notice_anchor = "    setState(() => gmailLoading = true);\n    try {\n"
notice_replacement = (
    "    setState(() => gmailLoading = true);\n"
    "    ScaffoldMessenger.of(context).showSnackBar(\n"
    "      const SnackBar(content: Text('Buscando en Gmail. Puedes minimizar la app; la búsqueda seguirá en segundo plano.')),\n"
    "    );\n"
    "    try {\n"
)
ps = replace_once(ps, notice_anchor, notice_replacement, 'aviso Gmail background package')
packages_path.write_text(ps)


# Give the purchase/order editor the same explicit feedback when a lookup starts.
purchases_path = Path('app/lib/purchases.dart')
us = purchases_path.read_text()
purchase_notice = "    setState(() => gmailPurchaseLoading = true);\n    try {\n"
if purchase_notice in us:
    us = us.replace(
        purchase_notice,
        "    setState(() => gmailPurchaseLoading = true);\n"
        "    ScaffoldMessenger.of(context).showSnackBar(\n"
        "      const SnackBar(content: Text('Buscando en Gmail. Puedes minimizar la app; la búsqueda seguirá en segundo plano.')),\n"
        "    );\n"
        "    try {\n",
        1,
    )
purchases_path.write_text(us)

print('Gmail v5 applied: real compact order rows preserved, recommendation cards rejected, background lookup enabled.')
