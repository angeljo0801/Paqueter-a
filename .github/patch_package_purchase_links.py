from pathlib import Path

# Apply after all Gmail, local-first and recovery patches.
# The guard intentionally fails if a prior patch changed a UI anchor.
def replace_once(source, old, new, label):
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'Package/purchase link patch: expected one {label}, found {count}')
    return source.replace(old, new, 1)


main_path = Path('app/lib/main.dart')
main = main_path.read_text()
main = replace_once(main, "part 'packages.dart';",
                    "part 'packages.dart';\npart 'package_purchase_links.dart';",
                    'helper part registration')
main_path.write_text(main)

packages_path = Path('app/lib/packages.dart')
s = packages_path.read_text()
s = replace_once(s,
    '  String? clientId, purchaseId, recipientId;',
    '  String? clientId, purchaseId, recipientId;\n  Set<String> selectedPurchaseIds = <String>{};',
    'package form link state')
s = replace_once(s,
    "    purchaseId = widget.existing?['purchaseId']?.toString();",
    "    purchaseId = widget.existing?['purchaseId']?.toString();\n"
    "    selectedPurchaseIds = PackagePurchaseLinks.ids(widget.existing ?? <String, dynamic>{}).toSet();",
    'load legacy and multiple links')
s = replace_once(s,
    "      'purchaseId': purchaseId,",
    "      'purchaseIds': <String>{...selectedPurchaseIds,\n"
    "        if (purchaseId != null && purchaseId!.isNotEmpty) purchaseId!}.toList(),\n"
    "      'purchaseId': <String>{...selectedPurchaseIds,\n"
    "        if (purchaseId != null && purchaseId!.isNotEmpty) purchaseId!}.firstOrNull,",
    'write link ids and legacy primary')
s = replace_once(s,
    "setState(() { clientId = v; purchaseId = null; recipientId = null; })",
    "setState(() { clientId = v; purchaseId = null; selectedPurchaseIds.clear(); recipientId = null; })",
    'client-change safety')

old_selector = "_drop('Compra / pedido relacionado', purchaseId, cp.map((p) => DropdownMenuItem(value: '${p['id']}', child: Text('${p['store']} · ${p['description']}'))).toList(), (v) => setState(() => purchaseId = v)),"
new_selector = """Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Compras y pedidos vinculados',
                style: TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: clientId == null ? null : () async {
                  final next = await PackagePurchaseLinks.choosePurchases(
                    context,
                    clientId: clientId!,
                    purchases: purchases,
                    selected: <String>{...selectedPurchaseIds,
                      if (purchaseId != null && purchaseId!.isNotEmpty) purchaseId!},
                  );
                  if (next == null || !mounted) return;
                  setState(() {
                    selectedPurchaseIds = next;
                    purchaseId = next.firstOrNull;
                  });
                },
                icon: const Icon(Icons.link),
                label: const Text('Seleccionar compras y pedidos'),
              ),
              if (selectedPurchaseIds.isEmpty && purchaseId == null)
                const Text('Sin vínculos. Puedes seleccionar más de una compra o pedido.'),
              if (selectedPurchaseIds.isNotEmpty || purchaseId != null)
                Wrap(spacing: 6, runSpacing: 6, children: [
                  for (final id in <String>{...selectedPurchaseIds,
                    if (purchaseId != null && purchaseId!.isNotEmpty) purchaseId!})
                    InputChip(
                      label: Text(
                        purchases.where((p) => '${p['id']}' == id).isEmpty
                          ? 'Compra / pedido #$id'
                          : PackagePurchaseLinks.description(
                              purchases.firstWhere((p) => '${p['id']}' == id)),
                      ),
                      onDeleted: () => setState(() {
                        selectedPurchaseIds.remove(id);
                        if (purchaseId == id) purchaseId = selectedPurchaseIds.firstOrNull;
                      }),
                    ),
                ]),
            ]),
          ),
        ),"""
s = replace_once(s, old_selector, new_selector, 'package purchase selector')

# Keep the Gmail badge visible; add a distinct link count beside it.
badge_anchor = "                          if (gmailRecordIsLinked(p)) ...["
if badge_anchor in s:
    s = replace_once(s, badge_anchor,
      """                          if (PackagePurchaseLinks.ids(p).isNotEmpty) ...[
                            const SizedBox(width: 6),
                            const Icon(Icons.link, size: 16),
                            Text('${PackagePurchaseLinks.ids(p).length}'),
                          ],
""" + badge_anchor, 'linked package counter')

# Existing local "cp" dropdown filter is no longer needed.
s = s.replace(
    "    final cp = purchases.where((e) => clientId != null && purchaseHasClient(e, clientId!)).toList();\n",
    '', 1)
packages_path.write_text(s)

purchases_path = Path('app/lib/purchases.dart')
s = purchases_path.read_text()
s = replace_once(s,
    """                        trailing: Wrap(
                          children: [
                            if (isUnassigned(p))""",
    """                        trailing: Wrap(
                          children: [
                            IconButton(
                              tooltip: 'Vincular paquetes',
                              icon: const Icon(Icons.link),
                              onPressed: () async {
                                await PackagePurchaseLinks.choosePackagesForPurchase(context, p);
                                if (mounted) load();
                              },
                            ),
                            if (isUnassigned(p))""",
    'purchase list reverse-link action')

s = replace_once(s,
    "  bool loaded = false;\n",
    "  bool loaded = false;\n  Future<List<Map<String, dynamic>>>? linkedPackageRows;\n",
    'purchase editor cached package link rows')
s = replace_once(s,
    "    clients = active(await Store.list('clients'));",
    "    clients = active(await Store.list('clients'));\n"
    "    linkedPackageRows = Store.list('packages');",
    'purchase editor linked packages load')

purchase_type_anchor = "        _drop('Tipo de compra', type,"
if s.count(purchase_type_anchor) != 1:
    raise SystemExit('Package/purchase link patch: purchase type field missing')
section = """        if (widget.existing != null) ...[
          FutureBuilder<List<Map<String, dynamic>>>(
            future: linkedPackageRows,
            builder: (context, snapshot) {
              final linked = PackagePurchaseLinks.forPurchase(
                snapshot.data ?? <Map<String, dynamic>>[],
                '${widget.existing!['id']}',
              );
              return Card(child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Paquetes vinculados (${linked.length})',
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                    const SizedBox(height: 8),
                    for (final p in linked)
                      ListTile(
                        dense: true,
                        leading: const Icon(Icons.inventory_2_outlined),
                        title: Text('${p['tracking'] ?? ''}'),
                        subtitle: Text('${p['status'] ?? ''}'),
                        onTap: () async {
                          await Navigator.push(context, MaterialPageRoute(
                            builder: (_) => PackageEditPage(existing: p)));
                          if (mounted) setState(() {
                            linkedPackageRows = Store.list('packages');
                          });
                        },
                      ),
                    OutlinedButton.icon(
                      icon: const Icon(Icons.link),
                      label: const Text('Vincular / desvincular paquetes'),
                      onPressed: () async {
                        await PackagePurchaseLinks.choosePackagesForPurchase(
                          context, widget.existing!);
                        if (mounted) setState(() {
                          linkedPackageRows = Store.list('packages');
                        });
                      },
                    ),
                  ],
                ),
              ));
            },
          ),
          const SizedBox(height: 12),
        ],
"""
s = s.replace(purchase_type_anchor, section + purchase_type_anchor, 1)
purchases_path.write_text(s)

helper = Path('app/lib/package_purchase_links.dart')
if not helper.exists():
    raise SystemExit('Shared package-purchase links helper was not copied to app/lib')
assert 'class PackagePurchaseLinks' in helper.read_text()
print('Package ↔ purchase/order many-to-many UI and persistence installed.')
