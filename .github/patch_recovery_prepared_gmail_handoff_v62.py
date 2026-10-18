from pathlib import Path

# v62: The server returned prepared Gmail photos, but the editor discarded
# thumbnailUrl/originalUrl when mapping them to a list of URL strings.
# Temu original CDN links can fail on Android even if Railway downloaded them.
# Keep cached thumbnails with each image submitted for OCR.
p=Path('app/lib/packages.dart')
s=p.read_text()

# v55 accidentally gave all bare remote URLs the SAME url: identity.
old=r'''    return 'url:';
  }

'''
new=r'''    final raw = (image['url'] ?? '').toString().trim();
    return 'url:$raw';
  }

'''
assert s.count(old)==1, 'v62 candidate identity anchor changed'
s=s.replace(old,new,1)

a=s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b=s.index('  Future<void> _showRejectedGmailPhotos() async {',a)
part=s[a:b]
old=r'''    final uniqueImages = <String, Map<String, dynamic>>{};
    for (final row in _emailPhotoEntries()) {
      uniqueImages.putIfAbsent(_gmailCandidateIdentity(row), () => row);
    }
    final allImages = uniqueImages.values.toList();'''
new=r'''    // Prefer the server-prepared thumbnail and original provenance.
    // The old emailPhotoEntries() loses thumbnailUrl, forcing direct
    // downloads from Temu CDNs which can reject the phone's request.
    final preparedByUrl = <String, Map<String, dynamic>>{};
    for (final candidate in gmailCandidateInbox) {
      final url = (candidate['url'] ?? '').toString().trim();
      if (url.isEmpty || hiddenEmailPhotoUrls.contains(url)) continue;
      final previous = preparedByUrl[url];
      if (previous == null ||
          (previous['thumbnailUrl'] ?? '').toString().isEmpty) {
        preparedByUrl[url] = candidate;
      }
    }
    final uniqueImages = <String, Map<String, dynamic>>{};
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
assert part.count(old)==1, 'v62 smart-filter raw source changed'
part=part.replace(old,new,1)
s=s[:a]+part+s[b:]
p.write_text(s)
assert "return 'url:$raw';" in s
assert 'final preparedByUrl = <String, Map<String, dynamic>>{};' in s
assert '...prepared' in s
print('v62: full candidate identity restored; Railway-prepared images reach Temu OCR.')
