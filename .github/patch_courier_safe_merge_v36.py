from pathlib import Path

p = Path('app/lib/tracking_service.dart')
s = p.read_text()
start = s.find('  static Future<CourierSyncResult> syncAll({bool createMissing = true}) async {')
if start < 0:
    raise SystemExit('Safe courier merge: syncAll missing')
end = s.find('\n  }\n', start)
if end < 0:
    raise SystemExit('Safe courier merge: syncAll end missing')
block = s[start:end]

old = """    final rows = await Store.list('packages');
    final notices = await Store.list('courierNotifications');
    var checked = 0, changed = 0, errors = 0;"""
new = """    final rows = await Store.list('packages');
    final originals = {
      for (final p in rows) '${p['id']}': Map<String, dynamic>.from(p),
    };
    final notices = await Store.list('courierNotifications');
    final originalNoticeIds = notices.map((n) => '${n['id']}').toSet();
    var checked = 0, changed = 0, errors = 0;"""
if block.count(old)!=1:
    raise SystemExit('Safe courier merge: initial fetch anchor missing')
block=block.replace(old,new,1)

old_end="""    await Store.saveList('packages', rows);
    await Store.saveList('courierNotifications', notices);
    return CourierSyncResult(checked: checked, changed: changed, errors: errors);"""
new_end="""    // Courier calls can take several minutes. They run after the dashboard
    // loads, so never overwrite newer package edits or Gmail results with
    // a stale snapshot loaded before the network requests.
    final latest = await Store.list('packages', forceRefresh: true);
    const courierFields = <String>[
      'easyPostTrackerId', 'courierStatus', 'courierStatusEs',
      'lastCourierSync', 'estimatedDelivery', 'publicTrackingUrl',
      'courierDetails', 'carrierRemote', 'courierError',
    ];
    for (final updated in rows) {
      final id = '${updated['id']}';
      final old = originals[id];
      if (old == null ||
          '${old['lastCourierSync']}' == '${updated['lastCourierSync']}') {
        continue;
      }
      final i = latest.indexWhere((p) => '${p['id']}' == id);
      if (i < 0 || latest[i]['deleted'] == true ||
          '${latest[i]['tracking']}' != '${old['tracking']}') {
        continue;
      }
      final current = latest[i];
      for (final field in courierFields) {
        // Do not clobber a value changed by another operation during sync.
        if (jsonEncode(current[field]) != jsonEncode(old[field])) continue;
        if (updated.containsKey(field)) {
          current[field] = updated[field];
        } else {
          current.remove(field);
        }
      }
      if (current['status'] == old['status'] &&
          updated['status'] != old['status']) {
        current['status'] = updated['status'];
      }
      if (current['receivedAt'] == null && updated['receivedAt'] != null) {
        current['receivedAt'] = updated['receivedAt'];
      }
    }
    await Store.saveList('packages', latest);
    final latestNotices = await Store.list('courierNotifications', forceRefresh: true);
    final existingNoticeIds = latestNotices.map((n) => '${n['id']}').toSet();
    for (final n in notices) {
      final id = '${n['id']}';
      if (!originalNoticeIds.contains(id) && existingNoticeIds.add(id)) {
        latestNotices.add(n);
      }
    }
    await Store.saveList('courierNotifications', latestNotices);
    return CourierSyncResult(checked: checked, changed: changed, errors: errors);"""
if block.count(old_end)!=1:
    raise SystemExit('Safe courier merge: commit anchor missing')
block=block.replace(old_end,new_end,1)
s=s[:start]+block+s[end:]
p.write_text(s)
print('Courier sync v36: merge only fresh courier fields, preserve local edits during background network calls.')
