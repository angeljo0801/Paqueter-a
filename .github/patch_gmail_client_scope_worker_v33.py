from pathlib import Path

p = Path('app/lib/background_sync.dart')
s = p.read_text()

def ensure_scoped_call(text: str, call: str, label: str) -> str:
    start = text.find(call)
    if start < 0:
        raise SystemExit('Gmail v33 missing call: ' + label)
    end = text.find(');', start)
    if end < 0:
        raise SystemExit('Gmail v33 unterminated call: ' + label)
    end += 2
    snippet = text[start:end]
    if 'clientId:' not in snippet:
        if snippet.count('token: token,') != 1:
            raise SystemExit('Gmail v33 missing token in: ' + label)
        snippet = snippet.replace('token: token,', 'token: token,\n        clientId: clientId,', 1)
        text = text[:start] + snippet + text[end:]
    return text


# Both WorkManager entry points must use the same client as the package editor.
for marker in [
    'static Future<bool> execute(Map<String, dynamic>? inputData)',
    'static Future<bool> collectServerJob(Map<String, dynamic>? inputData)',
]:
    a = s.find(marker)
    if a < 0:
        raise SystemExit('Gmail v33 missing worker ' + marker)
    b = s.find('  @pragma(', a + len(marker))
    if b < 0:
        b = s.find('\n}\n\nclass NotificationService', a)
    if b < 0:
        raise SystemExit('Gmail v33 missing worker end ' + marker)
    body = s[a:b]
    client_local = "final clientId = '${data['clientId'] ?? ''}';"
    if client_local not in body:
        package_local = "final packageId = '${data['packageId'] ?? ''}';"
        if package_local not in body:
            raise SystemExit('Gmail v33 missing package context')
        body = body.replace(package_local, package_local + '\n    ' + client_local, 1)
    body = ensure_scoped_call(body, 'final snapshot = await _serverJobSnapshot(', marker)
    # Scheduled collector tasks must retain clientId on every retry.
    key = 'await _scheduleServerCollector('
    pos = 0
    while True:
        i = body.find(key, pos)
        if i < 0:
            break
        j = body.find(');', i)
        if j < 0:
            raise SystemExit('Gmail v33 invalid collector')
        original = body[i:j+2]
        if 'clientId:' not in original:
            if original.count('packageId: packageId,') != 1:
                raise SystemExit('Gmail v33 expected package in collector')
            updated = original.replace('packageId: packageId,',
                'packageId: packageId,\n          clientId: clientId,', 1)
            body = body[:i] + updated + body[j+2:]
            pos = i + len(updated)
        else:
            pos = j + 2
    s = s[:a] + body + s[b:]

# Foreground joins the exact same scoped job started by the tapping action.
a = s.index('static Future<Map<String, dynamic>> reconstruct({')
b = s.find('\n  static String _upgradeKey(', a)
if b < 0:
    b = s.find("\n  @pragma('vm:entry-point')", a)
if b < 0:
    raise SystemExit('Gmail v33 missing reconstruction boundary')
block = s[a:b]
for call in ('await _startServerJobNow(', 'await _requestServerJob('):
    if call in block:
        block = ensure_scoped_call(block, call, call)
s = s[:a] + block + s[b:]

if 'Gmail v33 scope verified' not in s:
    s = s.replace('  static Future<Map<String, dynamic>> reconstruct({',
        '  // Gmail v33 scope verified across foreground and WorkManager.\n'
        '  static Future<Map<String, dynamic>> reconstruct({', 1)
p.write_text(s)
print('Gmail v33: foreground, WorkManager and collector requests keep the client scope.')
