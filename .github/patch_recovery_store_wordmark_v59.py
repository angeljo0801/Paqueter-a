from pathlib import Path

# v59 -- A brand wordmark (e.g. a white SHEIN logo) must never be promoted to
# a purchase photo merely because it appears inside the verified first email.
# This is a deliberately narrow OCR veto. Product watches without readable
# descriptions and product thumbnails containing logos remain eligible.
p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()
anchor = 'Future<Map<String, dynamic>> gmailPrepareProductPhotos({'
assert s.count(anchor) == 1, 'v59 Gmail photo classifier missing'
helper = r'''
// Only a standalone shop wordmark is a logo, not an item photo.
// OCR strings can include trademark signs, punctuation or separate letters.
// Do NOT reject regular item photos just because SHEIN/Temu is mentioned
// alongside product names, sizes, prices, or in the original image URL.
bool gmailIsIsolatedStoreWordmark(String ocr) {
  final compressed = ocr.toLowerCase()
      .replaceAll(RegExp(r'[\s\-_.,:;!|/\\®™©]+'), '');
  return compressed == 'shein' || compressed == 'temu';
}

'''
s = s.replace(anchor, helper + anchor, 1)

a=s.index(anchor)
b=s.index('\nWidget gmailSmartPhotoImage(',a)
fn=s[a:b]
# Hard rejection occurs immediately after OCR, BEFORE the v58 verified-source
# override and geometry points can accept a real shop logo.
needle = '''      if (_gmailPromoText(ocr) && !trustedProductShape) {'''
assert fn.count(needle)==1, 'v59: expected promotion/geometry filter after OCR'
logo = r'''      // The screenshot with only "SHEIN" is a brand asset, not a watch.
      // Reject only when the whole recognized text is that single wordmark.
      // Merely seeing the store name inside a real product card is fine.
      if (gmailIsIsolatedStoreWordmark(ocr)) {
        await temp.delete().catchError((_) => temp);
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'ocrText': ocr,
          'rejectReason': 'logotipo de tienda (no artículo)',
          'photoClass': 'store_wordmark',
        });
        continue;
      }

'''
fn = fn.replace(needle, logo + needle, 1)
assert fn.index('gmailIsIsolatedStoreWordmark(ocr)') < fn.index(needle)
s=s[:a]+fn+s[b:]
p.write_text(s)

# The v58 empty-gallery safety net must not undo the explicit brand-wordmark
# rejection (it used to reintroduce every square image on an empty result).
p=Path('app/lib/packages.dart')
s=p.read_text()
a=s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b=s.index('  Future<void> _showRejectedGmailPhotos() async {',a)
fn=s[a:b]
# v46 must not resurrect an old accepted logo when the new OCR correctly
# identifies it as a wordmark (its preserve-previous-photo branch ran early).
prior = "    if (accepted.isEmpty) {\n"
assert fn.count(prior)>=2, 'v59 legacy preservation structure unavailable'
fn=fn.replace(prior, '''    final isolatedWordmarkUrls = rejected
        .where((e) => e['photoClass'] == 'store_wordmark' ||
            e['rejectReason'] == 'logotipo de tienda (no artículo)')
        .map((e) => (e['url'] ?? '').toString().trim())
        .where((u) => u.isNotEmpty).toSet();
    if (accepted.isEmpty) {
''',1)
old = '''        if (url.isEmpty || !previousUrls.contains(url) ||
            hiddenEmailPhotoUrls.contains(url) || !present.add(url)) continue;'''
new = '''        if (url.isEmpty || !previousUrls.contains(url) ||
            isolatedWordmarkUrls.contains(url) ||
            hiddenEmailPhotoUrls.contains(url) || !present.add(url)) continue;'''
assert fn.count(old)==1, 'v59 old saved photo resurrection guard missing'
fn=fn.replace(old,new,1)
anchor = '''      for (final image in gmailCandidateInbox) {'''
assert fn.count(anchor)==1, 'v59 verified source fallback loop missing'
fn=fn.replace(anchor, '''      for (final image in gmailCandidateInbox) {''',1)
needle = '''        if (url.isEmpty || hiddenEmailPhotoUrls.contains(url) ||
            image['deliveryProofHint'] == true ||'''
assert fn.count(needle)==1, 'v59 fallback rejection check missing'
fn=fn.replace(needle, '''        if (url.isEmpty || hiddenEmailPhotoUrls.contains(url) ||
            isolatedWordmarkUrls.contains(url) ||
            image['deliveryProofHint'] == true ||''',1)
s=s[:a]+fn+s[b:]
p.write_text(s)

# Once the refreshed OCR identifies a logo, do not quietly resurrect an
# earlier saved copy when the new search has no other accepted image.
a=s.index('  Future<void> _persistRecoveredGmailSnapshot() async {')
b=s.index('  Future<void> removeMultipleEmailPhotos() async {', a)
fn=s[a:b]
needle="    final keptUrls = emailPhotoUrls"
assert fn.count(needle)==1, 'v59 auto-save guard missing'
fn=fn.replace(needle, """    final rejectedBrandUrls = gmailRejectedImages
        .where((e) => e['photoClass'] == 'store_wordmark' ||
            e['rejectReason'] == 'logotipo de tienda (no artículo)')
        .map((e) => (e['url'] ?? '').toString().trim())
        .where((url) => url.isNotEmpty).toSet();
""" + needle,1)
needle="    final mergedOffline = <String, String>{"
assert fn.count(needle)==1, 'v59 persistence merge missing'
fn=fn.replace(needle, """    // Only remove logo images *recognized by this fresh search*. Do not
    // erase legitimate purchases or unrelated user photos.
    keptUrls.removeWhere(rejectedBrandUrls.contains);
    keptAttachments.removeWhere((entry) =>
        rejectedBrandUrls.contains((entry['url'] ?? '').toString().trim()));
""" + needle,1)
s=s[:a]+fn+s[b:]
p.write_text(s)

# Regression guards, checked at build time against generated Dart sources.
h=Path('app/lib/gmail_purchase_link.dart').read_text()
a=h.index('Future<Map<String, dynamic>> gmailPrepareProductPhotos({')
b=h.index('\nWidget gmailSmartPhotoImage(',a)
fn=h[a:b]
assert fn.index('if (gmailIsIsolatedStoreWordmark(ocr))') < fn.index('if (_gmailPromoText(ocr)') 
assert fn.index('if (gmailIsIsolatedStoreWordmark(ocr))') < fn.index('if (score < 2')
assert "return compressed == 'shein' || compressed == 'temu';" in h
assert 'isolatedWordmarkUrls.contains(url)' in s
assert 'keptUrls.removeWhere(rejectedBrandUrls.contains);' in s
print('v59: standalone SHEIN/Temu logos rejected, real product photos and fallback retained.')
