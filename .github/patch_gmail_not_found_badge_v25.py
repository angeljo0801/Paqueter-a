from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Missing expected block: {label}')
    return text.replace(old, new, 1)


helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()

anchor = '''Widget gmailLinkedBadge(BuildContext context) {
'''

helpers = '''bool gmailRecordNotFound(Map<String, dynamic> record) {
  final status = '${record['gmailLookupStatus'] ?? record['gmailBulkLastResult'] ?? ''}'
      .trim()
      .toLowerCase();
  return status == 'not_found';
}

Future<void> persistPackageGmailLookupState({
  required String packageId,
  required String tracking,
  required String state,
}) async {
  final rows = await Store.list('packages', forceRefresh: true);
  var index = -1;
  final cleanId = packageId.trim();
  final cleanTracking = tracking.trim().toLowerCase();

  if (cleanId.isNotEmpty) {
    index = rows.indexWhere((e) => '${e['id'] ?? ''}'.trim() == cleanId);
  }
  if (index < 0 && cleanTracking.isNotEmpty) {
    index = rows.indexWhere(
      (e) => '${e['tracking'] ?? ''}'.trim().toLowerCase() == cleanTracking,
    );
  }
  if (index < 0) return;

  rows[index] = {
    ...rows[index],
    'gmailLookupStatus': state,
    'gmailBulkLastResult': state,
    'gmailLastCheckedAt': DateTime.now().toIso8601String(),
  };
  await Store.saveList('packages', rows);
  Store.clearListCache('packages');
}

Widget gmailNotFoundBadge(BuildContext context) {
  final colors = Theme.of(context).colorScheme;
  return Tooltip(
    message: 'La última búsqueda de Gmail no encontró un correo para este paquete',
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: colors.errorContainer,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.search_off_outlined,
            size: 15,
            color: colors.onErrorContainer,
          ),
          const SizedBox(width: 4),
          Text(
            'No encontrado',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: colors.onErrorContainer,
            ),
          ),
        ],
      ),
    ),
  );
}

'''

if 'bool gmailRecordNotFound(Map<String, dynamic> record)' not in hs:
    hs = replace_once(
        hs,
        anchor,
        helpers + anchor,
        'Gmail status helpers before linked badge',
    )
helper_path.write_text(hs)


packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()

old_badge = '''                          if (gmailRecordIsLinked(p)) ...[
                            const SizedBox(width: 8),
                            gmailLinkedBadge(context),
                          ],
'''
new_badge = '''                          if (gmailRecordNotFound(p)) ...[
                            const SizedBox(width: 8),
                            gmailNotFoundBadge(context),
                          ] else if (gmailRecordIsLinked(p)) ...[
                            const SizedBox(width: 8),
                            gmailLinkedBadge(context),
                          ],
'''
ps = replace_once(
    ps,
    old_badge,
    new_badge,
    'package dashboard Gmail/not-found badge',
)

terminal_anchor = '''        _gmailRecoveryPoll?.cancel();
        await GmailBackgroundSearch.acknowledgeFinished(
          orderNumber: order,
          tracking: track,
        );
'''
terminal_new = '''        _gmailRecoveryPoll?.cancel();
        await GmailBackgroundSearch.acknowledgeFinished(
          orderNumber: order,
          tracking: track,
        );
        await persistPackageGmailLookupState(
          packageId: '${widget.existing?['id'] ?? ''}',
          tracking: track,
          state: 'not_found',
        );
'''
ps = replace_once(
    ps,
    terminal_anchor,
    terminal_new,
    'persist individual Gmail not-found status',
)

success_anchor = '''      if (!mounted) return;
      setState(() {
        gmailStore.text ='''
success_new = '''      await persistPackageGmailLookupState(
        packageId: '${widget.existing?['id'] ?? ''}',
        tracking: track,
        state: 'found',
      );
      if (!mounted) return;
      setState(() {
        gmailStore.text ='''
ps = replace_once(
    ps,
    success_anchor,
    success_new,
    'clear not-found status after individual Gmail success',
)
packages_path.write_text(ps)


bg_path = Path('app/lib/background_sync.dart')
bs = bg_path.read_text()

not_found_old = '''      if(result['found']!=true){ await _advance(st,token,index,base,key,notFound:1); return true; }
'''
not_found_new = '''      if(result['found']!=true){
        await persistPackageGmailLookupState(
          packageId:id,
          tracking:tracking,
          state:'not_found',
        );
        await _advance(st,token,index,base,key,notFound:1);
        return true;
      }
'''
bs = replace_once(
    bs,
    not_found_old,
    not_found_new,
    'bulk not-found persistence',
)

found_anchor = '''      Store.clearListCache('packages');
      final n=(processed['_backgroundPhotoCount'] as num?)?.toInt() ??
'''
found_new = '''      await persistPackageGmailLookupState(
        packageId:id,
        tracking:tracking,
        state:'found',
      );
      Store.clearListCache('packages');
      final n=(processed['_backgroundPhotoCount'] as num?)?.toInt() ??
'''
bs = replace_once(
    bs,
    found_anchor,
    found_new,
    'bulk found status persistence',
)

marker = '''  static bool _doneWithPhotos(Map<String,dynamic> p) {
'''
if 'No encontrado siempre se reintenta' not in bs:
    bs = bs.replace(
        marker,
        "  // No encontrado siempre se reintenta en cada búsqueda masiva.\n" + marker,
        1,
    )

bg_path.write_text(bs)

print('Gmail v25 applied: package No encontrado badge + repeat-on-every-bulk-search behavior.')
