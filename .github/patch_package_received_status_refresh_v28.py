from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Missing expected block: {label}')
    return text.replace(old, new, 1)


p = Path('app/lib/packages.dart')
s = p.read_text()

init_anchor = r'''    hiddenEmailPhotoUrls.addAll(dynList(widget.existing?['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));
    cubaReceivedPhotoKeys.addAll(dynList(widget.existing?['cubaReceivedPhotoKeys']).map((e) => '$e').where((e) => e.isNotEmpty));
    gmailBackendUrl = await WhatsBotPurchaseSyncService.backendUrl();
'''
init_new = r'''    hiddenEmailPhotoUrls.addAll(dynList(widget.existing?['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));
    cubaReceivedPhotoKeys.addAll(dynList(widget.existing?['cubaReceivedPhotoKeys']).map((e) => '$e').where((e) => e.isNotEmpty));

    // The package list can be stale after changing "Recibida en Cuba" from the
    // client photo dashboard. Always read the newest persisted state.
    if (widget.existing != null) {
      final persistedPackages =
          await Store.list('packages', forceRefresh: true);
      final existingId = '${widget.existing?['id'] ?? ''}'.trim();
      final existingTracking =
          '${widget.existing?['tracking'] ?? ''}'.trim().toLowerCase();
      final latest = persistedPackages.where((e) {
        final idMatches =
            existingId.isNotEmpty && '${e['id'] ?? ''}'.trim() == existingId;
        final trackingMatches = existingTracking.isNotEmpty &&
            '${e['tracking'] ?? ''}'.trim().toLowerCase() == existingTracking;
        return idMatches || trackingMatches;
      }).firstOrNull;
      if (latest != null) {
        cubaReceivedPhotoKeys
          ..clear()
          ..addAll(
            dynList(latest['cubaReceivedPhotoKeys'])
                .map((e) => '$e')
                .where((e) => e.isNotEmpty),
          );
      }
    }

    gmailBackendUrl = await WhatsBotPurchaseSyncService.backendUrl();
'''
s = replace_once(
    s,
    init_anchor,
    init_new,
    'refresh Cuba received status from persisted package',
)

class_old = r'''class _PackageEditPageState extends State<PackageEditPage> {
'''
class_new = r'''class _PackageEditPageState extends State<PackageEditPage>
    with WidgetsBindingObserver {
'''
s = replace_once(s, class_old, class_new, 'package lifecycle observer')

initstate_old = r'''  @override
  void initState() { super.initState(); init(); }
'''
initstate_new = r'''  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    init();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    tracking.dispose();
    weightUs.dispose();
    weightCu.dispose();
    billWeight.dispose();
    notes.dispose();
    gmailStore.dispose();
    gmailOrder.dispose();
    gmailStatus.dispose();
    gmailEta.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _refreshCubaReceivedPhotoStatus();
    }
  }

  Future<void> _refreshCubaReceivedPhotoStatus() async {
    if (widget.existing == null) return;
    final all = await Store.list('packages', forceRefresh: true);
    final id = '${widget.existing?['id'] ?? ''}'.trim();
    final track = '${widget.existing?['tracking'] ?? ''}'.trim().toLowerCase();
    final latest = all.where((e) {
      if (id.isNotEmpty && '${e['id'] ?? ''}'.trim() == id) return true;
      return track.isNotEmpty &&
          '${e['tracking'] ?? ''}'.trim().toLowerCase() == track;
    }).firstOrNull;
    if (latest == null || !mounted) return;
    final keys = dynList(latest['cubaReceivedPhotoKeys'])
        .map((e) => '$e')
        .where((e) => e.isNotEmpty)
        .toSet();
    if (setEquals(keys, cubaReceivedPhotoKeys)) return;
    setState(() {
      cubaReceivedPhotoKeys
        ..clear()
        ..addAll(keys);
    });
  }
'''
s = replace_once(s, initstate_old, initstate_new, 'refresh package status on resume')

save_anchor = r'''      'hiddenEmailPhotoUrls': hiddenEmailPhotoUrls.toList(),
      'photoPaths': photoPaths,
'''
save_new = r'''      'hiddenEmailPhotoUrls': hiddenEmailPhotoUrls.toList(),
      'cubaReceivedPhotoKeys': cubaReceivedPhotoKeys.toList(),
      'photoPaths': photoPaths,
'''
s = replace_once(s, save_anchor, save_new, 'save Cuba received keys')

p.write_text(s)
print('Package v28 applied: always refresh/persist Cuba received photo status.')
