from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Missing expected block: {label}')
    return text.replace(old, new, 1)


packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()

# Keep the per-photo Cuba-received state visible inside PackageEditPage.
state_anchor = "  bool loaded = false, syncing = false, gmailLoading = false;\n"
if "Set<String> cubaReceivedPhotoKeys" not in ps:
    ps = replace_once(
        ps,
        state_anchor,
        state_anchor + "  final Set<String> cubaReceivedPhotoKeys = <String>{};\n",
        'package received-photo state',
    )

init_anchor = "    hiddenEmailPhotoUrls.addAll(dynList(widget.existing?['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n"
if "widget.existing?['cubaReceivedPhotoKeys']" not in ps:
    ps = replace_once(
        ps,
        init_anchor,
        init_anchor
        + "    cubaReceivedPhotoKeys.addAll(dynList(widget.existing?['cubaReceivedPhotoKeys']).map((e) => '$e').where((e) => e.isNotEmpty));\n",
        'load Cuba received-photo keys',
    )

helper_anchor = "  Future<void> openPackagePhoto(String path) async {\n"
helpers = r'''  bool _manualPhotoReceivedInCuba(String path) =>
      cubaReceivedPhotoKeys.contains('manual:$path');

  bool _gmailPhotoReceivedInCuba(Map<String, dynamic> image) {
    final url = ''.trim();
    return url.isNotEmpty && cubaReceivedPhotoKeys.contains('gmail:$url');
  }

  Widget _receivedInCubaSticker({double size = 25}) => Tooltip(
        message: 'Recibida en Cuba',
        child: Container(
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
        ),
      );

'''
if "_manualPhotoReceivedInCuba" not in ps:
    ps = replace_once(
        ps,
        helper_anchor,
        helpers + helper_anchor,
        'package Cuba received helpers',
    )

# Manual-photo zoom also carries the same status badge.
old_open_manual = r'''  Future<void> openPackagePhoto(String path) async {
    if (!File(path).existsSync()) return;
    await showDialog<void>(
      context: context,
      builder: (_) => Dialog(
        insetPadding: const EdgeInsets.all(12),
        child: Stack(
          children: [
            InteractiveViewer(
              minScale: 0.7,
              maxScale: 5,
              child: Image.file(File(path), fit: BoxFit.contain),
            ),
            Positioned(
              right: 4,
              top: 4,
              child: IconButton.filledTonal(
                onPressed: () => Navigator.pop(context),
                icon: const Icon(Icons.close),
              ),
            ),
          ],
        ),
      ),
    );
  }
'''
new_open_manual = r'''  Future<void> openPackagePhoto(String path) async {
    if (!File(path).existsSync()) return;
    final receivedInCuba = _manualPhotoReceivedInCuba(path);
    await showDialog<void>(
      context: context,
      builder: (_) => Dialog(
        insetPadding: const EdgeInsets.all(12),
        child: Stack(
          children: [
            InteractiveViewer(
              minScale: 0.7,
              maxScale: 5,
              child: Image.file(File(path), fit: BoxFit.contain),
            ),
            if (receivedInCuba)
              Positioned(
                left: 8,
                top: 8,
                child: _receivedInCubaSticker(size: 34),
              ),
            Positioned(
              right: 4,
              top: 4,
              child: IconButton.filledTonal(
                onPressed: () => Navigator.pop(context),
                icon: const Icon(Icons.close),
              ),
            ),
          ],
        ),
      ),
    );
  }
'''
ps = replace_once(
    ps,
    old_open_manual,
    new_open_manual,
    'manual package photo zoom badge',
)

# Gmail full-screen gallery receives the status bit so the large image shows it.
old_gallery_images = "    final images = _emailPhotoEntries();\n"
new_gallery_images = r'''    final images = _emailPhotoEntries()
        .map((e) => <String, dynamic>{
              ...e,
              'receivedInCuba': _gmailPhotoReceivedInCuba(e),
            })
        .toList();
'''
ps = replace_once(
    ps,
    old_gallery_images,
    new_gallery_images,
    'Gmail package gallery received marker',
)

# Manual thumbnails.
manual_item = r'''              itemBuilder: (_, i) {
                final path = photoPaths[i];
                return Stack(
'''
manual_item_new = r'''              itemBuilder: (_, i) {
                final path = photoPaths[i];
                final receivedInCuba = _manualPhotoReceivedInCuba(path);
                return Stack(
'''
ps = replace_once(ps, manual_item, manual_item_new, 'manual thumbnail received bool')

manual_close = r'''                    Positioned(
                      right: 2,
                      top: 2,
                      child: IconButton.filledTonal(
'''
manual_close_new = r'''                    if (receivedInCuba)
                      Positioned(
                        left: 4,
                        top: 4,
                        child: _receivedInCubaSticker(),
                      ),
                    Positioned(
                      right: 2,
                      top: 2,
                      child: IconButton.filledTonal(
'''
ps = replace_once(ps, manual_close, manual_close_new, 'manual thumbnail received sticker')

# Gmail thumbnails. At this point there is only one "final image = emailImages[i]"
# in the package editor grid.
email_item = r'''                    itemBuilder: (_, i) {
                      final image = emailImages[i];
                      return Stack(
'''
email_item_new = r'''                    itemBuilder: (_, i) {
                      final image = emailImages[i];
                      final receivedInCuba = _gmailPhotoReceivedInCuba(image);
                      return Stack(
'''
ps = replace_once(ps, email_item, email_item_new, 'Gmail thumbnail received bool')

# Insert before the Gmail delete/close control. This is the second top-right
# control block after the manual-photo one, so target the exact filled variant.
email_close = r'''                          Positioned(
                            right: 2,
                            top: 2,
                            child: IconButton.filled(
'''
email_close_new = r'''                          if (receivedInCuba)
                            Positioned(
                              left: 5,
                              top: 5,
                              child: _receivedInCubaSticker(),
                            ),
                          Positioned(
                            right: 2,
                            top: 2,
                            child: IconButton.filled(
'''
ps = replace_once(ps, email_close, email_close_new, 'Gmail thumbnail received sticker')

packages_path.write_text(ps)


# Shared Gmail zoom viewer: if the caller passes receivedInCuba=true, show the
# same green check and text while the full-size image is open.
helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()

delete_anchor = r'''              Positioned(
                left: 10,
                top: 10,
                child: IconButton.filledTonal(
                  tooltip: 'Borrar esta foto',
'''
status_overlay = r'''              if (working.isNotEmpty &&
                  working[currentIndex]['receivedInCuba'] == true)
                Positioned(
                  left: 72,
                  right: 72,
                  top: 12,
                  child: Center(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: Colors.green.withValues(alpha: .92),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: const Padding(
                        padding:
                            EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.check, color: Colors.white, size: 18),
                            SizedBox(width: 5),
                            Text(
                              'Recibida en Cuba',
                              style: TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
'''
if "working[currentIndex]['receivedInCuba'] == true" not in hs:
    hs = replace_once(
        hs,
        delete_anchor,
        status_overlay + delete_anchor,
        'Gmail zoom received status overlay',
    )

helper_path.write_text(hs)
print('Package v27 applied: Recibida en Cuba is visible on package thumbnails and zoom views.')
