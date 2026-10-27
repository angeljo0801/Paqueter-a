from pathlib import Path

# v82 regression from user photos: genuine dresses, hoodies and shirts
# (images 22–35 of 39) were placed in the "Descartadas" gallery with
# "Candidata del correo para revisión", NOT a real OCR rejection.
# The analyzer only considers the first 80 current emailPhotoEntries and the
# independently saved gmailCandidateInbox is never submitted to it.
# Analyze all unique email candidates, including the independently recovered
# raw Gmail results. Retain hard transport/advertising/catalog rejections;
# never auto-accept every inbox entry or corrupt package/manual photo data.

p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()
a = s.index('Future<Map<String, dynamic>> gmailPrepareProductPhotos({')
b = s.index('\nWidget gmailSmartPhotoImage(', a)
fn = s[a:b]
assert fn.count('for (final original in images.take(80)) {') == 1, \
    'v82 analyzer 80-image cap moved'
fn = fn.replace(
    'for (final original in images.take(80)) {',
    'for (final original in images) {', 1)
assert fn.count("'candidates': images.take(80).length,") == 1, \
    'v82 analysis count hard limit moved'
fn = fn.replace("'candidates': images.take(80).length,",
                "'candidates': images.length,", 1)
s = s[:a] + fn + s[b:]
p.write_text(s)

p = Path('app/lib/packages.dart')
s = p.read_text()
a = s.index('  Future<void> _stageGmailCandidateInbox() async {')
b = s.index('  void _restoreGmailCandidateInboxReview()', a)
staging = s[a:b]
assert staging.count('        .take(80)\n') == 1, \
    'v82 inbox 80-image truncation moved'
staging = staging.replace('        .take(80)\n', '', 1)
s = s[:a] + staging + s[b:]

a = s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b = s.index('  Future<void> _showRejectedGmailPhotos() async {', a)
fn = s[a:b]
old = r'''    final uniqueImages = <String, Map<String, dynamic>>{};
    for (final entry in _emailPhotoEntries()) {
      final url = (entry['url'] ?? '').toString().trim();
      if (url.isEmpty) continue;
      final prepared = preparedByUrl[url];
      final image = prepared == null
          ? entry
          : <String, dynamic>{
              ...entry,
              ...prepared,
              'kind': entry['kind'] ?? prepared['kind'] ?? 'remote',
            };
      uniqueImages.putIfAbsent(_gmailCandidateIdentity(image), () => image);
    }
    final allImages = uniqueImages.values.toList();'''
new = r'''    final uniqueImages = <String, Map<String, dynamic>>{};
    // emailPhotoEntries() may contain only previously accepted images after a
    // save/reload. The *independent* Gmail inbox contains the genuine photos
    // which the older 80-image pass never assessed. Both sources MUST enter
    // the classifier, otherwise the review gallery shows real products with
    // "Candidata del correo para revisión" forever.
    for (final entry in <Map<String, dynamic>>[
      ..._emailPhotoEntries(),
      ...gmailCandidateInbox,
    ]) {
      final url = (entry['url'] ?? '').toString().trim();
      final original = (entry['originalUrl'] ?? '').toString().trim();
      if (url.isEmpty ||
          hiddenEmailPhotoUrls.contains(url) ||
          (original.isNotEmpty && hiddenEmailPhotoUrls.contains(original))) {
        continue;
      }
      final prepared = preparedByUrl[url] ?? preparedByUrl[original];
      final image = prepared == null
          ? <String, dynamic>{
              ...entry,
              'kind': entry['kind'] ?? 'remote',
            }
          : <String, dynamic>{
              ...entry,
              ...prepared,
              'kind': prepared['kind'] ?? entry['kind'] ?? 'remote',
            };
      final identity = _gmailCandidateIdentity(image);
      uniqueImages.putIfAbsent(identity, () => image);
    }
    final allImages = uniqueImages.values.toList();'''
assert fn.count(old) == 1, 'v82 candidate mapper changed in v63'
fn = fn.replace(old, new, 1)

# Prevent preview-only candidate rows from lingering as "discarded" after
# their actual classification. The existing _restoreGmailCandidateInboxReview
# can only restore a raw inbox candidate if no accepted/rejected matching
# identity is already present; the smart filter now covers the whole inbox.
assert fn.count('_restoreGmailCandidateInboxReview();') == 1, \
    'v82 review status merge location changed'
assert fn.index('final allImages = uniqueImages.values.toList();') < \
       fn.index('gmailPrepareProductPhotos(')
s = s[:a] + fn + s[b:]
p.write_text(s)

assert "for (final original in images) {" in \
    Path('app/lib/gmail_purchase_link.dart').read_text()
assert '...gmailCandidateInbox,' in s
assert "        .take(80)" not in staging
assert 'final allImages = uniqueImages.values.toList();' in s
print('v82: analyze ALL unique Gmail photos including durable inbox; no raw candidate falsely discarded for being beyond 80.')
