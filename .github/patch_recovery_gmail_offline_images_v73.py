from pathlib import Path

# v73: Gmail photos accepted by OCR are usually cached, but fallback previews
# and raw URL-based thumbnails rely on Image.network. A reboot/offline mode
# then shows a broken image. Persist previews in Documents; do not change
# classification, metadata merging or manual photo recovery.
p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()
start = s.index('Widget gmailSmartPhotoImage(')
end = s.index('\n}\n', start) + len('\n}')
original = s[start:end]
assert 'return Image.network(' in original and "image['localPath']" in original, 'v73: renderer changed'

new = r'''
// Cached image files are stored in Documents (not the temporary cache).
// The URL hash also recovers them after a package is reopened, even when
// legacy emailPhotoUrls contain only URLs without localPath metadata.
final Map<String, Future<File?>> _gmailVisiblePhotoDownloads =
    <String, Future<File?>>{};

Future<File?> gmailEnsurePhotoAvailableOffline(
  String baseUrl, String apiKey, Map<String, dynamic> image,
) async {
  final local = (image['localPath'] ?? '').toString().trim();
  if (local.isNotEmpty) {
    try {
      final f = File(local);
      if (await f.exists() && await f.length() > 0) return f;
    } catch (_) {}
  }
  String url;
  try {
    url = gmailPhotoUrl(baseUrl, image).trim();
    final parsed = Uri.tryParse(url);
    if (parsed == null || (parsed.scheme != 'http' && parsed.scheme != 'https')) {
      return null;
    }
  } catch (_) { return null; }

  // Only one download, even when gallery + thumbnail + prefetch overlap.
  final pending = _gmailVisiblePhotoDownloads[url];
  if (pending != null) return pending;
  final next = _gmailFetchAndStoreVisiblePhoto(url, baseUrl, apiKey, image);
  _gmailVisiblePhotoDownloads[url] = next;
  try {
    return await next;
  } finally {
    if (identical(_gmailVisiblePhotoDownloads[url], next)) {
      _gmailVisiblePhotoDownloads.remove(url);
    }
  }
}

Future<File?> _gmailFetchAndStoreVisiblePhoto(
  String url, String baseUrl, String apiKey, Map<String, dynamic> image,
) async {
  try {
    final root = await getApplicationDocumentsDirectory();
    final dir = Directory(root.path + '/gmail_visible_offline_v1');
    if (!await dir.exists()) await dir.create(recursive: true);
    final digest = _gmailPhotoDigest(utf8.encode(url));
    final target = File(dir.path + '/' + digest + '.img');
    if (await target.exists()) {
      if (await target.length() > 0) return target;
      await target.delete();
    }
    final response = await http.get(Uri.parse(url),
      headers: gmailPhotoHeaders(baseUrl, apiKey, image) ??
          const <String, String>{},
    ).timeout(const Duration(seconds: 12));
    if (response.statusCode < 200 || response.statusCode >= 300) return null;
    final bytes = response.bodyBytes;
    if (bytes.length < 12 || bytes.length > 10 * 1024 * 1024) return null;
    final mime = (response.headers['content-type'] ?? '').toLowerCase();
    if (mime.contains('text/html') || mime.contains('application/json')) {
      return null;
    }
    final jpg = bytes[0] == 255 && bytes[1] == 216;
    final png = bytes[0] == 137 && bytes[1] == 80 &&
        bytes[2] == 78 && bytes[3] == 71;
    final gif = bytes[0] == 71 && bytes[1] == 73 && bytes[2] == 70;
    final webp = bytes[0] == 82 && bytes[1] == 73 &&
        bytes[2] == 70 && bytes[3] == 70 &&
        bytes[8] == 87 && bytes[9] == 69 &&
        bytes[10] == 66 && bytes[11] == 80;
    if (!jpg && !png && !gif && !webp &&
        !mime.startsWith('image/')) return null;
    final part = File(target.path + '.part');
    try {
      await part.writeAsBytes(bytes, flush: true);
      if (await target.exists()) {
        await part.delete();
      } else {
        await part.rename(target.path);
      }
    } catch (_) {
      if (await part.exists()) await part.delete();
      return await target.exists() ? target : null;
    }
    return target;
  } catch (_) {
    // Offline/expired permissions: leave remote reference intact for retry.
    return null;
  }
}

// Nonblocking: accepted fallback candidates get a local copy even if they
// haven't yet been scrolled into view. Do not preload rejected Gmail assets.
Future<void> gmailWarmAcceptedPhotosForOffline({
  required String baseUrl,
  required String apiKey,
  required List<Map<String, dynamic>> images,
}) async {
  for (var i = 0; i < images.length; i += 3) {
    await Future.wait(images.skip(i).take(3).map((image) async {
      await gmailEnsurePhotoAvailableOffline(baseUrl, apiKey, image);
    }));
  }
}

class _GmailOfflinePhotoImage extends StatefulWidget {
  const _GmailOfflinePhotoImage({
    required this.baseUrl, required this.apiKey,
    required this.image, required this.fit,
  });
  final String baseUrl;
  final String apiKey;
  final Map<String, dynamic> image;
  final BoxFit fit;

  @override
  State<_GmailOfflinePhotoImage> createState() =>
      _GmailOfflinePhotoImageState();
}

class _GmailOfflinePhotoImageState extends State<_GmailOfflinePhotoImage> {
  late Future<File?> file;

  void updateFuture() {
    file = gmailEnsurePhotoAvailableOffline(
      widget.baseUrl, widget.apiKey, widget.image);
  }

  @override
  void initState() { super.initState(); updateFuture(); }

  @override
  void didUpdateWidget(covariant _GmailOfflinePhotoImage old) {
    super.didUpdateWidget(old);
    if (old.baseUrl != widget.baseUrl ||
        old.apiKey != widget.apiKey ||
        (old.image['url'] ?? '') != (widget.image['url'] ?? '') ||
        (old.image['localPath'] ?? '') != (widget.image['localPath'] ?? '') ||
        (old.image['thumbnailUrl'] ?? '') !=
            (widget.image['thumbnailUrl'] ?? '')) {
      updateFuture();
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<File?>(
    future: file,
    builder: (context, snap) {
      final local = snap.data;
      if (local != null) {
        return Image.file(local, fit: widget.fit,
          errorBuilder: (_, __, ___) => const Center(
            child: Icon(Icons.broken_image_outlined),
          ),
        );
      }
      if (snap.connectionState != ConnectionState.done) {
        return const Center(child: CircularProgressIndicator());
      }
      return const Center(child: Icon(Icons.broken_image_outlined));
    },
  );
}

Widget gmailSmartPhotoImage(
  String baseUrl, String apiKey, Map<String, dynamic> image, {
  BoxFit fit = BoxFit.cover,
}) {
  final local = (image['localPath'] ?? '').toString().trim();
  if (local.isNotEmpty && File(local).existsSync()) {
    return Image.file(File(local), fit: fit,
      errorBuilder: (_, __, ___) =>
          const Center(child: Icon(Icons.broken_image_outlined)),
    );
  }
  return _GmailOfflinePhotoImage(
    baseUrl: baseUrl, apiKey: apiKey, image: image, fit: fit,
  );
}'''
s = s[:start] + new + s[end:]
p.write_text(s)

# The accepted list may include verified Gmail candidates that passed the
# fallback even though the classifier never saved their image bytes.
p = Path('app/lib/packages.dart')
s = p.read_text()
a = s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b = s.index('  Future<void> _showRejectedGmailPhotos() async {', a)
section = s[a:b]
marker = "    final offline = result['offlinePaths'];"
assert section.count(marker) == 1, 'v73: package filtered photo finalization moved'
section = section.replace(marker, r'''    unawaited(gmailWarmAcceptedPhotosForOffline(
      baseUrl: gmailBackendUrl,
      apiKey: gmailApiKey,
      images: accepted,
    ));
''' + marker, 1)
s = s[:a] + section + s[b:]
p.write_text(s)

p = Path('app/lib/purchases.dart')
s = p.read_text()
a = s.index('  Future<void> _smartFilterAndCachePurchaseGmailPhotos() async {')
b = s.index('  Future<void> _showRejectedPurchaseGmailPhotos() async {', a)
section = s[a:b]
marker = "    final offline = result['offlinePaths'];"
assert section.count(marker) == 1, 'v73: purchase filtered photo finalization moved'
section = section.replace(marker, r'''    unawaited(gmailWarmAcceptedPhotosForOffline(
      baseUrl: gmailPurchaseBackendUrl,
      apiKey: gmailPurchaseApiKey,
      images: accepted,
    ));
''' + marker, 1)
s = s[:a] + section + s[b:]
p.write_text(s)
print('v73: Gmail previews, fullscreen photos, and recovered products are persistently cached for offline display.')
