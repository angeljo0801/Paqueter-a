from pathlib import Path

# v55: user-triggered "Buscar por Gmail" is NOT a cached-result replay.
# Resume jobs keep the old token, but the explicit button starts a fresh
# backend search and forgets previous local hide markers only after real
# photos arrive. Preserve selected photos if the network fails.
p=Path('app/lib/background_sync.dart')
s=p.read_text()
a=s.index('class GmailBackgroundSearch {')
b=s.index('\nclass NotificationService',a)
fn=s[a:b]
needle="    bool autoAcknowledge = true,\n  }) async {"
assert fn.count(needle)==1, 'v55 background reconstruct signature changed'
fn=fn.replace(needle,"    bool autoAcknowledge = true,\n    bool freshSearch = false,\n  }) async {",1)
needle="""    final pendingKey = _pendingKey(slot);
    await prefs.reload();"""
assert fn.count(needle)==1, 'v55 slot preference anchor changed'
fn=fn.replace(needle,"""    final pendingKey = _pendingKey(slot);
    if (freshSearch) {
      // Invalidate ONLY this tracking's cached completion. Old workers use
      // another token and cannot overwrite the newly requested search.
      await prefs.remove(pendingKey);
      await prefs.remove(_resultKey(slot));
      await prefs.remove(_errorKey(slot));
    }
    await prefs.reload();""",1)
s=s[:a]+fn+s[b:]
p.write_text(s)

p=Path('app/lib/packages.dart')
s=p.read_text()
a=s.index('  Future<void> reconstructFromGmail() async {')
b=s.index('  Future<void> openEmailPhoto(',a)
flow=s[a:b]
needle="        autoAcknowledge: false,\n"
assert flow.count(needle)==1, 'v55 Gmail foreground request anchor changed'
flow=flow.replace(needle,needle+"        freshSearch: !_recoveringFinishedGmailSearch,\n",1)
s=s[:a]+flow+s[b:]

# Canonical identity is the server's digest-named thumbnail if one exists;
# otherwise use the original remote URL. Do not show identical accepted and
# rejected images twice just because two emails carried the same photo.
needle='  void _restoreGmailCandidateInboxReview() {'
assert s.count(needle)==1
helpers=r'''  String _gmailCandidateIdentity(Map<String, dynamic> image) {
    final thumbnail = (image['thumbnailUrl'] ?? '').toString().trim();
    if (thumbnail.isNotEmpty) return 'thumb:$thumbnail';
    final original = (image['originalUrl'] ?? '').toString().trim();
    if (original.isNotEmpty) return 'url:$original';
    return 'url:';
  }

'''
s=s.replace(needle,helpers+needle,1)

# The button's explicit search gets brand-new Gmail images; background job
# recovery never empties/overwrites the current gallery this way.
needle="  Future<void> _captureRawGmailPhotoResult(Map<String, dynamic> data) async {"
assert s.count(needle)==1
s=s.replace(needle,needle+r'''
    final hasServerImages =
        dynList(data['emailPhotoCandidates']).isNotEmpty ||
        dynList(data['emailPhotoUrls']).isNotEmpty ||
        dynList(data['emailAttachmentImages']).isNotEmpty;
    if (!_recoveringFinishedGmailSearch &&
        data['found'] == true && hasServerImages) {
      hiddenEmailPhotoUrls.clear();
      gmailCandidateInbox.clear();
      gmailRejectedImages.clear();
      emailPhotoUrls.clear();
      emailAttachmentImages.clear();
      // Keep offline image files, pending items and learned preferences.
      // Deleting a photo from the package never deletes its Gmail source.
    }
''',1)

# De-duplicate when capturing candidates from candidate+remote+attachment
# server fields. The same remote URL may have multiple representations.
a=s.index('  Future<void> _captureRawGmailPhotoResult(')
b=s.index('  Future<void> _stageGmailCandidateInbox() async {',a)
raw=s[a:b]
needle="    final seen = <String>{};"
assert raw.count(needle)==1
raw=raw.replace(needle,needle+"\n    final seenImages = <String>{};",1)
needle="      if (url.isEmpty || hiddenEmailPhotoUrls.contains(url) || !seen.add(url)) return;\n      candidates.add(Map<String, dynamic>.from(image));"
assert raw.count(needle)==1
raw=raw.replace(needle,"""      if (url.isEmpty || hiddenEmailPhotoUrls.contains(url) || !seen.add(url)) return;
      final identity = _gmailCandidateIdentity(image);
      if (!seenImages.add(identity)) return;
      candidates.add(Map<String, dynamic>.from(image));""",1)
needle="""    final merged = <String, Map<String, dynamic>>{};
    for (final image in [...gmailCandidateInbox, ...candidates]) {
      final url = (image['url'] ?? '').toString().trim();
      if (url.isNotEmpty && !hiddenEmailPhotoUrls.contains(url)) merged[url] = image;
    }"""
assert raw.count(needle)==1
raw=raw.replace(needle,"""    final merged = <String, Map<String, dynamic>>{};
    for (final image in [...gmailCandidateInbox, ...candidates]) {
      final url = (image['url'] ?? '').toString().trim();
      if (url.isNotEmpty && !hiddenEmailPhotoUrls.contains(url)) {
        merged.putIfAbsent(_gmailCandidateIdentity(image), () => image);
      }
    }""",1)
s=s[:a]+raw+s[b:]

# Staging must NOT add a second copy of every accepted thumbnail.
a=s.index('  Future<void> _stageGmailCandidateInbox() async {')
b=s.index('  void _restoreGmailCandidateInboxReview()',a)
part=s[a:b]
needle="      if (url.isEmpty || hiddenEmailPhotoUrls.contains(url) || !seen.add(url)) continue;"
assert part.count(needle)==1
part=part.replace(needle,"      if (url.isEmpty || hiddenEmailPhotoUrls.contains(url) || !seen.add(_gmailCandidateIdentity(image))) continue;",1)
s=s[:a]+part+s[b:]

# Review list should contain ONLY photos not present in accepted product list.
a=s.index('  void _restoreGmailCandidateInboxReview() {')
b=s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {',a)
part=s[a:b]
old="""    final seen = <String>{
      ...gmailRejectedImages
          .map((e) => (e['url'] ?? '').toString().trim()),
    };"""
new=r'''    final acceptedIds = <String>{
      for (final row in gmailCandidateInbox)
        if (accepted.contains((row['url'] ?? '').toString().trim()))
          _gmailCandidateIdentity(row),
    };
    final seen = <String>{
      ...gmailRejectedImages.map(_gmailCandidateIdentity),
    };
    gmailRejectedImages.removeWhere((row) {
      final url = (row['url'] ?? '').toString().trim();
      return accepted.contains(url) ||
          acceptedIds.contains(_gmailCandidateIdentity(row));
    });'''
assert part.count(old)==1, 'v55 review list changed'
part=part.replace(old,new,1)
old="""      if (url.isEmpty || accepted.contains(url) ||
          hiddenEmailPhotoUrls.contains(url) ||
          gmailManuallyAcceptedPhotoUrls.contains(url) || !seen.add(url)) {"""
new="""      if (url.isEmpty || accepted.contains(url) ||
          acceptedIds.contains(_gmailCandidateIdentity(raw)) ||
          hiddenEmailPhotoUrls.contains(url) ||
          gmailManuallyAcceptedPhotoUrls.contains(url) ||
          !seen.add(_gmailCandidateIdentity(raw))) {"""
assert part.count(old)==1
part=part.replace(old,new,1)
s=s[:a]+part+s[b:]

# Avoid evaluating the same thumbnail multiple times even if the app's raw
# URL/attachment lists overlap.
a=s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b=s.index('  Future<void> _showRejectedGmailPhotos() async {',a)
part=s[a:b]
needle="    final allImages = _emailPhotoEntries();"
assert part.count(needle)==1
part=part.replace(needle,'''    final uniqueImages = <String, Map<String, dynamic>>{};
    for (final row in _emailPhotoEntries()) {
      uniqueImages.putIfAbsent(_gmailCandidateIdentity(row), () => row);
    }
    final allImages = uniqueImages.values.toList();''',1)
s=s[:a]+part+s[b:]

p.write_text(s)
print('v55: fresh explicit Gmail search, full order email photos, dedupe accepted/rejected; background resume unchanged.')
