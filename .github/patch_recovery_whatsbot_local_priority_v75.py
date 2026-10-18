from pathlib import Path

# v75: sync no longer overwrites user edits, deletion tombstones, or newer
# package rows with old lists after a long backend HTTP call.
p=Path('app/lib/whatsbot_sync.dart')
s=p.read_text()

a=s.index('  static Future<int> _pushPackages(')
b=s.index('  static Future<bool> _uploadSnapshot(',a)
fn=s[a:b]
assert fn.count('    var changed = false;')==1
fn=fn.replace('    var changed = false;', '''    var changed = false;
    final pushedMetadata = <Map<String, String>>[];''',1)
old="""          package['whatsbotPackageSyncId'] = externalId;
          package['whatsbotPackagePushHash'] = fingerprint;
          changed = true;"""
new="""          package['whatsbotPackageSyncId'] = externalId;
          package['whatsbotPackagePushHash'] = fingerprint;
          pushedMetadata.add({
            'id': id,
            'tracking': tracking,
            'stamp': (package['paqueteriaLocalEditedAt'] ?? '').toString(),
            'external': externalId,
            'fingerprint': fingerprint,
          });
          changed = true;"""
assert fn.count(old)==1,'v75: package push success changed'
fn=fn.replace(old,new,1)
old="    if (changed) await Store.saveList('packages', packages);"
new=r'''    if (changed) {
      final fresh = await Store.list('packages', forceRefresh: true);
      var mutated = false;
      for (final meta in pushedMetadata) {
        final index = fresh.indexWhere((row) =>
            (row['id'] ?? '').toString() == meta['id']);
        if (index < 0 || fresh[index]['deleted'] == true ||
            (fresh[index]['tracking'] ?? '').toString().trim() !=
                meta['tracking'] ||
            (fresh[index]['paqueteriaLocalEditedAt'] ?? '').toString() !=
                meta['stamp']) continue;
        fresh[index]['whatsbotPackageSyncId'] = meta['external'];
        fresh[index]['whatsbotPackagePushHash'] = meta['fingerprint'];
        mutated = true;
      }
      if (mutated) await Store.saveList('packages', fresh);
    }'''
assert fn.count(old)==1,'v75: package push stale write changed'
fn=fn.replace(old,new,1)
s=s[:a]+fn+s[b:]

a=s.index('  static Future<int> _applyRemoteActions(')
b=s.index('  static Future<int> syncSilently()',a)
fn=s[a:b]
assert fn.count('      var packagesChanged = false;')==1
fn=fn.replace('      var packagesChanged = false;', '''      var packagesChanged = false;
      final statusEdits = <String, Map<String, String>>{};''',1)
old="""            if (index >= 0) {
              packages[index]['status'] = status;"""
new="""            if (index >= 0 &&
                packages[index]['deleted'] != true &&
                (packages[index]['paqueteriaLocalEditedAt'] ?? '')
                    .toString().isEmpty) {
              statusEdits[(packages[index]['id'] ?? '').toString()] = {
                'status': status,
                'actionId': actionId,
              };
              packages[index]['status'] = status;"""
assert fn.count(old)==1,'v75: package status action changed'
fn=fn.replace(old,new,1)
old="      if (packagesChanged) await Store.saveList('packages', packages);"
new=r'''      if (packagesChanged) {
        final fresh = await Store.list('packages', forceRefresh: true);
        var updated = false;
        for (final row in fresh) {
          final changes = statusEdits[(row['id'] ?? '').toString()];
          if (changes == null || row['deleted'] == true ||
              (row['paqueteriaLocalEditedAt'] ?? '')
                  .toString().isNotEmpty) continue;
          row['status'] = changes['status'];
          row['whatsbotActionId'] = changes['actionId'];
          row['whatsbotActionAt'] =
              DateTime.now().toUtc().toIso8601String();
          updated = true;
        }
        if (updated) await Store.saveList('packages', fresh);
      }'''
assert fn.count(old)==1,'v75: stale status action writer changed'
fn=fn.replace(old,new,1)
s=s[:a]+fn+s[b:]

old="  static Future<int> sync({bool forcePush = false}) async {"
new=r'''  // Background, resume and manual sync must not race one another.
  static bool _syncRunning = false;
  static Future<int> sync({bool forcePush = false}) async {
    if (_syncRunning) return 0;
    _syncRunning = true;
    try {
      return await _syncProtected(forcePush: forcePush);
    } finally {
      _syncRunning = false;
    }
  }

  static Future<int> _syncProtected({bool forcePush = false}) async {'''
assert s.count(old)==1, 'v75: sync API changed'
s=s.replace(old,new,1)

a=s.index('  static Future<int> _syncProtected(')
fn=s[a:]
old="    final packages = await Store.list('packages');"
new=r'''    final packages = await Store.list('packages', forceRefresh: true);
    final deletedIds = await PackageDeletionLedger.load();
    for (final row in packages.where((r) => r['deleted'] == true)) {
      deletedIds.addAll(PackageDeletionLedger.ids(row));
    }
    final changedRemotePackageIds = <String>{};'''
assert fn.count(old)==1,'v75: remote package list changed'
fn=fn.replace(old,new,1)

old="""      if (externalId.isEmpty || tracking.isEmpty) continue;

      var existingPackageIndex = packages.indexWhere("""
new="""      if (externalId.isEmpty || tracking.isEmpty) continue;

      final remoteIdentity = <String, dynamic>{
        'tracking': tracking,
        'whatsbotPackageSyncId': externalId,
        'whatsbotPackageRemoteId': item['id'],
      };
      if (PackageDeletionLedger.blocks(remoteIdentity, deletedIds)) continue;

      var existingPackageIndex = packages.indexWhere("""
assert fn.count(old)==1,'v75: remote package loop changed'
fn=fn.replace(old,new,1)

loop=fn.index('    for (final item in remotePackages.reversed) {')
idx=fn.index("      final remoteUpdatedAt =",loop)
fn=fn[:idx]+r'''      if (existingPackageIndex >= 0) {
        final local = packages[existingPackageIndex];
        if (local['deleted'] == true ||
            (local['paqueteriaLocalEditedAt'] ?? '')
                .toString().isNotEmpty) continue;
      }

'''+fn[idx:]

old="""      packagesChanged = true;
      importedPackages++;
    }

    if (clientsChanged)"""
new="""      packagesChanged = true;
      changedRemotePackageIds.add((incoming['id'] ?? '').toString());
      importedPackages++;
    }

    if (clientsChanged)"""
assert fn.count(old)==1,'v75: remote changed package IDs changed'
fn=fn.replace(old,new,1)

old="    if (packagesChanged) await Store.saveList('packages', packages);"
new=r'''    if (packagesChanged) {
      // Rebase only imported remote changes, never a stale full list.
      final fresh = await Store.list('packages', forceRefresh: true);
      final newlyDeleted = await PackageDeletionLedger.load();
      for (final row in fresh.where((r) => r['deleted'] == true)) {
        newlyDeleted.addAll(PackageDeletionLedger.ids(row));
      }
      var wrote = false;
      for (final row in packages) {
        final id = (row['id'] ?? '').toString();
        if (!changedRemotePackageIds.contains(id) ||
            PackageDeletionLedger.blocks(row, newlyDeleted)) continue;
        final index = fresh.indexWhere((e) =>
            (e['id'] ?? '').toString() == id);
        if (index >= 0) {
          if (fresh[index]['deleted'] == true ||
              (fresh[index]['paqueteriaLocalEditedAt'] ?? '')
                  .toString().isNotEmpty) continue;
          fresh[index] = {...fresh[index], ...row};
          wrote = true;
        } else {
          final track = PackageDeletionLedger.tracking(row['tracking']);
          if (fresh.any((e) =>
              PackageDeletionLedger.tracking(e['tracking']) == track)) {
            continue;
          }
          fresh.add(row);
          wrote = true;
        }
      }
      if (wrote) await Store.saveList('packages', fresh);
    }'''
assert fn.count(old)==1,'v75: stale remote import list changed'
fn=fn.replace(old,new,1)
s=s[:a]+fn
p.write_text(s)
print('v75: no stale WhatsBot list overwrites; local package edits and deletions take priority.')
