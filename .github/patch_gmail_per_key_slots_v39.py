from pathlib import Path
import re

p = Path('app/lib/main.dart')
s = p.read_text()
anchor = "  static Future<void> _writeRaw(String key, String value) async {"
if s.count(anchor) != 1:
    raise SystemExit('Gmail v39: native per-key writer not found')
code = r'''  static Future<void> _removeRaw(String key) async {
    if (Platform.isAndroid) {
      try {
        final removed = await _perKeyStore.invokeMethod<bool>(
          'removeKey', {'key': 'flutter.$key'},
        ).timeout(const Duration(seconds: 15));
        if (removed != true) throw StateError('No pude actualizar $key.');
        return;
      } on MissingPluginException {
        // Non-activity Flutter engines still use the legacy plugin.
      }
    }
    final legacy = await SharedPreferences.getInstance();
    if (!await legacy.remove(key)) {
      throw StateError('No pude actualizar $key.');
    }
  }

'''
s=s.replace(anchor,code+anchor,1)
p.write_text(s)

p=Path('app/android/app/src/main/kotlin/com/angelapps/paqueteria/PaqueteriaLocalStoreBridge.kt')
s=p.read_text()
anchor='''                    "writeString" -> {'''
if s.count(anchor)!=1: raise SystemExit('Gmail v39: native writes not found')
code='''                    "removeKey" -> {
                        val key = call.argument<String>("key") ?: ""
                        if (!key.startsWith("flutter.")) {
                            result.error("INVALID_KEY", "Invalid preference key.", null)
                        } else if (prefs.edit().remove(key).commit()) {
                            result.success(true)
                        } else {
                            result.error("REMOVE_FAILED", "Could not update preference.", null)
                        }
                    }
'''
s=s.replace(anchor,code+anchor,1)
p.write_text(s)

p = Path('app/lib/background_sync.dart')
s = p.read_text()
anchor = "class GmailBackgroundSearch {"
if s.count(anchor) != 1: raise SystemExit('Gmail v39: GmailBackgroundSearch changed')
shim = r'''// Gmail lookup state must not initialize the entire legacy preference map.
// That all-keys transfer can fail once packages contain many offline photos.
// This reads only the three keys for the requested tracking through the v38
// native per-key bridge, retaining compatibility with background FlutterEngine.
class _GmailPreferenceView {
  final String slot;
  final Map<String, String?> _cache = <String, String?>{};
  _GmailPreferenceView(this.slot);

  static Future<_GmailPreferenceView> open(String slot) async {
    final view = _GmailPreferenceView(slot);
    await view.reload();
    return view;
  }

  Future<void> reload() async {
    final keys = <String>[
      GmailBackgroundSearch._pendingKey(slot),
      GmailBackgroundSearch._resultKey(slot),
      GmailBackgroundSearch._errorKey(slot),
    ];
    for (final key in keys) {
      _cache[key] = await Store._readRaw(key);
    }
  }

  String? getString(String key) => _cache[key];

  Future<bool> setString(String key, String value) async {
    await Store._writeRaw(key, value);
    _cache[key] = value;
    return true;
  }

  Future<bool> remove(String key) async {
    await Store._removeRaw(key);
    _cache[key] = null;
    return true;
  }
}

'''
s=s.replace(anchor,shim+anchor,1)
start=s.index('class GmailBackgroundSearch {')
end=s.index('\nclass NotificationService',start)
body=s[start:end]
expected='    final prefs = await SharedPreferences.getInstance();'
number=body.count(expected)
if number < 6 or number > 14:
    raise SystemExit(f'Gmail v39: unexpected legacy Gmail init calls: {number}')

old='''    final prefs = await SharedPreferences.getInstance();
    final slot = _slot(order, track);
    final pendingKey = _pendingKey(slot);'''
new='''    final slot = _slot(order, track);
    final prefs = await _GmailPreferenceView.open(slot);
    final pendingKey = _pendingKey(slot);'''
if body.count(old)!=1: raise SystemExit('Gmail v39: reconstruct slot block mismatch')
body=body.replace(old,new,1)

old='''    final prefs = await SharedPreferences.getInstance();
    await prefs.reload();
    final slot = _slot(order, track);'''
new='''    final slot = _slot(order, track);
    final prefs = await _GmailPreferenceView.open(slot);
    await prefs.reload();'''
count=body.count(old)
if count!=2:
    raise SystemExit(f'Gmail v39: expected 2 poll/acknowledge blocks, got {count}')
body=body.replace(old,new)

if 'SharedPreferences prefs,' not in body:
    raise SystemExit('Gmail v39: finished-result helper signature not found')
body=body.replace('SharedPreferences prefs,','_GmailPreferenceView prefs,')
# Only the slot-specific methods have a slot variable. The photo/cache
# routines deliberately retain their own preferences object until migrated
# separately, so their package accesses are never mistaken for Gmail keys.
slot_methods = [
    '_finishBackgroundSnapshot', '_persistBackgroundError',
    'execute', 'collectServerJob',
]
for method_name in slot_methods:
    signature = re.search(
        r'  static Future<.*> ' + method_name + r'\(', body,
    )
    if signature is None:
        raise SystemExit('Gmail v39: missing slot method ' + method_name)
    lo = signature.start()
    starts = [
        i for i in [
            body.find('\n  static ', lo + 8),
            body.find('\n  @pragma(', lo + 8),
        ] if i >= 0
    ]
    hi = min(starts) if starts else len(body)
    block = body[lo:hi]
    if block.count(expected) != 1:
        raise SystemExit('Gmail v39: unexpected prefs init in ' + method_name)
    block = block.replace(expected, '    final prefs = await _GmailPreferenceView.open(slot);', 1)
    body = body[:lo] + block + body[hi:]

if body.count(expected) > 3:
    raise SystemExit('Gmail v39: unexpected unconverted preferences accesses')
s=s[:start]+body+s[end:]
p.write_text(s)
print(f'Gmail v39: migrated {number} Gmail lookup preference usages to native per-key reads.')
