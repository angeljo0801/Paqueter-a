from pathlib import Path

p = Path('app/lib/main.dart')
s = p.read_text()

def one(old: str, new: str, label: str):
    global s
    n = s.count(old)
    if n != 1:
        raise SystemExit(f'Startup v37: {label}: expected one anchor, got {n}')
    s = s.replace(old, new, 1)


# Delay automatic backup and remote sync until the local collections can load.
# Never overwrite a good backup with a snapshot of incomplete startup data.
one(
    'Future<void> main() async {',
    "final Completer<void> initialLocalDataReady = Completer<void>();\n\nFuture<void> main() async {",
    'startup readiness completer',
)
one(
    '  runApp(const PaqueteriaApp());\n',
    """  runApp(const PaqueteriaApp());
  // Await local data readiness before competing for SharedPreferences I/O.
  await initialLocalDataReady.future;
""",
    'delay backup and remote sync until valid local data',
)
one(
    '    FinanceSyncService.refreshSnapshot();\n    Timer(const Duration(milliseconds: 1350), () {',
    """    unawaited(initialLocalDataReady.future.then((_) async {
      try { await FinanceSyncService.refreshSnapshot(); } catch (_) {}
    }));
    Timer(const Duration(milliseconds: 1350), () {""",
    'defer finance snapshot until after startup',
)

# IndexedStack previously started all five heavy tabs on launch.
one(
    '  int index = 0;\n  List<Widget> pages =',
    '  int index = 0;\n  final Set<int> _visitedTabs = <int>{0};\n  List<Widget> pages =',
    'lazy-tab state',
)
one(
    """      body: IndexedStack(
        index: index,
        children: pages,
      ),""",
    """      body: IndexedStack(
        index: index,
        children: List<Widget>.generate(
          pages.length,
          (i) => _visitedTabs.contains(i)
              ? pages[i] : const SizedBox.shrink(),
        ),
      ),""",
    'instantiate tab only upon first visit',
)
one(
    '        onDestinationSelected: (v) => setState(() => index = v),',
    '        onDestinationSelected: (v) => setState(() { index = v; _visitedTabs.add(v); }),',
    'on-demand tab activation',
)

one(
    "  String dashboardLoadError = '';",
    "  String dashboardLoadError = '';\n  String dashboardLoadWarning = '';",
    'partial-load warning',
)
begin = s.index('  Future<void> load({bool syncCourier = false}) async {', s.index('class _DashboardPageState'))
end = s.index('\n  Future<void> openCourier() async {', begin)
new = r'''  Future<void> load({bool syncCourier = false}) async {
    final failedKeys = <String>[];
    const storageKeys = <String>[
      'clients', 'purchases', 'packages', 'trips', 'payments',
      'flightWatches', 'agents', 'agentReports',
    ];
    const labels = <String>[
      'clientes', 'compras', 'paquetes', 'viajes', 'pagos',
      'vuelos', 'agentes', 'reportes',
    ];

    Future<Object?> readSafely(String key) async {
      try {
        return await Store.list(key).timeout(const Duration(seconds: 10));
      } catch (_) {
        failedKeys.add(key);
        return null;
      }
    }

    Future<Object?> readSettings() async {
      try {
        return await Store.settings().timeout(const Duration(seconds: 10));
      } catch (_) {
        failedKeys.add('settings');
        return null;
      }
    }

    final values = await Future.wait<Object?>([
      for (final key in storageKeys) readSafely(key),
      readSettings(),
    ]);
    if (!mounted) return;

    final unreadable = <String>[
      for (var i = 0; i < storageKeys.length; i++)
        if (failedKeys.contains(storageKeys[i])) labels[i],
      if (failedKeys.contains('settings')) 'configuración',
    ];

    setState(() {
      if (values[0] != null) clients = active(values[0] as List<Map<String, dynamic>>);
      if (values[1] != null) purchases = active(values[1] as List<Map<String, dynamic>>);
      if (values[2] != null) packages = active(values[2] as List<Map<String, dynamic>>);
      if (values[3] != null) trips = active(values[3] as List<Map<String, dynamic>>);
      if (values[4] != null) payments = active(values[4] as List<Map<String, dynamic>>);
      if (values[5] != null) watches = active(values[5] as List<Map<String, dynamic>>);
      if (values[6] != null) agents = active(values[6] as List<Map<String, dynamic>>);
      if (values[7] != null) agentReports = active(values[7] as List<Map<String, dynamic>>);
      if (values[8] != null) settings = values[8] as Map<String, dynamic>;
      loading = false;
      dashboardLoadError = unreadable.length == values.length
          ? 'No pude acceder al almacenamiento local. Tus registros no se han modificado. '
            'Prueba de nuevo o abre otra pestaña.'
          : '';
      dashboardLoadWarning = unreadable.isEmpty
          ? ''
          : 'No se pudieron leer: ${unreadable.join(', ')}. '
            'Los totales pueden estar incompletos. No se ha borrado ni guardado ningún registro.';
    });

    if (failedKeys.isEmpty && !initialLocalDataReady.isCompleted) {
      initialLocalDataReady.complete();
    }
    if (syncCourier && failedKeys.isEmpty && mounted) {
      unawaited(_refreshCouriersAfterLoad());
    }
  }
'''
s=s[:begin]+new+s[end:]

one(
    "        child: ListView(padding: const EdgeInsets.all(12), children: [\n          Text('Centro de operaciones',",
    """        child: ListView(padding: const EdgeInsets.all(12), children: [
          if (dashboardLoadWarning.isNotEmpty) ...[
            Card(child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Datos locales parcialmente disponibles',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 5),
                Text(dashboardLoadWarning),
                TextButton.icon(
                  onPressed: () => unawaited(load()),
                  icon: const Icon(Icons.refresh),
                  label: const Text('Reintentar leer datos'),
                ),
              ]),
            )),
            const SizedBox(height: 8),
          ],
          Text('Centro de operaciones',""",
    'partial-data warning without masking accessible data',
)

p.write_text(s)
print('Startup v37: lazy tabs, deferred backup and finance I/O, independent local reads, diagnostics.')
