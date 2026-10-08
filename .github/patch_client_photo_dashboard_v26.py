from pathlib import Path

p = Path('app/lib/clients.dart')
s = p.read_text()

start = s.find('class _ClientArticlePhotosPage extends StatefulWidget {')
end = s.find('class ClientDetailPage extends StatefulWidget {', start)
if start < 0 or end < 0:
    raise SystemExit('Could not locate client photo dashboard')

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
  String gmailBackendUrl = '', gmailApiKey = '';
  bool loading = true, selecting = false;
  final Set<String> selectedPhotoKeys = <String>{};

  @override
  void initState() {
    super.initState();
    load();
  }

  String _statusKey(Map<String, dynamic> photo) {
    final explicit = '${photo['statusKey'] ?? ''}'.trim();
    if (explicit.isNotEmpty) return explicit;
    if ('${photo['source'] ?? 'gmail'}' == 'manual') {
      return 'manual:${photo['localPath'] ?? photo['url'] ?? ''}';
    }
    return 'gmail:${photo['url'] ?? ''}';
  }

  String _selectionKey(Map<String, dynamic> photo) =>
      '${photo['packageId'] ?? ''}|${_statusKey(photo)}';

  Map<String, dynamic>? _packageFor(String packageId, String tracking) {
    final byId = packages
        .where((e) => '${e['id'] ?? ''}'.trim() == packageId.trim())
        .firstOrNull;
    if (byId != null) return byId;
    final needle = tracking.trim().toLowerCase();
    if (needle.isEmpty) return null;
    return packages
        .where((e) =>
            '${e['tracking'] ?? ''}'.trim().toLowerCase() == needle)
        .firstOrNull;
  }

  bool _isReceived(Map<String, dynamic> photo) {
    final package = _packageFor(
      '${photo['packageId'] ?? ''}',
      '${photo['tracking'] ?? ''}',
    );
    if (package == null) return photo['receivedInCuba'] == true;
    return dynList(package['cubaReceivedPhotoKeys'])
        .map((e) => '$e')
        .contains(_statusKey(photo));
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
      final received = dynList(package['cubaReceivedPhotoKeys'])
          .map((e) => '$e')
          .toSet();

      final offline = <String, String>{};
      final offlineRaw = package['gmailOfflinePhotoPaths'];
      if (offlineRaw is Map) {
        offline.addAll(offlineRaw.map((k, v) => MapEntry('$k', '$v')));
      }

      void addGmail(Map<String, dynamic> image) {
        final url = '${image['url'] ?? ''}'.trim();
        if (url.isEmpty || hidden.contains(url)) return;
        final statusKey = 'gmail:$url';
        if (!seen.add('$packageId|$statusKey')) return;
        out.add({
          ...image,
          'packageId': packageId,
          'tracking': tracking,
          'url': url,
          'source': 'gmail',
          'statusKey': statusKey,
          'receivedInCuba': received.contains(statusKey),
          'localPath': '${image['localPath'] ?? offline[url] ?? ''}'.trim(),
        });
      }

      for (final raw in dynList(package['emailPhotoUrls'])) {
        final url = '$raw'.trim();
        if (url.isNotEmpty) addGmail({'kind': 'remote', 'url': url});
      }
      for (final raw
          in dynList(package['emailAttachmentImages']).whereType<Map>()) {
        addGmail({...Map<String, dynamic>.from(raw), 'kind': 'attachment'});
      }

      // A package whose tracking contains "unknown" can still have useful
      // manually-added article photos even though Gmail cannot identify it.
      if (tracking.toLowerCase().contains('unknown')) {
        for (final rawPath in packagePhotoPaths(package)) {
          final path = rawPath.trim();
          if (path.isEmpty || !File(path).existsSync()) continue;
          final statusKey = 'manual:$path';
          if (!seen.add('$packageId|$statusKey')) continue;
          out.add({
            'packageId': packageId,
            'tracking': tracking,
            'url': 'manual://$path',
            'localPath': path,
            'source': 'manual',
            'kind': 'manual',
            'statusKey': statusKey,
            'receivedInCuba': received.contains(statusKey),
          });
        }
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
    final allPackages = active(result[0] as List<Map<String, dynamic>>)
        .where((e) => '${e['clientId'] ?? ''}' == widget.clientId)
        .toList();
    final photoRows = _collectPhotos(allPackages);

    if (!mounted) return;
    setState(() {
      packages = allPackages;
      photos = photoRows;
      gmailBackendUrl = '${result[1]}'.trim();
      gmailApiKey = '${result[2]}'.trim();
      selectedPhotoKeys.removeWhere(
        (key) => !photoRows.any((p) => _selectionKey(p) == key),
      );
      if (selectedPhotoKeys.isEmpty) selecting = false;
      loading = false;
    });
  }

  Future<void> _openPackage(Map<String, dynamic> package) async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => PackageEditPage(existing: package)),
    );
    await load();
  }

  Future<void> _openPackageForPhoto(Map<String, dynamic> photo) async {
    final package = _packageFor(
      '${photo['packageId'] ?? ''}',
      '${photo['tracking'] ?? ''}',
    );
    if (package != null) await _openPackage(package);
  }

  Future<void> _copyTracking(String tracking) async {
    final value = tracking.trim();
    if (value.isEmpty) return;
    await Clipboard.setData(ClipboardData(text: value));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Tracking copiado.')),
      );
    }
  }

  Future<void> _setReceived(
    Iterable<Map<String, dynamic>> targets,
    bool received,
  ) async {
    final all = await Store.list('packages', forceRefresh: true);
    var changed = false;
    for (final photo in targets) {
      final id = '${photo['packageId'] ?? ''}'.trim();
      final track = '${photo['tracking'] ?? ''}'.trim().toLowerCase();
      var index = all.indexWhere((e) => '${e['id'] ?? ''}'.trim() == id);
      if (index < 0 && track.isNotEmpty) {
        index = all.indexWhere((e) =>
            '${e['tracking'] ?? ''}'.trim().toLowerCase() == track);
      }
      if (index < 0) continue;
      final current = Map<String, dynamic>.from(all[index]);
      final keys = dynList(current['cubaReceivedPhotoKeys'])
          .map((e) => '$e')
          .toSet();
      final key = _statusKey(photo);
      if (received) {
        if (keys.add(key)) changed = true;
      } else {
        if (keys.remove(key)) changed = true;
      }
      all[index] = {...current, 'cubaReceivedPhotoKeys': keys.toList()};
    }
    if (changed) {
      await Store.saveList('packages', all);
      Store.clearListCache('packages');
    }
    if (!mounted) return;
    setState(() {
      selectedPhotoKeys.clear();
      selecting = false;
    });
    await load();
  }

  Future<void> _deletePhotos(List<Map<String, dynamic>> targets) async {
    if (targets.isEmpty) return;
    final ok = await showDialog<bool>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: Text(targets.length == 1
                ? 'Eliminar foto'
                : 'Eliminar ${targets.length} fotos'),
            content: Text(targets.length == 1
                ? '¿Quieres eliminar esta foto?'
                : '¿Quieres eliminar las fotos seleccionadas?'),
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

    final all = await Store.list('packages', forceRefresh: true);
    final filesToDelete = <String>{};

    for (final photo in targets) {
      final id = '${photo['packageId'] ?? ''}'.trim();
      final index = all.indexWhere((e) => '${e['id'] ?? ''}'.trim() == id);
      if (index < 0) continue;
      final current = Map<String, dynamic>.from(all[index]);
      final statusKey = _statusKey(photo);
      final received = dynList(current['cubaReceivedPhotoKeys'])
          .map((e) => '$e')
          .toSet()
        ..remove(statusKey);

      if ('${photo['source'] ?? 'gmail'}' == 'manual') {
        final local = '${photo['localPath'] ?? ''}'.trim();
        final remaining = packagePhotoPaths(current)
            .where((path) => path.trim() != local)
            .toList();
        all[index] = {
          ...current,
          'photoPaths': remaining,
          'photoPath': remaining.isEmpty ? '' : remaining.first,
          'cubaReceivedPhotoKeys': received.toList(),
        };
        if (local.isNotEmpty) filesToDelete.add(local);
        continue;
      }

      final url = '${photo['url'] ?? ''}'.trim();
      if (url.isEmpty) continue;
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
      final rawOffline = current['gmailOfflinePhotoPaths'];
      if (rawOffline is Map) {
        offline.addAll(rawOffline.map((k, v) => MapEntry('$k', '$v')));
      }
      final local = '${offline.remove(url) ?? photo['localPath'] ?? ''}'.trim();
      if (local.isNotEmpty) filesToDelete.add(local);
      final accepted = dynList(current['manuallyAcceptedGmailPhotoUrls'])
          .map((e) => '$e'.trim())
          .where((e) => e.isNotEmpty && e != url)
          .toList();

      all[index] = {
        ...current,
        'emailPhotoUrls': remote,
        'emailAttachmentImages': attachments,
        'hiddenEmailPhotoUrls': hidden.toList(),
        'gmailOfflinePhotoPaths': offline,
        'manuallyAcceptedGmailPhotoUrls': accepted,
        'cubaReceivedPhotoKeys': received.toList(),
      };
    }

    await Store.saveList('packages', all);
    Store.clearListCache('packages');
    for (final path in filesToDelete) {
      try {
        final file = File(path);
        if (await file.exists()) await file.delete();
      } catch (_) {}
    }
    if (!mounted) return;
    setState(() {
      selectedPhotoKeys.clear();
      selecting = false;
    });
    await load();
  }

  List<Map<String, dynamic>> _selectedPhotos() => photos
      .where((p) => selectedPhotoKeys.contains(_selectionKey(p)))
      .toList();

  void _toggleSelection(Map<String, dynamic> photo) {
    final key = _selectionKey(photo);
    setState(() {
      selecting = true;
      if (!selectedPhotoKeys.add(key)) selectedPhotoKeys.remove(key);
      if (selectedPhotoKeys.isEmpty) selecting = false;
    });
  }

  Future<void> _openPhoto(Map<String, dynamic> photo) async {
    await showDialog<void>(
      context: context,
      barrierColor: Colors.black87,
      builder: (dialogContext) {
        final received = _isReceived(photo);
        return Dialog(
          backgroundColor: Colors.black,
          insetPadding: const EdgeInsets.all(10),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 760),
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
                      if (received)
                        Positioned(
                          left: 12,
                          top: 12,
                          child: _receivedSticker(size: 34),
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
                  padding: const EdgeInsets.fromLTRB(12, 9, 6, 9),
                  color: Theme.of(dialogContext)
                      .colorScheme
                      .surfaceContainerHighest,
                  child: Column(
                    children: [
                      InkWell(
                        onTap: () async {
                          Navigator.pop(dialogContext);
                          await _openPackageForPhoto(photo);
                        },
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                'Tracking: ${photo['tracking'] ?? ''}',
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                  fontSize: 16,
                                  decoration: TextDecoration.underline,
                                ),
                              ),
                            ),
                            const Icon(Icons.open_in_new, size: 19),
                          ],
                        ),
                      ),
                      Row(
                        children: [
                          IconButton(
                            tooltip: 'Copiar tracking',
                            onPressed: () =>
                                _copyTracking('${photo['tracking'] ?? ''}'),
                            icon: const Icon(Icons.copy),
                          ),
                          Expanded(
                            child: TextButton.icon(
                              onPressed: () async {
                                Navigator.pop(dialogContext);
                                await _setReceived([photo], !received);
                              },
                              icon: Icon(received
                                  ? Icons.undo
                                  : Icons.check_circle_outline),
                              label: Text(received
                                  ? 'Quitar recibido en Cuba'
                                  : 'Recibida en Cuba'),
                            ),
                          ),
                          IconButton(
                            tooltip: 'Eliminar foto',
                            onPressed: () async {
                              Navigator.pop(dialogContext);
                              await _deletePhotos([photo]);
                            },
                            icon: const Icon(Icons.delete_outline),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _receivedSticker({double size = 25}) => Container(
        width: size,
        height: size,
        decoration: const BoxDecoration(
          color: Colors.green,
          shape: BoxShape.circle,
        ),
        child: Icon(
          Icons.check,
          color: Colors.white,
          size: size * .7,
        ),
      );

  Widget _photoTile(Map<String, dynamic> photo) {
    final selected = selectedPhotoKeys.contains(_selectionKey(photo));
    final received = _isReceived(photo);
    return InkWell(
      onTap: () => selecting ? _toggleSelection(photo) : _openPhoto(photo),
      onLongPress: () => _toggleSelection(photo),
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
            if (selected)
              ColoredBox(
                color: Theme.of(context)
                    .colorScheme
                    .primary
                    .withValues(alpha: .28),
              ),
            if (selected)
              Positioned(
                left: 7,
                top: 7,
                child: CircleAvatar(
                  radius: 13,
                  backgroundColor: Theme.of(context).colorScheme.primary,
                  child: const Icon(Icons.check, color: Colors.white, size: 18),
                ),
              ),
            if (received)
              Positioned(right: 7, top: 7, child: _receivedSticker()),
            Positioned(
              left: 4,
              right: 4,
              bottom: 4,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: .72),
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

  Widget _selectionAction(
    IconData icon,
    String label,
    VoidCallback? onPressed,
  ) =>
      Expanded(
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(12),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 3),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon),
                const SizedBox(height: 3),
                Text(
                  label,
                  maxLines: 2,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 11),
                ),
              ],
            ),
          ),
        ),
      );

  Widget _selectionBar() {
    final selected = _selectedPhotos();
    return Material(
      elevation: 10,
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            _selectionAction(
              Icons.delete_outline,
              'Borrar',
              selected.isEmpty ? null : () => _deletePhotos(selected),
            ),
            _selectionAction(
              Icons.check_circle_outline,
              'Recibida en Cuba',
              selected.isEmpty ? null : () => _setReceived(selected, true),
            ),
            _selectionAction(
              Icons.undo,
              'Quitar recibida',
              selected.isEmpty ? null : () => _setReceived(selected, false),
            ),
          ],
        ),
      ),
    );
  }

  List<Map<String, dynamic>> get _notFoundPackages => packages
      .where(gmailRecordNotFound)
      .where((p) => '${p['tracking'] ?? ''}'.trim().isNotEmpty)
      .toList();

  Widget _notFoundTile(Map<String, dynamic> package) {
    final tracking = '${package['tracking'] ?? ''}'.trim();
    return ListTile(
      leading: const Icon(Icons.search_off_outlined),
      title: Text(
        tracking,
        style: TextStyle(
          decoration: TextDecoration.underline,
          color: Theme.of(context).colorScheme.primary,
          fontWeight: FontWeight.w600,
        ),
      ),
      subtitle: const Text('No se encontró correo en la última búsqueda'),
      trailing: IconButton(
        tooltip: 'Copiar tracking',
        onPressed: () => _copyTracking(tracking),
        icon: const Icon(Icons.copy),
      ),
      onTap: () => _openPackage(package),
    );
  }

  @override
  Widget build(BuildContext context) {
    final notFound = _notFoundPackages;
    return Scaffold(
      appBar: AppBar(
        title: Text(selecting
            ? '${selectedPhotoKeys.length} seleccionada(s)'
            : 'Fotos · ${widget.clientName}'),
        actions: [
          if (photos.isNotEmpty)
            TextButton(
              onPressed: () {
                setState(() {
                  if (selecting) {
                    selecting = false;
                    selectedPhotoKeys.clear();
                  } else {
                    selecting = true;
                  }
                });
              },
              child: Text(selecting ? 'Cancelar' : 'Seleccionar'),
            ),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : CustomScrollView(
              slivers: [
                if (photos.isEmpty)
                  const SliverToBoxAdapter(
                    child: Padding(
                      padding: EdgeInsets.all(24),
                      child: Text(
                        'Este cliente todavía no tiene fotos de artículos.',
                        textAlign: TextAlign.center,
                      ),
                    ),
                  )
                else
                  SliverPadding(
                    padding: const EdgeInsets.all(12),
                    sliver: SliverGrid(
                      delegate: SliverChildBuilderDelegate(
                        (_, i) => _photoTile(photos[i]),
                        childCount: photos.length,
                      ),
                      gridDelegate:
                          const SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: 3,
                        crossAxisSpacing: 8,
                        mainAxisSpacing: 8,
                        childAspectRatio: 1,
                      ),
                    ),
                  ),
                const SliverToBoxAdapter(
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(16, 20, 16, 8),
                    child: Text(
                      'Correos no encontrados',
                      style:
                          TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                    ),
                  ),
                ),
                if (notFound.isEmpty)
                  const SliverToBoxAdapter(
                    child: Padding(
                      padding: EdgeInsets.fromLTRB(16, 4, 16, 28),
                      child: Text(
                        'No hay paquetes con correo pendiente de encontrar.',
                      ),
                    ),
                  )
                else
                  SliverList(
                    delegate: SliverChildBuilderDelegate(
                      (_, i) => _notFoundTile(notFound[i]),
                      childCount: notFound.length,
                    ),
                  ),
                const SliverToBoxAdapter(child: SizedBox(height: 24)),
              ],
            ),
      bottomNavigationBar: selecting ? _selectionBar() : null,
    );
  }
}

'''

s = s[:start] + gallery + s[end:]
p.write_text(s)

print('Client photo dashboard v26 applied: selection, Cuba status, package links/copy, no-email list and unknown manual photos.')
