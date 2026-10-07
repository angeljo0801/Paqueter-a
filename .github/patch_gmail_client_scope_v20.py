from pathlib import Path

def ro(text, old, new, label):
    if old not in text:
        raise SystemExit(f'Missing: {label}')
    return text.replace(old, new, 1)

p = Path('app/lib/background_sync.dart')
s = p.read_text()

# Public reconstruct gains clientId.
s = ro(s,
"""    String tracking = '',
    String packageId = '',
    bool autoAcknowledge = true,
""",
"""    String tracking = '',
    String packageId = '',
    String clientId = '',
    bool autoAcknowledge = true,
""",
'reconstruct clientId')

# Persist/forward clientId wherever packageId is already stored.
s = s.replace(
"          'packageId': packageId.trim(),\n",
"          'packageId': packageId.trim(),\n          'clientId': clientId.trim(),\n",
)
s = s.replace(
"              'packageId': packageId.trim(),\n",
"              'packageId': packageId.trim(),\n              'clientId': clientId.trim(),\n",
)

# Immediate Railway helper.
a = s.index('  static Future<void> _startServerJobNow({')
b = s.index('\n  static Future<Map<String, dynamic>> _serverJobSnapshot({', a)
x = s[a:b]
x = ro(x,
"""    required String tracking,
    required String token,
  }) async {
""",
"""    required String tracking,
    required String token,
    String clientId = '',
  }) async {
""",
'start helper signature')
x = ro(x,
"      'client_token': token,\n",
"      'client_token': token,\n      if (clientId.trim().isNotEmpty) 'client_id': clientId.trim(),\n",
'start helper query')
s = s[:a] + x + s[b:]

# Snapshot helper.
a = s.index('  static Future<Map<String, dynamic>> _serverJobSnapshot({')
b = s.index('\n  static Future<void> _scheduleServerCollector({', a)
x = s[a:b]
x = ro(x,
"""    required String tracking,
    required String token,
  }) async {
""",
"""    required String tracking,
    required String token,
    String clientId = '',
  }) async {
""",
'snapshot signature')
x = ro(x,
"      'client_token': token,\n",
"      'client_token': token,\n      if (clientId.trim().isNotEmpty) 'client_id': clientId.trim(),\n",
'snapshot query')
s = s[:a] + x + s[b:]

# Foreground server job helper.
a = s.index('  static Future<Map<String, dynamic>> _requestServerJob({')
b = s.index('\n  static List<Map<String, dynamic>> _backgroundPhotoCandidates(', a)
x = s[a:b]
x = ro(x,
"""    required String tracking,
    required String token,
  }) async {
""",
"""    required String tracking,
    required String token,
    String clientId = '',
  }) async {
""",
'server job signature')
x = ro(x,
"      'client_token': token,\n",
"      'client_token': token,\n      if (clientId.trim().isNotEmpty) 'client_id': clientId.trim(),\n",
'server job query')
s = s[:a] + x + s[b:]

# Collector persists the client scope.
a = s.index('  static Future<void> _scheduleServerCollector({')
b = s.index('\n  static Future<bool> _finishBackgroundSnapshot({', a)
x = s[a:b]
x = ro(x,
"""    required String tracking,
    required String packageId,
    required int attempt,
""",
"""    required String tracking,
    required String packageId,
    String clientId = '',
    required int attempt,
""",
'collector signature')
x = ro(x,
"        'packageId': packageId,\n        'attempt': attempt,\n",
"        'packageId': packageId,\n        'clientId': clientId,\n        'attempt': attempt,\n",
'collector data')
s = s[:a] + x + s[b:]

# Every main/collector worker reads clientId.
s = s.replace(
"    final packageId = '${data['packageId'] ?? ''}';\n",
"    final packageId = '${data['packageId'] ?? ''}';\n    final clientId = '${data['clientId'] ?? ''}';\n",
)

# Propagate to snapshot and collector calls.
s = s.replace(
"        token: token,\n      );\n      final status =",
"        token: token,\n        clientId: clientId,\n      );\n      final status =",
)
s = s.replace(
"        packageId: packageId,\n        attempt:",
"        packageId: packageId,\n        clientId: clientId,\n        attempt:",
)
s = s.replace(
"          packageId: packageId,\n          attempt:",
"          packageId: packageId,\n          clientId: clientId,\n          attempt:",
)

# Foreground reconstruct calls both helpers with clientId.
a = s.index('  static Future<Map<String, dynamic>> reconstruct({')
b = s.find('\n  static String _upgradeKey(', a)
if b < 0:
    b = s.index("\n  @pragma('vm:entry-point')\n  static Future<bool> execute(", a)
x = s[a:b]
x = x.replace(
"          token: token,\n        );",
"          token: token,\n          clientId: clientId,\n        );",
)
s = s[:a] + x + s[b:]

p.write_text(s)

# Package editor supplies the selected client.
p = Path('app/lib/packages.dart')
s = p.read_text()
s = ro(s,
"""        packageId: '${widget.existing?['id'] ?? ''}',
        autoAcknowledge: false,
""",
"""        packageId: '${widget.existing?['id'] ?? ''}',
        clientId: clientId ?? '',
        autoAcknowledge: false,
""",
'package client Gmail scope')
p.write_text(s)

print('Client-scoped Gmail reconstruction applied.')
