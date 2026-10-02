from pathlib import Path

purchases = Path('app/lib/purchases.dart')
s = purchases.read_text()

s = s.replace(
    "  String q = '';\n",
    "  String q = '';\n  bool backgroundSyncing = false;\n",
    1,
)

old = '''  Future<void> load() async {\n    await WhatsBotPurchaseSyncService.syncSilently();\n    final r = await Future.wait([Store.list('purchases'), Store.list('clients')]);\n    if (!mounted) return;\n    setState(() { rows = active(r[0]); clients = active(r[1]); });\n  }\n'''

new = '''  Future<void> load() async {\n    // Mostrar inmediatamente las compras guardadas en el telefono.\n    // La sincronizacion de red ocurre despues para no dejar la pantalla vacia.\n    final r = await Future.wait([\n      Store.list('purchases'),\n      Store.list('clients'),\n    ]);\n    if (!mounted) return;\n    setState(() {\n      rows = active(r[0]);\n      clients = active(r[1]);\n    });\n\n    if (!backgroundSyncing) {\n      unawaited(_refreshRemoteAfterLocalLoad());\n    }\n  }\n\n  Future<void> _refreshRemoteAfterLocalLoad() async {\n    if (backgroundSyncing) return;\n    backgroundSyncing = true;\n    try {\n      await WhatsBotPurchaseSyncService.syncSilently();\n      final r = await Future.wait([\n        Store.list('purchases'),\n        Store.list('clients'),\n      ]);\n      if (!mounted) return;\n      setState(() {\n        rows = active(r[0]);\n        clients = active(r[1]);\n      });\n    } finally {\n      backgroundSyncing = false;\n    }\n  }\n'''

if old not in s:
    raise SystemExit('No se encontro PurchasesPage.load() esperado')

s = s.replace(old, new, 1)
purchases.write_text(s)
