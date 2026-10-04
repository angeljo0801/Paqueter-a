from pathlib import Path

p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()

start = s.find('bool gmailCatalogRecommendationCard(String text) {')
end = s.find('\n}\n\nbool _gmailUrlClearlyNotProduct', start)
if start < 0 or end < 0:
    raise SystemExit('No se encontró gmailCatalogRecommendationCard para aplicar v3')
end += 2

new = r'''bool gmailCatalogRecommendationCard(String text) {
  final lower = text.toLowerCase().replaceAll(RegExp(r'\s+'), ' ').trim();
  if (lower.isEmpty) return false;

  // v3: We are selecting useful product/order photos, NOT screenshots of a
  // storefront/catalog UI. These UI signals override order-item text because
  // a catalog card can also contain size/color/price words.
  if (_gmailPromoText(lower)) return true;

  final priceCount = RegExp(
    r'(?:us\$|usd\s*\$?|\$)\s*[0-9][0-9,]*(?:[\.,][0-9]{1,2})?',
    caseSensitive: false,
  ).allMatches(lower).length;

  final starGlyphs = RegExp(r'(?:★|☆|⭐|✩|✭|✮|✯|✰){1,}').hasMatch(text);
  final ratingWords = RegExp(
    r'\b(?:rating|ratings|review|reviews|stars?|valoraci[oó]n|reseñas?)\b',
    caseSensitive: false,
  ).hasMatch(lower);
  final ratingNumber = RegExp(r'\b[0-5](?:[\.,][0-9])?\s*(?:/\s*5|stars?)\b').hasMatch(lower);

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

  // A visible rating/star treatment or cart/buy UI is a storefront screenshot,
  // like the Halloween example. Do not keep it as a product photo even when it
  // contains a valid price or item description.
  if (starGlyphs || ratingWords || ratingNumber || cartUi || catalogUi || nonProductUi) {
    return true;
  }

  // Multiple prices commonly mean catalog/list price + sale price. Preserve an
  // actual order row when it has explicit order-line evidence.
  if (priceCount >= 2 && !gmailOrderItemPhotoSignals(lower)) return true;
  return false;
}'''

s = s[:start] + new + s[end:]
p.write_text(s)
print('Gmail product-photo filter v3 applied: storefront UI/cart/stars/reviews rejected.')
