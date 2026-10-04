from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# Shared Gmail-link detector and compact badge. The detector intentionally uses
# persisted reconstruction/link fields so old records are marked too; no new
# migration or manual flag is required.
helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()
if 'bool gmailRecordIsLinked(Map<String, dynamic> record)' not in hs:
    hs += r'''

bool _gmailEvidenceHasValue(dynamic value) {
  if (value == null) return false;
  if (value is String) return value.trim().isNotEmpty;
  if (value is Iterable) {
    for (final item in value) {
      if (item is Map) {
        if (item.isNotEmpty) return true;
      } else if ('$item'.trim().isNotEmpty) {
        return true;
      }
    }
    return false;
  }
  if (value is Map) return value.isNotEmpty;
  return '$value'.trim().isNotEmpty;
}

bool gmailRecordIsLinked(Map<String, dynamic> record) {
  const evidenceKeys = <String>[
    'gmailLinkedOrderNumbers',
    'gmailSourceEmails',
    'emailPhotoUrls',
    'emailAttachmentImages',
    'gmailItems',
    'gmailStatus',
    'gmailEstimatedDelivery',
  ];
  for (final key in evidenceKeys) {
    if (_gmailEvidenceHasValue(record[key])) return true;
  }
  return false;
}

Widget gmailLinkedBadge(BuildContext context) {
  final colors = Theme.of(context).colorScheme;
  return Tooltip(
    message: 'Ya vinculado / reconstruido con Gmail',
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: colors.secondaryContainer,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.mark_email_read_outlined,
            size: 15,
            color: colors.onSecondaryContainer,
          ),
          const SizedBox(width: 4),
          Text(
            'Gmail ✓',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: colors.onSecondaryContainer,
            ),
          ),
        ],
      ),
    ),
  );
}
'''
    helper_path.write_text(hs)


# Main purchases/orders dashboard: put the badge beside store + amount so the
# user can see the state before opening the row.
purchases_path = Path('app/lib/purchases.dart')
us = purchases_path.read_text()
old_purchase_title = """                        title: Text(\n                          '${p['store']} · ${money(isUnassigned(p) ? number(p['total']) : number(p['clientTotal']))}',\n                        ),\n"""
new_purchase_title = """                        title: Row(\n                          children: [\n                            Expanded(\n                              child: Text(\n                                '${p['store']} · ${money(isUnassigned(p) ? number(p['total']) : number(p['clientTotal']))}',\n                                overflow: TextOverflow.ellipsis,\n                              ),\n                            ),\n                            if (gmailRecordIsLinked(p)) ...[\n                              const SizedBox(width: 8),\n                              gmailLinkedBadge(context),\n                            ],\n                          ],\n                        ),\n"""
if 'if (gmailRecordIsLinked(p))' not in us:
    us = replace_once(us, old_purchase_title, new_purchase_title, 'purchase dashboard title')
    purchases_path.write_text(us)


# Main packages dashboard.
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()
old_package_title = "                      title: Text('${p['tracking']}'),\n"
new_package_title = """                      title: Row(\n                        children: [\n                          Expanded(\n                            child: Text(\n                              '${p['tracking']}',\n                              overflow: TextOverflow.ellipsis,\n                            ),\n                          ),\n                          if (gmailRecordIsLinked(p)) ...[\n                            const SizedBox(width: 8),\n                            gmailLinkedBadge(context),\n                          ],\n                        ],\n                      ),\n"""
if 'gmailLinkedBadge(context)' not in ps.split('class PackageEditPage')[0]:
    ps = replace_once(ps, old_package_title, new_package_title, 'package dashboard title')
    packages_path.write_text(ps)


# Client detail dashboard also lists purchases and packages. Mark them there too
# so entering a client does not hide whether Gmail reconstruction already ran.
clients_path = Path('app/lib/clients.dart')
cs = clients_path.read_text()
old_client_purchase_title = """                  title: Text(\n                    '${p['store']} · ${money(purchaseAmountForClient(p, widget.clientId))}',\n                  ),\n"""
new_client_purchase_title = """                  title: Row(\n                    children: [\n                      Expanded(\n                        child: Text(\n                          '${p['store']} · ${money(purchaseAmountForClient(p, widget.clientId))}',\n                          overflow: TextOverflow.ellipsis,\n                        ),\n                      ),\n                      if (gmailRecordIsLinked(p)) ...[\n                        const SizedBox(width: 8),\n                        gmailLinkedBadge(context),\n                      ],\n                    ],\n                  ),\n"""
if cs.count('gmailRecordIsLinked(p)') < 1:
    cs = replace_once(cs, old_client_purchase_title, new_client_purchase_title, 'client purchase title')

old_client_package_title = "                  title: Text('${p['tracking']}'),\n"
new_client_package_title = """                  title: Row(\n                    children: [\n                      Expanded(\n                        child: Text(\n                          '${p['tracking']}',\n                          overflow: TextOverflow.ellipsis,\n                        ),\n                      ),\n                      if (gmailRecordIsLinked(p)) ...[\n                        const SizedBox(width: 8),\n                        gmailLinkedBadge(context),\n                      ],\n                    ],\n                  ),\n"""
if cs.count('gmailRecordIsLinked(p)') < 2:
    cs = replace_once(cs, old_client_package_title, new_client_package_title, 'client package title')
clients_path.write_text(cs)

print('Gmail linked/reconstructed badges added to overview dashboards.')
