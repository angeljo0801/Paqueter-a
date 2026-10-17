from pathlib import Path

p = Path('app/lib/main.dart')
s = p.read_text()

old = """  bool courierSyncing = false;
  List<Map<String, dynamic>> clients = [], purchases = [], packages = [], trips = [], payments = [], watches = [], agents = [], agentReports = [];
  Map<String, dynamic> settings = {};

  @override
  void initState() {
    super.initState();
    load(syncCourier: true);
  }

  Future<void> load({bool syncCourier = false}) async {
    if (syncCourier) {
      if (mounted) setState(() => courierSyncing = true);
      await EasyPostService.syncAll();
      if (mounted) setState(() => courierSyncing = false);
    }
    final r = await Future.wait(["""
new = """  bool courierSyncing = false;
  String dashboardLoadError = '';
  List<Map<String, dynamic>> clients = [], purchases = [], packages = [], trips = [], payments = [], watches = [], agents = [], agentReports = [];
  Map<String, dynamic> settings = {};

  @override
  void initState() {
    super.initState();
    // Render local data before calling any courier or network service.
    load(syncCourier: true);
  }

  Future<void> _refreshCouriersAfterLoad() async {
    if (courierSyncing || !mounted) return;
    setState(() => courierSyncing = true);
    try {
      await EasyPostService.syncAll();
    } catch (_) {
      // Failure of EasyPost must never prevent the dashboard from opening.
    } finally {
      if (mounted) {
        setState(() => courierSyncing = false);
        await load(); // Refresh local dashboard data only, never restart sync.
      }
    }
  }

  Future<void> load({bool syncCourier = false}) async {
    try {
      final r = await Future.wait(["""
if s.count(old) != 1:
    raise SystemExit('Startup patch: dashboard loading anchor changed')
s=s.replace(old,new)
old2="""      Store.settings(),
    ]);
    if (!mounted) return;
    setState(() {
      clients = active(r[0] as List<Map<String, dynamic>>);"""
new2="""      Store.settings(),
      ]).timeout(const Duration(seconds: 12));
      if (!mounted) return;
      setState(() {
        dashboardLoadError = '';
        clients = active(r[0] as List<Map<String, dynamic>>);"""
if s.count(old2)!=1: raise SystemExit('Startup patch: local-data load anchor changed')
s=s.replace(old2,new2)
old3="""      settings = r[8] as Map<String, dynamic>;
      loading = false;
    });
  }

  Future<void> openCourier() async {"""
new3="""        settings = r[8] as Map<String, dynamic>;
        loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        loading = false;
        dashboardLoadError = 'No pude cargar los datos locales. Puedes reintentar sin borrar tus registros.';
      });
    }
    if (syncCourier && mounted && dashboardLoadError.isEmpty) {
      unawaited(_refreshCouriersAfterLoad());
    }
  }

  Future<void> openCourier() async {"""
if s.count(old3)!=1: raise SystemExit('Startup patch: end of local data load changed')
s=s.replace(old3,new3)
old4="""    if (loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    final pendingPurchases = purchases.where((e) => e['status'] == 'Pendiente de comprar').length;"""
new4="""    if (loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (dashboardLoadError.isNotEmpty) {
      return Scaffold(
        appBar: AppBar(title: const Text('Paquetería')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.warning_amber_rounded, size: 48),
                const SizedBox(height: 12),
                Text(dashboardLoadError, textAlign: TextAlign.center),
                const SizedBox(height: 16),
                FilledButton.icon(
                  onPressed: () {
                    setState(() => loading = true);
                    unawaited(load());
                  },
                  icon: const Icon(Icons.refresh),
                  label: const Text('Reintentar cargar mis datos'),
                ),
                const SizedBox(height: 8),
                const Text('Tus datos no han sido borrados.',
                    textAlign: TextAlign.center),
              ],
            ),
          ),
        ),
      );
    }
    final pendingPurchases = purchases.where((e) => e['status'] == 'Pendiente de comprar').length;"""
if s.count(old4)!=1: raise SystemExit('Startup patch: loading indicator changed')
s=s.replace(old4,new4)
p.write_text(s)
print('Startup v36: local-first dashboard, EasyPost non-blocking, error/retry instead of infinite spinner.')
