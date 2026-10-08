from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Missing expected block: {label}')
    return text.replace(old, new, 1)


p = Path('app/lib/packages.dart')
s = p.read_text()

# Always refresh the persisted Cuba-received photo keys when the package opens.
# The client photo dashboard may have updated these keys after the package list
# screen was built, so widget.existing can legitimately be stale.
init_anchor = """    hiddenEmailPhotoUrls.addAll(dynList(widget.existing?['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));
    cubaReceivedPhotoKeys.addAll(dynList(widget.existing?['cubaReceivedPhotoKeys']).map((e) => '$e').where((e) => e.isNotEmpty));
"""
init_new = init_anchor + """
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
"""
s = replace_once(
    s,
    init_anchor,
    init_new,
    'refresh Cuba received status from persisted package',
)

# PackageEditPage already observes app lifecycle for Gmail recovery. Extend that
# existing resume hook instead of adding a second observer/mixin.
lifecycle_old = """  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      Future<void>.delayed(
        const Duration(milliseconds: 250),
        _recoverFinishedGmailSearch,
      );
    }
  }

"""
lifecycle_new = """  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _refreshCubaReceivedPhotoStatus();
      Future<void>.delayed(
        const Duration(milliseconds: 250),
        _recoverFinishedGmailSearch,
      );
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

"""
s = replace_once(
    s,
    lifecycle_old,
    lifecycle_new,
    'extend existing lifecycle refresh hook',
)

save_anchor = """      'hiddenEmailPhotoUrls': hiddenEmailPhotoUrls.toList(),
      'photoPaths': photoPaths,
"""
save_new = """      'hiddenEmailPhotoUrls': hiddenEmailPhotoUrls.toList(),
      'cubaReceivedPhotoKeys': cubaReceivedPhotoKeys.toList(),
      'photoPaths': photoPaths,
"""
s = replace_once(
    s,
    save_anchor,
    save_new,
    'save Cuba received keys',
)

p.write_text(s)
print('Package refresh fix applied: persisted Cuba photo status is reloaded and preserved.')
