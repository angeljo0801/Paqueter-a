from pathlib import Path

# v71: the screenshots show three false positives in Gmail product photos:
# 1) a fashion-glasses *catalog listing* with a second crossed-out price,
#    review stars and "add to cart";
# 2) a tiny green protection/shield pictogram;
# 3) an orange Temu "Order out for delivery" tracking/status strip.
#
# Preserve v67-v69 short "1pc" photo/quantity rows, the watches, footwear,
# product thumbnails and the manual-recovery gallery. Avoid store-specific URL
# word bans or a generic "small" / "wide" rejection.

helper_path = Path('app/lib/gmail_purchase_link.dart')
s = helper_path.read_text()
anchor = 'Future<Map<String, dynamic>> gmailPrepareProductPhotos({'
assert s.count(anchor) == 1, 'v71: Gmail photo helper missing'

helpers = r'''
// A strong status phrase is different from an item description containing
// "shipping" or "delivered". These words appear in a courier/status banner.
bool gmailIsExplicitDeliveryStatusArtwork(String text) {
  final lower = text.toLowerCase().replaceAll(RegExp(r'\s+'), ' ').trim();
  return <String>[
    'order out for delivery',
    'out for delivery',
    'your order is on the way',
    'order is on the way',
    'your package is out for delivery',
    'your parcel is out for delivery',
    'pedido en reparto',
    'pedido en camino para entrega',
  ].any(lower.contains);
}

// OCR may miss the words if 80 other thumbnails consumed its budget.
// Temu's observed status strip is a near-black horizontal banner with the
// small orange Temu square at the FAR LEFT and pale delivery status at RIGHT.
// A photographic product+quantity row has texture/colorful image content and
// cannot pass this very specific geometry/palette signature.
Future<bool> gmailLooksLikeDarkTemuDeliveryStatusStrip(
  List<int> bytes, int width, int height,
) async {
  if (width < 220 || height < 35 ||
      width / height < 2.80 || width / height > 22) return false;
  try {
    final codec = await ui.instantiateImageCodec(
      Uint8List.fromList(bytes), targetWidth: width > 256 ? 256 : null,
    );
    try {
      final frame = await codec.getNextFrame();
      try {
        final img = frame.image;
        final data = await img.toByteData(format: ui.ImageByteFormat.rawRgba);
        if (data == null) return false;
        final px = data.buffer.asUint8List();
        final w = img.width;
        var total = 0, dark = 0, orangeLeft = 0, paleRight = 0;
        var vividLeftNotOrange = 0;
        for (var i = 0; i + 3 < px.length; i += 4) {
          if (px[i + 3] < 128) continue;
          final x = ((i ~/ 4) % w) / w;
          final r = px[i], g = px[i + 1], b = px[i + 2];
          final lum = (r * 299 + g * 587 + b * 114) ~/ 1000;
          total++;
          if (lum < 80) dark++;
          final orange = r >= 155 && g >= 46 && g <= 188 &&
              b < 100 && r > g * 1.30;
          if (x < .26 && orange) orangeLeft++;
          if (x < .32 && !orange &&
              ((r - g).abs() > 85 || (g - b).abs() > 85)) {
            vividLeftNotOrange++;
          }
          if (x > .55 && lum >= 125) paleRight++;
        }
        if (total < 350) return false;
        return dark / total >= .70 &&
            orangeLeft / total >= .007 &&
            orangeLeft / total <= .19 &&
            vividLeftNotOrange / total < .07 &&
            paleRight / total >= .002;
      } finally {
        frame.image.dispose();
      }
    } finally {
      codec.dispose();
    }
  } catch (_) { return false; }
}

// Narrow second check for the user's green shield: a small muted-green
// square with a brighter green *line* symbol. A green product photograph
// normally has broader color diversity or a different layout. This guard
// only runs when the image has no order-item/name match.
Future<bool> gmailLooksLikeGreenSafetyTile(
  List<int> bytes, int width, int height,
) async {
  if (width < 90 || height < 90 ||
      width > 260 || height > 260 ||
      width / height < .78 || width / height > 1.30) return false;
  try {
    final codec = await ui.instantiateImageCodec(
      Uint8List.fromList(bytes),
      targetWidth: 96, targetHeight: 96,
    );
    try {
      final frame = await codec.getNextFrame();
      try {
        final data = await frame.image.toByteData(
            format: ui.ImageByteFormat.rawRgba);
        if (data == null) return false;
        final px = data.buffer.asUint8List();
        var total = 0, symbol = 0, ground = 0;
        final bins = <int, int>{};
        for (var i = 0; i + 3 < px.length; i += 4) {
          if (px[i + 3] < 128) continue;
          final r = px[i], g = px[i + 1], b = px[i + 2];
          total++;
          if (r < 50 && g >= 85 && b < 55 && g > r * 1.8 &&
              g > b * 1.7) symbol++;
          if (r >= 35 && r <= 120 && g >= 70 && g <= 160 &&
              b >= 35 && b <= 125 && g > r) ground++;
          final key = ((r >> 5) << 6) |
              ((g >> 5) << 3) | (b >> 5);
          bins[key] = (bins[key] ?? 0) + 1;
        }
        if (total < 400 || bins.length > 27) return false;
        return symbol / total >= .075 &&
            symbol / total <= .58 &&
            ground / total >= .25;
      } finally {
        frame.image.dispose();
      }
    } finally {
      codec.dispose();
    }
  } catch (_) { return false; }
}

// A genuine order photo can have a price; do not reject for ONE price.
// Marketplace suggestions frequently show TWO retail prices: current and
// crossed-out, or OCR two decimal amounts without currency symbols.
bool gmailHasTwoCatalogPrices(String ocr) {
  final normalized = ocr.toLowerCase();
  final money = RegExp(
    r'(?:us\$|usd\s*\$?|\$)\s*\d{1,6}(?:[.,]\d{1,2})?',
    caseSensitive: false,
  ).allMatches(normalized).length;
  final decimals = RegExp(
    r'(?<!\d)\d{1,5}[.,]\d{2}(?!\d)',
  ).allMatches(normalized).length;
  return money >= 2 || decimals >= 2;
}

// Strong visual confirmation of a listing CARD rather than an order-row
// screenshot: product photograph above, then broad WHITE lower footer with
// dark title/prices/stars/cart treatment. Never use it by itself: two prices
// in OCR and no purchase-item match are ALSO required by the caller.
Future<bool> gmailHasMarketplaceListingFooter(
  List<int> bytes, int width, int height,
) async {
  if (width < 180 || height < 230 ||
      width / height < .50 || width / height > 1.80) return false;
  try {
    final codec = await ui.instantiateImageCodec(
      Uint8List.fromList(bytes), targetWidth: width > 160 ? 160 : null,
    );
    try {
      final frame = await codec.getNextFrame();
      try {
        final img = frame.image;
        final data = await img.toByteData(format: ui.ImageByteFormat.rawRgba);
        if (data == null) return false;
        final px = data.buffer.asUint8List();
        var topTotal = 0, topWhite = 0;
        var footerTotal = 0, footerWhite = 0, footerDark = 0;
        for (var i = 0; i + 3 < px.length; i += 4) {
          if (px[i + 3] < 128) continue;
          final y = ((i ~/ 4) ~/ img.width) / img.height;
          final r = px[i], g = px[i + 1], b = px[i + 2];
          final white = r >= 205 && g >= 205 && b >= 205;
          if (y <= .62) {
            topTotal++;
            if (white) topWhite++;
          } else if (y >= .73) {
            footerTotal++;
            if (white) footerWhite++;
            if (r < 95 && g < 95 && b < 95) footerDark++;
          }
        }
        if (topTotal < 400 || footerTotal < 250) return false;
        return topWhite / topTotal < .58 &&
            footerWhite / footerTotal >= .68 &&
            footerDark / footerTotal >= .018;
      } finally {
        frame.image.dispose();
      }
    } finally {
      codec.dispose();
    }
  } catch (_) { return false; }
}

'''
s = s.replace(anchor, helpers + anchor, 1)

a = s.index(anchor)
b = s.index('\nWidget gmailSmartPhotoImage(', a)
fn = s[a:b]

old = '''          await gmailLooksLikeStandaloneUiSymbol(bytes, width, height)) {'''
new = '''          (await gmailLooksLikeStandaloneUiSymbol(bytes, width, height) ||
           await gmailLooksLikeGreenSafetyTile(bytes, width, height))) {'''
assert fn.count(old) == 1, 'v71: v70 standalone symbol guard moved'
fn = fn.replace(old, new, 1)

needle = '''      final catalogCard = gmailCatalogRecommendationCard(ocr);'''
assert fn.count(needle) == 1, 'v71: OCR catalog decision moved'
insert = r'''      // Do not let a verified retailer email or a mistaken productRowHint
      // promote delivery status artwork into an actual order item.
      if (matchedItem.isEmpty &&
          !orderItemSignals &&
          image['manuallyAccepted'] != true &&
          (gmailIsExplicitDeliveryStatusArtwork(ocr) ||
           await gmailLooksLikeDarkTemuDeliveryStatusStrip(
             bytes, width, height))) {
        await temp.delete().catchError((_) => temp);
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'ocrText': ocr,
          'rejectReason': 'banner de estado de entrega (no artículo)',
          'photoClass': 'delivery_status_banner',
        });
        continue;
      }

      // Visually confirmed retailer *listing*, not a purchased order row.
      // Requiring all three independent signals protects small/large genuine
      // item photographs, order quantities, watches, and 1pc thumbnail rows.
      if (matchedItem.isEmpty &&
          !orderItemSignals &&
          image['manuallyAccepted'] != true &&
          gmailHasTwoCatalogPrices(ocr) &&
          await gmailHasMarketplaceListingFooter(bytes, width, height)) {
        await temp.delete().catchError((_) => temp);
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'ocrText': ocr,
          'rejectReason': 'tarjeta de catálogo con precio/oferta (no artículo)',
          'photoClass': 'catalog_card',
        });
        continue;
      }
'''
fn = fn.replace(needle, insert + needle, 1)
assert fn.index('gmailHasTwoCatalogPrices(ocr)') < fn.index('if (sectionProduct) score += 8;')
assert fn.index('gmailLooksLikeDarkTemuDeliveryStatusStrip(') < fn.index('if (sectionProduct) score += 8;')
assert 'if (shortItemPhotoRow) score += 6;' in fn
assert 'final compactPhotoRow = photographicRowCandidate;' in fn
s = s[:a] + fn + s[b:]
helper_path.write_text(s)

# Guard package-level safety fallbacks and the persisted photo merge. These
# previously protected only hard-excluded store/transport graphics; without
# this step the same URL could be silently resurrected after classification.
p = Path('app/lib/packages.dart')
s = p.read_text()
hard = "              e['photoClass'] == 'app_install_banner' ||"
hard_new = hard + "\n              e['photoClass'] == 'delivery_status_banner' ||\n              e['photoClass'] == 'catalog_card' ||"
assert s.count(hard) == 1, 'v71: package fallback hard classes moved'
s = s.replace(hard, hard_new, 1)
persist = "            e['photoClass'] == 'app_install_banner' ||"
persist_new = persist + "\n            e['photoClass'] == 'delivery_status_banner' ||\n            e['photoClass'] == 'catalog_card' ||"
assert s.count(persist) == 1, 'v71: persist hard classes moved'
s = s.replace(persist, persist_new, 1)

identities = """          .where((e) => e['photoClass'] == 'store_wordmark')"""
assert s.count(identities) == 1, 'v71: digest fallback rejection moved'
s = s.replace(identities, """          .where((e) => e['photoClass'] == 'store_wordmark' ||
              e['photoClass'] == 'delivery_status_banner' ||
              e['photoClass'] == 'catalog_card')""", 1)

assert "e['photoClass'] == 'catalog_card'" in s
assert "e['photoClass'] == 'delivery_status_banner'" in s
assert 'rejectedWordmarkIds.contains(_gmailCandidateIdentity(image))' in s
p.write_text(s)
print('v71: social/security icons, Temu delivery strip and double-price listing filtered; real compact product photos and manual review preserved.')
