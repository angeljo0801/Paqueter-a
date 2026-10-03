from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontro bloque esperado: {label}')
    return text.replace(old, new, 1)


# Shared helpers for keeping search text even when the page/app is reopened.
main = Path('app/lib/main.dart')
s = main.read_text()
marker = "List<dynamic> dynList(dynamic v) => v is List ? v : const [];\n\n"
helper = """List<dynamic> dynList(dynamic v) => v is List ? v : const [];

const String _searchStatePrefix = 'ui_search_';

Future<String> readPersistentSearch(String key) async {
  final prefs = await SharedPreferences.getInstance();
  return prefs.getString('$_searchStatePrefix$key') ?? '';
}

Future<void> writePersistentSearch(String key, String value) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString('$_searchStatePrefix$key', value);
}

"""
s = replace_once(s, marker, helper, 'helpers de busqueda')
main.write_text(s)


# CLIENTS: keep search, load packages too, and show total billable pounds per client.
clients = Path('app/lib/clients.dart')
s = clients.read_text()
start = s.index('class _ClientsPageState extends State<ClientsPage> {')
end = s.index('class ClientEditPage', start)
seg = s[start:end]

old = """class _ClientsPageState extends State<ClientsPage> {
  List<Map<String, dynamic>> rows = [], purchases = [], payments = [];
  String q = '';
  bool importing = false;
  bool syncing = false;
  bool backgroundSyncing = false;

  @override
  void initState() {
    super.initState();
    load();
  }
"""
new = """class _ClientsPageState extends State<ClientsPage> {
  List<Map<String, dynamic>> rows = [], purchases = [], payments = [], packages = [];
  final search = TextEditingController();
  String q = '';
  bool importing = false;
  bool syncing = false;
  bool backgroundSyncing = false;

  @override
  void initState() {
    super.initState();
    _restoreSearch();
    load();
  }

  @override
  void dispose() {
    search.dispose();
    super.dispose();
  }

  Future<void> _restoreSearch() async {
    final saved = await readPersistentSearch('clients');
    if (!mounted) return;
    search.text = saved;
    setState(() => q = saved);
  }
"""
seg = replace_once(seg, old, new, 'estado ClientsPage')

# Both local-first loads (initial and refresh) must include packages.
seg = seg.replace(
    "      Store.list('payments'),\n    ]);",
    "      Store.list('payments'),\n      Store.list('packages'),\n    ]);",
)
seg = seg.replace(
    "      payments = active(r[2]);\n",
    "      payments = active(r[2]);\n      packages = active(r[3]);\n",
)

old = """            child: TextField(
              onChanged: (v) => setState(() => q = v),
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Buscar cliente',
              ),
            ),
"""
new = """            child: TextField(
              controller: search,
              onChanged: (v) {
                setState(() => q = v);
                unawaited(writePersistentSearch('clients', v));
              },
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Buscar cliente',
              ),
            ),
"""
seg = replace_once(seg, old, new, 'buscador ClientesPage')

old = """                      final due = clientDue(
                        '${c['id']}',
                        purchases,
                        payments,
                      );
"""
new = """                      final due = clientDue(
                        '${c['id']}',
                        purchases,
                        payments,
                      );
                      final totalLb = packages
                          .where((p) => '${p['clientId'] ?? ''}' == '${c['id']}')
                          .fold<double>(
                            0,
                            (sum, p) => sum + number(p['billWeight']),
                          );
"""
seg = replace_once(seg, old, new, 'calculo de libras por cliente')

old = """                        subtitle: Text(
                          '${contactLine.isEmpty ? 'Sin teléfono' : contactLine}\\nPendiente: ${money(due)}',
                        ),
                        isThreeLine: true,
"""
new = """                        subtitle: Text(
                          '${contactLine.isEmpty ? 'Sin teléfono' : contactLine}\\nPendiente: ${money(due)}\\nLibras: ${totalLb.toStringAsFixed(1)} lb',
                        ),
                        isThreeLine: true,
"""
seg = replace_once(seg, old, new, 'texto de libras por cliente')
s = s[:start] + seg + s[end:]

# Also keep the temporary contact-import search, since it is a search field in the app.
start = s.index('class _ContactImportPageState extends State<ContactImportPage> {')
end = s.index('class ClientsPage', start)
seg = s[start:end]
seg = replace_once(
    seg,
    """  final selected = <String>{};
  String q = '';

  String _key(Contact c, int index) =>
""",
    """  final selected = <String>{};
  final search = TextEditingController();
  String q = '';

  @override
  void initState() {
    super.initState();
    _restoreSearch();
  }

  @override
  void dispose() {
    search.dispose();
    super.dispose();
  }

  Future<void> _restoreSearch() async {
    final saved = await readPersistentSearch('contact_import');
    if (!mounted) return;
    search.text = saved;
    setState(() => q = saved);
  }

  String _key(Contact c, int index) =>
""",
    'estado buscador importar contactos',
)
seg = replace_once(
    seg,
    """            child: TextField(
              onChanged: (v) => setState(() => q = v),
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Buscar en tus contactos',
              ),
            ),
""",
    """            child: TextField(
              controller: search,
              onChanged: (v) {
                setState(() => q = v);
                unawaited(writePersistentSearch('contact_import', v));
              },
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Buscar en tus contactos',
              ),
            ),
""",
    'buscador importar contactos',
)
s = s[:start] + seg + s[end:]
clients.write_text(s)


# PACKAGES: persistent search text.
packages = Path('app/lib/packages.dart')
s = packages.read_text()
s = replace_once(
    s,
    """class _PackagesPageState extends State<PackagesPage> {
  List<Map<String, dynamic>> rows = [], clients = [];
  String q = '';
  @override
  void initState() { super.initState(); load(); }
""",
    """class _PackagesPageState extends State<PackagesPage> {
  List<Map<String, dynamic>> rows = [], clients = [];
  final search = TextEditingController();
  String q = '';
  @override
  void initState() {
    super.initState();
    _restoreSearch();
    load();
  }

  @override
  void dispose() {
    search.dispose();
    super.dispose();
  }

  Future<void> _restoreSearch() async {
    final saved = await readPersistentSearch('packages');
    if (!mounted) return;
    search.text = saved;
    setState(() => q = saved);
  }
""",
    'estado PackagesPage',
)
s = replace_once(
    s,
    """          child: TextField(
            onChanged: (v) => setState(() => q = v),
            decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Tracking o nombre del cliente'),
          ),
""",
    """          child: TextField(
            controller: search,
            onChanged: (v) {
              setState(() => q = v);
              unawaited(writePersistentSearch('packages', v));
            },
            decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Tracking o nombre del cliente'),
          ),
""",
    'buscador PackagesPage',
)
packages.write_text(s)


# PURCHASES: persistent search text, including explicit clear.
purchases = Path('app/lib/purchases.dart')
s = purchases.read_text()
s = replace_once(
    s,
    """  @override
  void initState() { super.initState(); load(); }
""",
    """  @override
  void initState() {
    super.initState();
    _restoreSearch();
    load();
  }

  Future<void> _restoreSearch() async {
    final saved = await readPersistentSearch('purchases');
    if (!mounted) return;
    search.text = saved;
    setState(() => q = saved);
  }
""",
    'init PurchasesPage',
)
s = replace_once(
    s,
    """              onChanged: (v) => setState(() => q = v),
""",
    """              onChanged: (v) {
                setState(() => q = v);
                unawaited(writePersistentSearch('purchases', v));
              },
""",
    'onChanged PurchasesPage',
)
s = replace_once(
    s,
    """                        onPressed: () {
                          search.clear();
                          setState(() => q = '');
                        },
""",
    """                        onPressed: () {
                          search.clear();
                          setState(() => q = '');
                          unawaited(writePersistentSearch('purchases', ''));
                        },
""",
    'limpiar PurchasesPage',
)
purchases.write_text(s)


# AGENTS: persistent search text.
agents = Path('app/lib/agents.dart')
s = agents.read_text()
s = replace_once(
    s,
    """  List<Map<String, dynamic>> agents = [], reports = [];
  bool importing = false;
  String q = '';

  @override
  void initState() {
    super.initState();
    load();
  }
""",
    """  List<Map<String, dynamic>> agents = [], reports = [];
  final search = TextEditingController();
  bool importing = false;
  String q = '';

  @override
  void initState() {
    super.initState();
    _restoreSearch();
    load();
  }

  @override
  void dispose() {
    search.dispose();
    super.dispose();
  }

  Future<void> _restoreSearch() async {
    final saved = await readPersistentSearch('agents');
    if (!mounted) return;
    search.text = saved;
    setState(() => q = saved);
  }
""",
    'estado AgentsPage',
)
s = replace_once(
    s,
    """          child: TextField(
            onChanged: (v) => setState(() => q = v),
            decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Buscar agente'),
          ),
""",
    """          child: TextField(
            controller: search,
            onChanged: (v) {
              setState(() => q = v);
              unawaited(writePersistentSearch('agents', v));
            },
            decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Buscar agente'),
          ),
""",
    'buscador AgentsPage',
)
agents.write_text(s)


# GLOBAL BUSINESS SEARCH: persistent search text.
search_file = Path('app/lib/search.dart')
if search_file.exists():
    s = search_file.read_text()
    s = replace_once(
        s,
        """  @override
  void initState() {
    super.initState();
    load();
  }
""",
        """  @override
  void initState() {
    super.initState();
    _restoreSearch();
    load();
  }

  @override
  void dispose() {
    q.dispose();
    super.dispose();
  }

  Future<void> _restoreSearch() async {
    final saved = await readPersistentSearch('global');
    if (!mounted) return;
    q.text = saved;
    setState(() {});
  }
""",
        'init BusinessSearchPage',
    )
    s = replace_once(
        s,
        """                  onChanged: (_) => setState(() {}),
""",
        """                  onChanged: (value) {
                    setState(() {});
                    unawaited(writePersistentSearch('global', value));
                  },
""",
        'onChanged BusinessSearchPage',
    )
    s = replace_once(
        s,
        """                        : IconButton(icon: const Icon(Icons.clear), onPressed: () => setState(q.clear)),
""",
        """                        : IconButton(
                            icon: const Icon(Icons.clear),
                            onPressed: () {
                              q.clear();
                              setState(() {});
                              unawaited(writePersistentSearch('global', ''));
                            },
                          ),
""",
        'limpiar BusinessSearchPage',
    )
    search_file.write_text(s)

print('Persistent search + client pounds patch applied.')
