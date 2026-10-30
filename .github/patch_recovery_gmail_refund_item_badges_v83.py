from pathlib import Path

# v83: Refund evidence comes from verified same-order Gmail notices.
# Mark ONLY identified product rows. A generic refund email without an
# identifiable item gets an order-level notice, never an all-item flag.
# Covers both package and linked purchase editors, without modifying
# Gmail photo classification or local/manual photos.
helper=Path('app/lib/gmail_purchase_link.dart')
s=helper.read_text()
needle="String gmailItemKey(dynamic raw) {"
assert s.count(needle)==1,'v83 Gmail item-key helper missing'
# Keep exact normalized names to avoid false labels for similarly-named items.
extra=r'''
bool gmailItemMentionedInRefund(
  dynamic name, List<String> refundedItemNames,
) {
  final key = gmailItemKey(name);
  if (key.length < 5) return false;
  return refundedItemNames.any((candidate) => gmailItemKey(candidate) == key);
}

'''
s=s.replace(needle,extra+needle,1)
helper.write_text(s)

p=Path('app/lib/packages.dart')
s=p.read_text()
decl="  List<Map<String, dynamic>> gmailItems = [];"
assert s.count(decl)==1,'v83 Gmail item state missing'
s=s.replace(decl,decl+'''
  List<Map<String, dynamic>> gmailRefundNotices = [];
  List<String> gmailRefundedItemNames = [];
''',1)
load="    gmailItems = dynList(widget.existing?['gmailItems']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();"
assert s.count(load)==1,'v83 old package Gmail item restore'
s=s.replace(load,load+'''
    gmailRefundNotices = dynList(widget.existing?['gmailRefundNotices'])
        .whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
    gmailRefundedItemNames = dynList(widget.existing?['gmailRefundedItemNames'])
        .map((e) => e.toString()).where((e) => e.trim().isNotEmpty).toList();
''',1)
merge="        gmailItems = mergeGmailDetectedItems(gmailItems, data['items']);"
assert s.count(merge)==1,'v83 package result application missing'
s=s.replace(merge,merge+'''
        // This is evidence from the CURRENT verified Gmail lookup. A generic
        // refund notice must not label every item in this package.
        gmailRefundNotices = dynList(data['refundNotices'])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e)).toList();
        gmailRefundedItemNames = dynList(data['refundedItemNames'])
            .map((e) => e.toString()).where((e) => e.trim().isNotEmpty)
            .toList();
''',1)
persist="      'gmailItems': gmailItems,"
assert s.count(persist)==1,'v83 package storage schema missing'
s=s.replace(persist,persist+'''
      'gmailRefundNotices': gmailRefundNotices,
      'gmailRefundedItemNames': gmailRefundedItemNames,
''',1)
# Package's checklist annotates the individual recognized product.
title="                       title: Text("
# Don't depend on indentation; the literal only exists in the original
# Gmail package checklist, not the client/purchase page.
title="                      title: Text('\${gmailItems[i]['name'] ?? 'Artículo'}'),"
assert s.count(title)==1,'v83 package item title changed'
s=s.replace(title,'''                      title: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('\${gmailItems[i]['name'] ?? 'Artículo'}'),
                          if (gmailItemMentionedInRefund(
                              gmailItems[i]['name'], gmailRefundedItemNames))
                            const Text(
                              'Reembolso mencionado en Gmail',
                              style: TextStyle(
                                  color: Colors.orangeAccent,
                                  fontWeight: FontWeight.bold, fontSize: 12),
                            ),
                        ],
                      ),''',1)
# Visible notice even when the provider email lacks specific article names.
check="        if (gmailItems.isNotEmpty) ...["
assert s.count(check)==1,'v83 package refund banner location missing'
s=s.replace(check,'''        if (gmailRefundNotices.isNotEmpty) ...[
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Avisos de reembolso encontrados en Gmail',
                      style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text(gmailRefundedItemNames.isNotEmpty
                      ? 'Artículos identificados: \${gmailRefundedItemNames.join(', ')}'
                      : 'El correo habla de un reembolso, pero no identifica '
                        'con seguridad qué artículo. No se marcará ninguno.'),
                  for (final row in gmailRefundNotices.take(3))
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(
                        '\${row['date'] ?? ''} · \${row['subject'] ?? ''}',
                        style: const TextStyle(fontSize: 11),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
'''+check,1)

# Transfer metadata to an explicitly linked purchase without overwriting
# other purchases. Only item name matches are marked; no purchase-wide refund.
prop="    await _propagateReceivedGmailItemsToPurchase();"
assert s.count(prop)==1,'v83 saved package propagation anchor'
s=s.replace(prop,prop+"\n    await _propagateRefundGmailEvidenceToPurchase();",1)
method="  Future<void> _propagateReceivedGmailItemsToPurchase() async {"
assert s.count(method)==1,'v83 propagation method anchor missing'
s=s.replace(method,r'''
  Future<void> _propagateRefundGmailEvidenceToPurchase() async {
    if (purchaseId == null || gmailRefundNotices.isEmpty) return;
    final rows = await Store.list('purchases', forceRefresh: true);
    final index = rows.indexWhere((e) => '\${e['id']}' == purchaseId);
    if (index < 0) return;
    rows[index] = {
      ...rows[index],
      'gmailRefundNotices': gmailRefundNotices,
      'gmailRefundedItemNames': gmailRefundedItemNames,
    };
    await Store.saveList('purchases', rows);
  }

'''+method,1)
p.write_text(s)

# Purchase editor (independent order-number lookup and linked package).
p=Path('app/lib/purchases.dart')
s=p.read_text()
anchor="  List<String> gmailPurchaseSourceEmails = [];"
assert s.count(anchor)==1,'v83 purchase source state missing'
s=s.replace(anchor,anchor+'''
  List<Map<String, dynamic>> gmailPurchaseRefundNotices = [];
  List<String> gmailPurchaseRefundedItemNames = [];
''',1)
restore="      gmailPurchaseSourceEmails = dynList(widget.existing!['gmailSourceEmails']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();"
assert s.count(restore)==1,'v83 purchase load anchor missing'
s=s.replace(restore,restore+'''
      gmailPurchaseRefundNotices = dynList(widget.existing!['gmailRefundNotices'])
          .whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
      gmailPurchaseRefundedItemNames =
          dynList(widget.existing!['gmailRefundedItemNames'])
              .map((e) => e.toString()).where((e) => e.trim().isNotEmpty)
              .toList();
''',1)
merge="          items = mergeGmailDetectedItems("
assert s.count(merge)==1,'v83 purchase Gmail item merge missing'
s=s.replace(merge,'''          for (final raw in dynList(data['refundNotices'])) {
            if (raw is! Map) continue;
            final row = Map<String, dynamic>.from(raw);
            if (!gmailPurchaseRefundNotices.any((old) =>
                old['subject'] == row['subject'] &&
                old['date'] == row['date'])) {
              gmailPurchaseRefundNotices.add(row);
            }
          }
          for (final raw in dynList(data['refundedItemNames'])) {
            final name = raw.toString().trim();
            if (name.isNotEmpty &&
                !gmailPurchaseRefundedItemNames.contains(name)) {
              gmailPurchaseRefundedItemNames.add(name);
            }
          }
'''+merge,1)
persist="      'gmailPurchaseStatus':"
# Actual stored key is gmailStatus, inspect against canonical patch version.
storage="      'gmailSourceEmails': gmailPurchaseSourceEmails,"
assert s.count(storage)==1,'v83 purchase persist anchor missing'
s=s.replace(storage,storage+'''
      'gmailRefundNotices': gmailPurchaseRefundNotices,
      'gmailRefundedItemNames': gmailPurchaseRefundedItemNames,
''',1)
# Item editing display: show flag directly beside its name in purchase list.
title="              title: Text('\${e['name']}'),"
assert s.count(title)==1,'v83 purchase item title missing'
s=s.replace(title,'''              title: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('\${e['name']}'),
                  if (gmailItemMentionedInRefund(
                      e['name'], gmailPurchaseRefundedItemNames))
                    const Text(
                      'Reembolso mencionado en Gmail',
                      style: TextStyle(color: Colors.orangeAccent,
                          fontWeight: FontWeight.bold, fontSize: 12),
                    ),
                ],
              ),''',1)
# Show order-level alert even if the refunded product could not be identified.
marker="        if (items.isEmpty) const Text('No hay artículos todavía."
idx=s.find(marker)
assert idx >= 0,'v83 purchase item-section anchor missing'
s=s[:idx]+'''        if (gmailPurchaseRefundNotices.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text(
              gmailPurchaseRefundedItemNames.isEmpty
                  ? 'Aviso de reembolso en Gmail: artículo no identificado'
                  : 'Reembolso en Gmail: \${gmailPurchaseRefundedItemNames.join(', ')}',
              style: const TextStyle(color: Colors.orangeAccent),
            ),
          ),
'''+s[idx:]
p.write_text(s)
assert 'gmailPurchaseRefundNotices' in s
assert 'gmailRefundNotices' in Path('app/lib/packages.dart').read_text()
print('v83: package and purchase checklists persist and highlight verified item-level refund notices.')
