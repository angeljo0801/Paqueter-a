from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# v8 addresses two field reports:
# 1) A Gmail reconstruction that finishes while Paquetería is minimized must be
#    consumed automatically when the package editor resumes (or when the same
#    package is reopened after Android recreated the process).
# 2) Temu recommendation cards such as the Halloween drinking-straw card can
#    contain many "x3" variant labels, causing them to look like order-item rows.
#    Multiple variant quantities + sale pricing are catalog signals, not proof
#    that the image belongs to the purchased item.

# ---------------------------------------------------------------------------
# Background-result availability probe.
# ---------------------------------------------------------------------------
bg_path = Path('app/lib/background_sync.dart')
bs = bg_path.read_text()

reconstruct_anchor = r'''  static Future<Map<String, dynamic>> reconstruct({
'''
has_finished = r'''  static Future<bool> hasFinished({
    String orderNumber = '',
    String tracking = '',
  }) async {
    final order = orderNumber.trim();
    final track = tracking.trim();
    if (order.isEmpty && track.isEmpty) return false;

    final prefs = await SharedPreferences.getInstance();
    await prefs.reload();
    final slot = _slot(order, track);
    final pendingRaw = prefs.getString(_pendingKey(slot));
    if (pendingRaw == null || pendingRaw.isEmpty) return false;

    String token = '';
    try {
      final pending = jsonDecode(pendingRaw);
      if (pending is Map) token = '${pending['token'] ?? ''}';
    } catch (_) {}
    if (token.isEmpty) return false;

    final resultRaw = prefs.getString(_resultKey(slot));
    if (resultRaw == null || resultRaw.isEmpty) return false;
    try {
      final wrapped = jsonDecode(resultRaw);
      return wrapped is Map &&
          '${wrapped['token'] ?? ''}' == token &&
          wrapped['data'] is Map;
    } catch (_) {
      return false;
    }
  }

'''
if 'static Future<bool> hasFinished({' not in bs:
    bs = replace_once(bs, reconstruct_anchor, has_finished + reconstruct_anchor, 'Gmail finished-result probe')
bg_path.write_text(bs)


# ---------------------------------------------------------------------------
# Package editor lifecycle recovery.
# ---------------------------------------------------------------------------
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()

ps = replace_once(
    ps,
    'class _PackageEditPageState extends State<PackageEditPage> {',
    'class _PackageEditPageState extends State<PackageEditPage> with WidgetsBindingObserver {',
    'PackageEditPage lifecycle observer mixin',
)

old_init_state = '  @override\n  void initState() { super.initState(); init(); }\n\n'
new_init_state = r'''  bool _recoveringFinishedGmailSearch = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    init();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      Future<void>.delayed(
        const Duration(milliseconds: 250),
        _recoverFinishedGmailSearch,
      );
    }
  }

  Future<void> _recoverFinishedGmailSearch() async {
    if (!mounted || gmailLoading || _recoveringFinishedGmailSearch) return;
    final track = tracking.text.trim();
    final order = gmailOrder.text.trim();
    if (track.isEmpty && order.isEmpty) return;

    final ready = await GmailBackgroundSearch.hasFinished(
      orderNumber: order,
      tracking: track,
    );
    if (!ready || !mounted) return;

    _recoveringFinishedGmailSearch = true;
    try {
      await reconstructFromGmail();
    } finally {
      _recoveringFinishedGmailSearch = false;
    }
  }

'''
ps = replace_once(ps, old_init_state, new_init_state, 'PackageEditPage init lifecycle hooks')

load_done = "    if (mounted) setState(() => loaded = true);\n"
load_done_new = (
    "    if (mounted) {\n"
    "      setState(() => loaded = true);\n"
    "      await Future<void>.delayed(const Duration(milliseconds: 120));\n"
    "      await _recoverFinishedGmailSearch();\n"
    "    }\n"
)
ps = replace_once(ps, load_done, load_done_new, 'recover Gmail result when package editor opens')
packages_path.write_text(ps)


# ---------------------------------------------------------------------------
# Temu sale/recommendation-card guard.
# ---------------------------------------------------------------------------
helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()
start = hs.find('bool gmailCatalogRecommendationCard(String text) {')
end = hs.find('\n}\n\nbool _gmailUrlClearlyNotProduct', start)
if start < 0 or end < 0:
    raise SystemExit('No se encontró gmailCatalogRecommendationCard para aplicar v8')
end += 2
func = hs[start:end]

money_anchor = r'''  final decimalMoneyCount = RegExp(
    r'(?<!\d)[0-9]{1,5}[\.,][0-9]{2}(?!\d)',
  ).allMatches(lower).length;
'''
money_insert = money_anchor + r'''

  // A recommendation tile can contain a grid of variants (Red x3, Pink x3,
  // Orange x3...) and therefore accidentally trigger the same quantity cue as
  // a real compact order row. Several xN labels inside one image are instead a
  // strong catalog/marketing signal.
  final variantQuantityCount = RegExp(
    r'(?:^|\s)[x×]\s*\d{1,3}\b',
    caseSensitive: false,
  ).allMatches(lower).length;
  final multiVariantGrid = variantQuantityCount >= 3;
  final multiPieceListing = RegExp(
    r'\b\d{2,4}\s*(?:pcs?|pieces)\b',
    caseSensitive: false,
  ).hasMatch(lower);
'''
func = replace_once(func, money_anchor, money_insert, 'Temu variant-grid signals')

old_price_rule = "  if (!orderSignals && (priceCount >= 2 || decimalMoneyCount >= 2)) return true;\n"
new_price_rule = r'''  if (multiVariantGrid && (priceCount >= 1 || decimalMoneyCount >= 1)) {
    return true;
  }
  if ((priceCount >= 2 || decimalMoneyCount >= 2) &&
      (!orderSignals || multiVariantGrid || multiPieceListing)) {
    return true;
  }
'''
func = replace_once(func, old_price_rule, new_price_rule, 'sale-card price rule independent of false xN order signals')

hs = hs[:start] + func + hs[end:]
helper_path.write_text(hs)

print('Gmail v8 applied: completed background searches recover on resume/reopen; Temu multi-variant sale cards are rejected.')
