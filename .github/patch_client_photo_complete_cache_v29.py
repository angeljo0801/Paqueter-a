import base64, zlib
from pathlib import Path
try:
    exec(zlib.decompress(base64.b64decode("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")).decode("utf-8"))
except SystemExit as e:
    if 'Completed package status dropdown' not in str(e):
        raise

    packages_path = Path('app/lib/packages.dart')
    ps = packages_path.read_text()

    helper_anchor = "String inferCarrier(String tracking) {\n"
    completed_helper = r'''Widget packageCompletedBadge(BuildContext context) {
  return Tooltip(
    message: 'Todos los artículos de este paquete están recibidos en Cuba',
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: Colors.green.withValues(alpha: .18),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.green.withValues(alpha: .45)),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.check_circle, size: 15, color: Colors.green),
          SizedBox(width: 4),
          Text(
            'Completed',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: Colors.green,
            ),
          ),
        ],
      ),
    ),
  );
}

'''
    if 'Widget packageCompletedBadge(BuildContext context)' not in ps:
        if helper_anchor not in ps:
            raise SystemExit('Missing fallback Completed helper anchor')
        ps = ps.replace(helper_anchor, completed_helper + helper_anchor, 1)

    badge_anchor = r'''                          if (gmailRecordNotFound(p)) ...[
                            const SizedBox(width: 8),
                            gmailNotFoundBadge(context),
                          ] else if (gmailRecordIsLinked(p)) ...[
                            const SizedBox(width: 8),
                            gmailLinkedBadge(context),
                          ],
'''
    badge_new = r'''                          if ('${p['status'] ?? ''}' == 'Completed') ...[
                            const SizedBox(width: 8),
                            packageCompletedBadge(context),
                          ],
                          if (gmailRecordNotFound(p)) ...[
                            const SizedBox(width: 8),
                            gmailNotFoundBadge(context),
                          ] else if (gmailRecordIsLinked(p)) ...[
                            const SizedBox(width: 8),
                            gmailLinkedBadge(context),
                          ],
'''
    if 'packageCompletedBadge(context)' not in ps:
        if badge_anchor not in ps:
            raise SystemExit('Missing fallback Completed badge anchor')
        ps = ps.replace(badge_anchor, badge_new, 1)

    if "'Completed'" not in ps:
        old_tail = "'Entregado', 'Problema'"
        if old_tail not in ps:
            raise SystemExit('Missing fallback Completed status tail')
        ps = ps.replace(old_tail, "'Entregado', 'Completed', 'Problema'", 1)

    packages_path.write_text(ps)
    print('Client photo v29 applied with flexible Completed status fallback.')
