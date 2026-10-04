from pathlib import Path
import re


def replace_regex(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return updated


# Add one shared full-screen Gmail gallery. It keeps a private working list while
# the dialog is open, so deleting a photo immediately reveals the next/previous
# image without forcing the user back to the thumbnail grid.
helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()

if 'Future<Set<String>> openGmailPhotoGallery(' not in hs:
    gallery = r'''
Future<Set<String>> openGmailPhotoGallery(
  BuildContext context, {
  required String baseUrl,
  required String apiKey,
  required List<Map<String, dynamic>> images,
  int initialIndex = 0,
}) async {
  if (images.isEmpty) return <String>{};
  final working = images.map((e) => Map<String, dynamic>.from(e)).toList();
  final removed = <String>{};
  var currentIndex = initialIndex.clamp(0, working.length - 1);
  final controller = PageController(initialPage: currentIndex);

  await showDialog<void>(
    context: context,
    barrierColor: Colors.black,
    builder: (_) => StatefulBuilder(
      builder: (dialogContext, setDialog) => Dialog.fullscreen(
        backgroundColor: Colors.black,
        child: SafeArea(
          child: Stack(
            children: [
              Positioned.fill(
                child: PageView.builder(
                  controller: controller,
                  scrollDirection: Axis.horizontal,
                  itemCount: working.length,
                  onPageChanged: (index) => setDialog(() => currentIndex = index),
                  itemBuilder: (_, index) {
                    final image = working[index];
                    final url = gmailPhotoUrl(baseUrl, image);
                    return InteractiveViewer(
                      minScale: 0.8,
                      maxScale: 6,
                      panEnabled: true,
                      scaleEnabled: true,
                      child: Center(
                        child: Image.network(
                          url,
                          headers: gmailPhotoHeaders(baseUrl, apiKey, image),
                          fit: BoxFit.contain,
                          loadingBuilder: (_, child, progress) => progress == null
                              ? child
                              : const Center(child: CircularProgressIndicator()),
                          errorBuilder: (_, __, ___) => const Center(
                            child: Icon(Icons.broken_image_outlined, size: 64),
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
              Positioned(
                left: 10,
                top: 10,
                child: IconButton.filledTonal(
                  tooltip: 'Borrar esta foto',
                  icon: const Icon(Icons.delete_outline),
                  onPressed: working.isEmpty
                      ? null
                      : () async {
                          final image = working[currentIndex];
                          final raw = '${image['url'] ?? ''}'.trim();
                          if (raw.isEmpty) return;
                          final ok = await showDialog<bool>(
                                context: dialogContext,
                                builder: (confirmContext) => AlertDialog(
                                  title: const Text('Borrar foto'),
                                  content: const Text(
                                    '¿Quieres quitar esta foto de este registro? El correo original no se borrará.',
                                  ),
                                  actions: [
                                    TextButton(
                                      onPressed: () => Navigator.pop(confirmContext, false),
                                      child: const Text('Cancelar'),
                                    ),
                                    FilledButton.icon(
                                      onPressed: () => Navigator.pop(confirmContext, true),
                                      icon: const Icon(Icons.delete_outline),
                                      label: const Text('Borrar'),
                                    ),
                                  ],
                                ),
                              ) ??
                              false;
                          if (!ok) return;

                          removed.add(raw);
                          if (working.length == 1) {
                            Navigator.pop(dialogContext);
                            return;
                          }

                          setDialog(() {
                            working.removeAt(currentIndex);
                            if (currentIndex >= working.length) {
                              currentIndex = working.length - 1;
                            }
                          });
                          WidgetsBinding.instance.addPostFrameCallback((_) {
                            if (controller.hasClients) {
                              controller.jumpToPage(currentIndex);
                            }
                          });
                        },
                ),
              ),
              Positioned(
                right: 10,
                top: 10,
                child: IconButton.filled(
                  tooltip: 'Cerrar',
                  onPressed: () => Navigator.pop(dialogContext),
                  icon: const Icon(Icons.close),
                ),
              ),
              Positioned(
                left: 16,
                right: 16,
                bottom: 14,
                child: Center(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.68),
                      borderRadius: BorderRadius.circular(24),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                      child: Text(
                        '${currentIndex + 1} / ${working.length} · Desliza horizontalmente',
                        style: const TextStyle(color: Colors.white),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );

  controller.dispose();
  return removed;
}

'''
    marker = 'Future<Set<String>?> selectGmailPhotosToRemove(\n'
    if marker not in hs:
        raise SystemExit('No se encontró bloque esperado: Gmail photo selector marker')
    hs = hs.replace(marker, gallery + marker, 1)
    helper_path.write_text(hs)


# Package editor: tapping any Gmail thumbnail now opens the whole gallery at the
# tapped position. Deletions made in the large viewer are persisted immediately
# when the viewer closes (or when the final image is removed).
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()

package_gallery_method = r'''  Future<void> openEmailPhoto(Map<String, dynamic> image) async {
    final images = _emailPhotoEntries();
    if (images.isEmpty) return;
    final tapped = '${image['url'] ?? ''}'.trim();
    var initialIndex = images.indexWhere((e) => '${e['url'] ?? ''}'.trim() == tapped);
    if (initialIndex < 0) initialIndex = 0;
    final removed = await openGmailPhotoGallery(
      context,
      baseUrl: gmailBackendUrl,
      apiKey: gmailApiKey,
      images: images,
      initialIndex: initialIndex,
    );
    if (!mounted || removed.isEmpty) return;
    setState(() {
      hiddenEmailPhotoUrls.addAll(removed);
      emailPhotoUrls.removeWhere((e) => removed.contains(e.trim()));
      emailAttachmentImages.removeWhere(
        (e) => removed.contains('${e['url'] ?? ''}'.trim()),
      );
    });
  }

'''

if 'openGmailPhotoGallery(\n      context,\n      baseUrl: gmailBackendUrl' not in ps:
    ps = replace_regex(
        ps,
        r"  Future<void> openEmailPhoto\(Map<String, dynamic> image\) async \{.*?\n  \}\n\n  Future<void> removeEmailPhoto",
        package_gallery_method + '  Future<void> removeEmailPhoto',
        'package single-photo preview',
    )
    packages_path.write_text(ps)


# Purchase editor: same gallery behavior for Gmail photos attached to purchases.
purchases_path = Path('app/lib/purchases.dart')
us = purchases_path.read_text()

purchase_old_pattern = (
    r"  Future<void> _openPurchaseEmailPhoto\(Map<String, dynamic> image\) =>\n"
    r"      openGmailPhotoPreview\(\n"
    r"        context,\n"
    r"        baseUrl: gmailPurchaseBackendUrl,\n"
    r"        apiKey: gmailPurchaseApiKey,\n"
    r"        image: image,\n"
    r"      \);\n"
)

purchase_gallery_method = r'''  Future<void> _openPurchaseEmailPhoto(Map<String, dynamic> image) async {
    final images = _purchaseEmailPhotoEntries();
    if (images.isEmpty) return;
    final tapped = '${image['url'] ?? ''}'.trim();
    var initialIndex = images.indexWhere((e) => '${e['url'] ?? ''}'.trim() == tapped);
    if (initialIndex < 0) initialIndex = 0;
    final removed = await openGmailPhotoGallery(
      context,
      baseUrl: gmailPurchaseBackendUrl,
      apiKey: gmailPurchaseApiKey,
      images: images,
      initialIndex: initialIndex,
    );
    if (!mounted || removed.isEmpty) return;
    setState(() {
      hiddenGmailPurchasePhotoUrls.addAll(removed);
      gmailPurchasePhotoUrls.removeWhere((e) => removed.contains(e.trim()));
      gmailPurchaseAttachmentImages.removeWhere(
        (e) => removed.contains('${e['url'] ?? ''}'.trim()),
      );
    });
  }
'''

if 'baseUrl: gmailPurchaseBackendUrl,\n      apiKey: gmailPurchaseApiKey,\n      images: images,' not in us:
    us = replace_regex(
        us,
        purchase_old_pattern,
        purchase_gallery_method,
        'purchase single-photo preview',
    )
    purchases_path.write_text(us)

print('Swipeable Gmail photo gallery with in-view deletion applied.')
