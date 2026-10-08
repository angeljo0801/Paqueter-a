from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Missing expected block: {label}')
    return text.replace(old, new, 1)


p = Path('app/lib/clients.dart')
s = p.read_text()

# Add a dedicated all-item-photo browser before ClientDetailPage so it can be
# opened from the client dashboard without disturbing the existing sections.
anchor = '''class ClientDetailPage extends StatefulWidget {
'''

gallery = r'''
class _ClientArticlePhotosPage extends StatefulWidget {
  final String clientId;
  final String clientName;
  const _ClientArticlePhotosPage({
    required this.clientId,
    required this.clientName,
  });

  @override
  State<_ClientArticlePhotosPage> createState() =>
      _ClientArticlePhotosPageState();
}

class _ClientArticlePhotosPageState
    extends State<_ClientArticlePhotosPage> {
  List<Map<String, dynamic>> packages = [];
  List<Map<String, dynamic>> photos = [];
  String gmailBackendUrl = '';
  String gmailApiKey = '';
  bool loading = true;

  @override
  void initState() {
    super.initState();
    load();
  }

  List<Map<String, dynamic>> _collectPhotos(
    List<Map<String, dynamic>> packageRows,
  ) {
    final out = <Map<String, dynamic>>[];
    final seen = <String>{};

    for (final package in packageRows) {
      final packageId = '${package['id'] ?? ''}'.trim();
      final tracking = '${package['tracking'] ?? ''}'.trim();
      final hidden = dynList(package['hiddenEmailPhotoUrls'])
          .map((e) => '$e'.trim())
          .where((e) => e.isNotEmpty)
          .toSet();

      final offline = <String, String>{};
      final offlineRaw = package['gmailOfflinePhotoPaths'];
      if (offlineRaw is Map) {
        offline.addAll(
          offlineRaw.map((k, v) => MapEntry('$k', '$v')),
        );
      }

      void addPhoto(Map<String, dynamic> image) {
        final url = '${image['url'] ?? ''}'.trim();
        if (url.isEmpty || hidden.contains(url)) return;
        final dedupe = '$packageId|$url';
        if (!seen.add(dedupe)) return;
        out.add({
          ...image,
          'packageId': packageId,
          'tracking': tracking,
          'url': url,
          'localPath':
              '${image['localPath'] ?? offline[url] ?? ''}'.trim(),
        });
      }

      for (final raw in dynList(package['emailPhotoUrls'])) {
        final url = '$raw'.trim();
        if (url.isEmpty) continue;
        addPhoto({
          'kind': 'remote',
          'url': url,
          'name': '',
        });
      }

      for (final raw in dynList(package['emailAttachmentImages'])
          .whereType<Map>()) {
        addPhoto({
          ...Map<String, dynamic>.from(raw),
          'kind': 'attachment',
        });
      }
    }
    return out;
  }

  Future<void> load() async {
    final result = await Future.wait([
      Store.list('packages', forceRefresh: true),
      WhatsBotPurchaseSyncService.backendUrl(),
      WhatsBotPurchaseSyncService.apiKey(),
    ]);
    final allPackages =
        active(result[0] as List<Map<String, dynamic>>)
            .where((e) => '${e['clientId'] ?? ''}' == widget.clientId)
            .toList();
    final photoRows = _collectPhotos(allPackages);

    if (!mounted) return;
    setState(() {
      packages = allPackages;
      photos = photoRows;
      gmailBackendUrl = '${result[1]}'.trim();
      gmailApiKey = '${result[2]}'.trim();
      loading = false;
    });
  }

  Future<void> _deletePhoto(Map<String, dynamic> photo) async {
    final ok = await showDialog<bool>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: const Text('Eliminar foto'),
            content: Text(
              '¿Quieres eliminar esta foto del paquete '
              '${photo['tracking'] ?? ''}?',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('Cancelar'),
              ),
              FilledButton.icon(
                onPressed: () => Navigator.pop(dialogContext, true),
                icon: const Icon(Icons.delete_outline),
                label: const Text('Eliminar'),
              ),
            ],
          ),
        ) ??
        false;
    if (!ok) return;

    final packageId = '${photo['packageId'] ?? ''}'.trim();
    final url = '${photo['url'] ?? ''}'.trim();
    if (packageId.isEmpty || url.isEmpty) return;

    final all = await Store.list('packages', forceRefresh: true);
    final index =
        all.indexWhere((e) => '${e['id'] ?? ''}'.trim() == packageId);
    if (index < 0) return;

    final current = Map<String, dynamic>.from(all[index]);
    final hidden = dynList(current['hiddenEmailPhotoUrls'])
        .map((e) => '$e'.trim())
        .where((e) => e.isNotEmpty)
        .toSet()
      ..add(url);

    final remote = dynList(current['emailPhotoUrls'])
        .map((e) => '$e'.trim())
        .where((e) => e.isNotEmpty && e != url)
        .toList();

    final attachments = dynList(current['emailAttachmentImages'])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .where((e) => '${e['url'] ?? ''}'.trim() != url)
        .toList();

    final offline = <String, String>{};
    final offlineRaw = current['gmailOfflinePhotoPaths'];
    if (offlineRaw is Map) {
      offline.addAll(
        offlineRaw.map((k, v) => MapEntry('$k', '$v')),
      );
    }
    final localPath = '${offline.remove(url) ?? photo['localPath'] ?? ''}'.trim();

    final manuallyAccepted = dynList(
      current['manuallyAcceptedGmailPhotoUrls'],
    ).map((e) => '$e'.trim()).where((e) => e.isNotEmpty && e != url).toList();

    all[index] = {
      ...current,
      'emailPhotoUrls': remote,
      'emailAttachmentImages': attachments,
      'hiddenEmailPhotoUrls': hidden.toList(),
      'gmailOfflinePhotoPaths': offline,
      'manuallyAcceptedGmailPhotoUrls': manuallyAccepted,
    };
    await Store.saveList('packages', all);
    Store.clearListCache('packages');

    if (localPath.isNotEmpty) {
      try {
        final file = File(localPath);
        if (await file.exists()) await file.delete();
      } catch (_) {}
    }

    await load();
  }

  Future<void> _openPhoto(Map<String, dynamic> photo) async {
    var removed = false;
    await showDialog<void>(
      context: context,
      barrierColor: Colors.black87,
      builder: (dialogContext) => Dialog(
        backgroundColor: Colors.black,
        insetPadding: const EdgeInsets.all(10),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 720),
          child: Column(
            children: [
              Expanded(
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: InteractiveViewer(
                        minScale: 0.7,
                        maxScale: 6,
                        child: Center(
                          child: gmailSmartPhotoImage(
                            gmailBackendUrl,
                            gmailApiKey,
                            photo,
                            fit: BoxFit.contain,
                          ),
                        ),
                      ),
                    ),
                    Positioned(
                      right: 8,
                      top: 8,
                      child: IconButton.filledTonal(
                        tooltip: 'Cerrar',
                        onPressed: () => Navigator.pop(dialogContext),
                        icon: const Icon(Icons.close),
                      ),
                    ),
                  ],
                ),
              ),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.fromLTRB(16, 12, 10, 12),
                color: Theme.of(dialogContext).colorScheme.surfaceContainerHighest,
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        'Tracking: ${photo['tracking'] ?? ''}',
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 16,
                        ),
                      ),
                    ),
                    IconButton(
                      tooltip: 'Eliminar foto',
                      onPressed: () async {
                        Navigator.pop(dialogContext);
                        await _deletePhoto(photo);
                        removed = true;
                      },
                      icon: const Icon(Icons.delete_outline),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
    if (removed && mounted) setState(() {});
  }

  Widget _photoTile(Map<String, dynamic> photo) {
    return InkWell(
      onTap: () => _openPhoto(photo),
      borderRadius: BorderRadius.circular(10),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(10),
        child: Stack(
          fit: StackFit.expand,
          children: [
            ColoredBox(
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              child: gmailSmartPhotoImage(
                gmailBackendUrl,
                gmailApiKey,
                photo,
                fit: BoxFit.cover,
              ),
            ),
            Positioned(
              left: 4,
              right: 4,
              bottom: 4,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.72),
                  borderRadius: BorderRadius.circular(7),
                ),
                child: Text(
                  '${photo['tracking'] ?? ''}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Fotos · ${widget.clientName}'),
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : photos.isEmpty
              ? const Center(
                  child: Padding(
                    padding: EdgeInsets.all(24),
                    child: Text(
                      'Este cliente todavía no tiene fotos de artículos encontradas por Gmail.',
                      textAlign: TextAlign.center,
                    ),
                  ),
                )
              : GridView.builder(
                  padding: const EdgeInsets.all(12),
                  gridDelegate:
                      const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 3,
                    crossAxisSpacing: 8,
                    mainAxisSpacing: 8,
                    childAspectRatio: 1,
                  ),
                  itemCount: photos.length,
                  itemBuilder: (_, index) => _photoTile(photos[index]),
                ),
    );
  }
}

'''

if 'class _ClientArticlePhotosPage extends StatefulWidget' not in s:
    s = replace_once(
        s,
        anchor,
        gallery + anchor,
        'client all-article-photo page',
    )

# Put the requested button in the client summary, before the next section.
summary_anchor = r'''          const SizedBox(height: 10),
          _sectionCard(
            context,
            'Destinatarios en Cuba',
'''
summary_new = r'''          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () async {
                await Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => _ClientArticlePhotosPage(
                      clientId: widget.clientId,
                      clientName: '${client!['name'] ?? 'Cliente'}',
                    ),
                  ),
                );
                await load();
              },
              icon: const Icon(Icons.photo_library_outlined),
              label: const Text('Ver fotos de todos los artículos'),
            ),
          ),
          const SizedBox(height: 10),
          _sectionCard(
            context,
            'Destinatarios en Cuba',
'''
s = replace_once(
    s,
    summary_anchor,
    summary_new,
    'client all-photos button',
)

p.write_text(s)
print('Client all-article Gmail photo grid + zoom/tracking/delete applied.')
