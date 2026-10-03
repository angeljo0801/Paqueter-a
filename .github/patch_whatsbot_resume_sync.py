from pathlib import Path

# 1) Make APP_API_KEY reads safe and single-flight so a blocked Android
# keystore read cannot freeze every sync call.
sync = Path('app/lib/whatsbot_sync.dart')
s = sync.read_text()
old = """  static Future<String> apiKey() async =>
      (await _secure.read(key: _apiKeyName) ?? '').trim();

  static Future<void> saveApiKey(String value) async {
    final key = value.trim();
    if (key.isEmpty) {
      await _secure.delete(key: _apiKeyName);
    } else {
      await _secure.write(key: _apiKeyName, value: key);
    }
  }
"""
new = """  static String _cachedApiKey = '';
  static Future<String>? _apiKeyReadInFlight;

  static Future<String> apiKey() async {
    if (_cachedApiKey.isNotEmpty) return _cachedApiKey;
    final existing = _apiKeyReadInFlight;
    if (existing != null) return existing;

    final future = _readApiKeySafe();
    _apiKeyReadInFlight = future;
    try {
      return await future;
    } finally {
      if (identical(_apiKeyReadInFlight, future)) {
        _apiKeyReadInFlight = null;
      }
    }
  }

  static Future<String> _readApiKeySafe() async {
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        final raw = await _secure
            .read(key: _apiKeyName)
            .timeout(const Duration(seconds: 4));
        final key = (raw ?? '').trim();
        if (key.isNotEmpty) _cachedApiKey = key;
        return key;
      } catch (_) {
        if (attempt == 0) {
          await Future<void>.delayed(const Duration(milliseconds: 350));
        }
      }
    }
    return _cachedApiKey;
  }

  static Future<void> saveApiKey(String value) async {
    final key = value.trim();
    _cachedApiKey = key;
    try {
      if (key.isEmpty) {
        await _secure
            .delete(key: _apiKeyName)
            .timeout(const Duration(seconds: 4));
      } else {
        await _secure
            .write(key: _apiKeyName, value: key)
            .timeout(const Duration(seconds: 4));
      }
    } catch (_) {
      // Keep the in-memory value so the current session can still sync.
    }
  }
"""
if old not in s:
    raise SystemExit('apiKey/saveApiKey block not found')
s = s.replace(old, new, 1)
sync.write_text(s)

# 2) When the user returns from WhatsBot, immediately pull purchases from
# Railway. Recreate the tab pages after the pull so the freshly imported data
# is visible without forcing the user to close/reopen Paqueteria.
main = Path('app/lib/main.dart')
m = main.read_text()
old_home = """class _HomeShellState extends State<HomeShell> {
  int index = 0;
  final pages = const [DashboardPage(), ClientsPage(), PackagesPage(), TripsPage(), MorePage()];
  @override
  Widget build(BuildContext context) {
"""
new_home = """class _HomeShellState extends State<HomeShell> with WidgetsBindingObserver {
  int index = 0;
  List<Widget> pages = const [DashboardPage(), ClientsPage(), PackagesPage(), TripsPage(), MorePage()];
  bool _resumeSyncing = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_syncWhatsBotAfterResume());
    }
  }

  Future<void> _syncWhatsBotAfterResume() async {
    if (_resumeSyncing) return;
    _resumeSyncing = true;
    try {
      await WhatsBotPurchaseSyncService.syncSilently()
          .timeout(const Duration(seconds: 60));
      if (!mounted) return;
      setState(() {
        pages = [
          DashboardPage(key: UniqueKey()),
          ClientsPage(key: UniqueKey()),
          PackagesPage(key: UniqueKey()),
          TripsPage(key: UniqueKey()),
          MorePage(key: UniqueKey()),
        ];
      });
    } catch (_) {
      // A failed background refresh must never block navigation.
    } finally {
      _resumeSyncing = false;
    }
  }

  @override
  Widget build(BuildContext context) {
"""
if old_home not in m:
    raise SystemExit('HomeShell block not found')
m = m.replace(old_home, new_home, 1)
main.write_text(m)
