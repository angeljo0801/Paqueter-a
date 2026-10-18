from pathlib import Path

# v58: A verified retailer thumbnail is a product candidate even if OCR sees
# stars, prices or banner words. OCR is used for ranking, never as the sole
# reason to throw away a watch/other real product. All raw candidates remain
# in the separately persisted Gmail review inbox.
p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()
start = s.index('bool _gmailUrlClearlyNotProduct(String url) {')
end = s.index('\n}\n', start) + 2
old = s[start:end]
assert "bool _gmailUrlClearlyNotProduct(String url)" in old, 'v58 URL filter moved'
s = s[:start] + r'''bool _gmailUrlClearlyNotProduct(String url) {
  // A product image URL can contain "tracking", "banner", "icon" or "logo"
  // as an unrelated query value. Reject only explicit tracking pixels.
  final path = (Uri.tryParse(url)?.path ?? url).toLowerCase();
  return RegExp(
    r'(?:^|[/_-])(?:tracking[-_]?pixel|pixel|beacon|spacer)(?:[/_.-]|$)',
    caseSensitive: false,
  ).hasMatch(path);
}''' + s[end:]

a = s.index('Future<Map<String, dynamic>> gmailPrepareProductPhotos({')
b = s.index('\nWidget gmailSmartPhotoImage(', a)
fn = s[a:b]
def one(old, new, label):
    global fn
    assert fn.count(old) == 1, f'v58 changed anchor {label}: {fn.count(old)}'
    fn = fn.replace(old, new, 1)

# Some actual watch thumbnails compress to fewer than 3500 bytes.
one('if (bytes.length < 3500 || bytes.length > 10 * 1024 * 1024)',
    'if (bytes.length < (matchedStoreSource ? 500 : 3500) || bytes.length > 10 * 1024 * 1024)',
    'minimum compressed bytes')

# A prepared Railway original can expire while its cached thumbnail still
# works; check the thumbnail before declaring a photo unavailable.
one('''      final response = await http.get(
        Uri.parse(resolved),
        headers: gmailPhotoHeaders(baseUrl, apiKey, analysisImage) ?? const <String, String>{},
      ).timeout(const Duration(seconds: 18));
      if (response.statusCode < 200 || response.statusCode >= 300) {''',
    '''      http.Response response;
      try {
        response = await http.get(
          Uri.parse(resolved),
          headers: gmailPhotoHeaders(baseUrl, apiKey, analysisImage) ??
              const <String, String>{},
        ).timeout(const Duration(seconds: 12));
      } catch (_) {
        response = http.Response('', 503);
      }
      // Retry the original URL if the prepared Railway thumbnail is missing.
      if ((response.statusCode < 200 || response.statusCode >= 300 ||
           response.bodyBytes.isEmpty) && analysisRaw != rawUrl) {
        try {
          response = await http.get(
            Uri.parse(gmailPhotoUrl(baseUrl, image)),
            headers: gmailPhotoHeaders(baseUrl, apiKey, image) ??
                const <String, String>{},
          ).timeout(const Duration(seconds: 12));
        } catch (_) {}
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {''',
    'thumbnail network fallback')

one('''      final ratio = width > 0 && height > 0 ? width / height : 1.0;''',
    '''      final ratio = width > 0 && height > 0 ? width / height : 1.0;
      // Positive provenance and actual decoded product-like geometry outweigh
      // incidental OCR text. Never override courier delivery-proof context.
      final trustedProductShape = matchedStoreSource &&
          !deliveryProofHint &&
          width >= 70 && height >= 70 &&
          ratio >= 0.62 && ratio <= 1.58;''',
    'square product trust')

one('if (_gmailPromoText(ocr)) {',
    'if (_gmailPromoText(ocr) && !trustedProductShape) {',
    'OCR promotions not a veto')
one('if (catalogCard && !orderItemSignals) {',
    'if (catalogCard && !orderItemSignals && !trustedProductShape) {',
    'OCR star/cart text not a veto')

# The v56 bonus requires too many additional conditions for a simple watch.
one('''      if (sourceThumbnail || verifiedSquareProductImage) {
        score += 3;''',
    '''      if (sourceThumbnail || verifiedSquareProductImage || trustedProductShape) {
        score += 3;''',
    'product shape scoring')
one('if (score < 2) {','if (score < 2 && !trustedProductShape) {',
    'insufficient OCR evidence')
s = s[:a] + fn + s[b:]
p.write_text(s)

p = Path('app/lib/packages.dart')
s = p.read_text()
a = s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b = s.index('  Future<void> _showRejectedGmailPhotos() async {', a)
fn = s[a:b]
anchor = "    final offline = result['offlinePaths'];"
assert fn.count(anchor) == 1, 'v58 no package gallery handoff'
safe_fallback = r'''    // The user asked Gmail to collect product photos. If OCR/network
    // analysis accepts nothing, show plausible images from this VERIFIED
    // tracking's retailer emails as unverified rather than an empty gallery.
    // All original candidates are retained in the review inbox either way.
    if (accepted.isEmpty &&
        (gmailVerifiedPhotoSourceRule.startsWith('shein_predelivery_first') ||
         gmailVerifiedPhotoSourceRule.startsWith('temu_latest_first'))) {
      for (final image in gmailCandidateInbox) {
        final url = (image['url'] ?? '').toString().trim();
        if (url.isEmpty || hiddenEmailPhotoUrls.contains(url) ||
            image['deliveryProofHint'] == true ||
            gmailDeliveryPhotoHints.contains(url)) continue;
        final width = (image['width'] as num?)?.toInt() ?? 0;
        final height = (image['height'] as num?)?.toInt() ?? 0;
        if (width > 0 && height > 0) {
          final ratio = width / height;
          if (width < 70 || height < 70 || ratio < 0.62 || ratio > 1.58) continue;
        }
        if (_gmailUrlClearlyNotProduct(url)) continue;
        accepted.add({
          ...image, 'photoClass': 'pending_product_review',
          'rejectReason': '',
        });
        if (accepted.length >= 24) break;
      }
      final fallbackUrls = accepted.map(
        (e) => (e['url'] ?? '').toString().trim()).toSet();
      rejected.removeWhere(
        (e) => fallbackUrls.contains((e['url'] ?? '').toString().trim()));
    }
'''
fn = fn.replace(anchor, safe_fallback + anchor, 1)
s = s[:a] + fn + s[b:]
p.write_text(s)
print('v58: watch-safe OCR, Railway thumbnail retry, and verified Gmail photos retained in gallery.')
