from pathlib import Path

clients = Path('app/lib/clients.dart')
s = clients.read_text()

s = s.replace(
    "  bool syncing = false;\n",
    "  bool syncing = false;\n  bool backgroundSyncing = false;\n",
    1,
)

old = '''  Future<void> load() async {\n    await WhatsBotPurchaseSyncService.syncSilently();\n    final r = await Future.wait([\n      Store.list('clients'),\n      Store.list('purchases'),\n      Store.list('payments'),\n    ]);\n    if (!mounted) return;\n    setState(() {\n      rows = active(r[0]);\n      purchases = active(r[1]);\n      payments = active(r[2]);\n    });\n  }\n'''

new = '''  Future<void> load() async {\n    // Mostrar primero lo que ya esta guardado en el telefono.\n    // La sincronizacion de red puede tardar bastante (especialmente si hay fotos),\n    // y antes dejaba la pantalla aparentemente vacia hasta que terminaba.\n    final r = await Future.wait([\n      Store.list('clients'),\n      Store.list('purchases'),\n      Store.list('payments'),\n    ]);\n    if (!mounted) return;\n    setState(() {\n      rows = active(r[0]);\n      purchases = active(r[1]);\n      payments = active(r[2]);\n    });\n\n    if (!syncing && !backgroundSyncing) {\n      unawaited(_refreshRemoteAfterLocalLoad());\n    }\n  }\n\n  Future<void> _refreshRemoteAfterLocalLoad() async {\n    if (backgroundSyncing || syncing) return;\n    backgroundSyncing = true;\n    try {\n      await WhatsBotPurchaseSyncService.syncSilently();\n      final r = await Future.wait([\n        Store.list('clients'),\n        Store.list('purchases'),\n        Store.list('payments'),\n      ]);\n      if (!mounted) return;\n      setState(() {\n        rows = active(r[0]);\n        purchases = active(r[1]);\n        payments = active(r[2]);\n      });\n    } finally {\n      backgroundSyncing = false;\n    }\n  }\n'''

if old not in s:
    raise SystemExit('No se encontro ClientsPage.load() esperado')

s = s.replace(old, new, 1)
clients.write_text(s)
