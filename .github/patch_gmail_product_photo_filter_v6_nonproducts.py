from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# v6: v5 correctly recovered genuine compact product rows such as the Temu
# bottle row, but its compact-row heuristic was too permissive and also let
# through status banners, payment-information cards, tracking banners and
# category promos. Keep real compact item rows, but require actual item cues and
# explicitly reject the non-product UI observed in the reported screenshots.
helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()

start = hs.find('bool gmailCatalogRecommendationCard(String text) {')
end = hs.find('\n}\n\nbool _gmailUrlClearlyNotProduct', start)
if start < 0 or end < 0:
    raise SystemExit('No se encontró gmailCatalogRecommendationCard para aplicar v6')
end += 2

catalog_v6 = r'''bool gmailCatalogRecommendationCard(String text) {
  final lower = text.toLowerCase().replaceAll(RegExp(r'\s+'), ' ').trim();
  if (lower.isEmpty) return false;
  if (_gmailPromoText(lower)) return true;

  final orderSignals = gmailOrderItemPhotoSignals(lower);
  final priceCount = RegExp(
    r'(?:us\$|usd\s*\$?|\$)\s*[0-9][0-9,]*(?:[\.,][0-9]{1,2})?',
    caseSensitive: false,
  ).allMatches(lower).length;
  final decimalMoneyCount = RegExp(
    r'(?<!\d)[0-9]{1,5}[\.,][0-9]{2}(?!\d)',
  ).allMatches(lower).length;

  // Gmail v6 utility/status-card guard. These are interface or logistics
  // graphics, not photos of the purchased article.
  final statusOrLogisticsUi = <String>[
    'order in transit',
    'order shipped',
    'order shipped and tracking number ready',
    'tracking number ready',
    'package in transit',
    'package shipped',
    'shipment in transit',
    'shipment shipped',
    'view details on gofo',
    'track package',
    'track your package',
    'tracking details',
    'delivery status',
  ].any(lower.contains);

  final paymentSafetyUi = <String>[
    'safe payments',
    'payment information is safe',
    'credit card information',
    'does not share your credit card',
    'secure payment',
    'payment protection',
    'learn more',
  ].any(lower.contains);

  final carrierTrackingUi =
      RegExp(r'\bgfus[a-z0-9*]{4,}\b', caseSensitive: false).hasMatch(lower) ||
      (lower.contains('gofo') && lower.contains('view details'));

  if (!orderSignals && (statusOrLogisticsUi || paymentSafetyUi || carrierTrackingUi)) {
    return true;
  }

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

hs = hs[:start] + catalog_v6 + hs[end:]

old_compact = r'''      final compactOrderRow = width >= 220 &&
          height >= 70 &&
          ratio >= 1.60 &&
          ratio <= 8.50 &&
          alphaWords >= 2 &&
          alphaWords <= 20 &&
          decimalMoneyCount <= 1 &&
          !catalogCard;
      if (compactOrderRow) score += 4;
'''

new_compact = r'''      final quantityCue = RegExp(
        r'(?:^|\s)[x×]\s*\d{1,3}(?:\s|$)|\b(?:qty|quantity|cantidad)\s*[:#-]?\s*\d{1,3}\b',
        caseSensitive: false,
      ).hasMatch(lowerOcr);
      final variantCue = RegExp(
        r'\b(?:color|colour|size|talla|variant|style)\b',
        caseSensitive: false,
      ).hasMatch(lowerOcr);
      final compactItemCue = orderItemSignals ||
          matchedItem.isNotEmpty ||
          quantityCue ||
          (variantCue && alphaWords >= 2);

      // A compact/wide image is accepted only when it actually looks like an
      // item row. Generic text strips such as “Order in transit”, “Safe
      // payments”, GOFO tracking cards or category banners no longer qualify.
      final compactOrderRow = width >= 220 &&
          height >= 70 &&
          ratio >= 1.60 &&
          ratio <= 8.50 &&
          alphaWords >= 2 &&
          alphaWords <= 20 &&
          decimalMoneyCount <= 1 &&
          compactItemCue &&
          !catalogCard;
      if (compactOrderRow) score += 4;
'''

hs = replace_once(hs, old_compact, new_compact, 'compact Gmail row v5 -> v6')
helper_path.write_text(hs)

print('Gmail v6 applied: status/payment/tracking/category cards rejected; real compact item rows preserved.')
