from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Missing expected block: {label}')
    return text.replace(old, new, 1)


p = Path('app/lib/packages.dart')
s = p.read_text()

start = s.find('  Future<void> reconstructFromGmail() async {')
end = s.find('\n  Future<void> openEmailPhoto(', start)
if start < 0 or end < 0:
    raise SystemExit('Could not locate reconstructFromGmail')
method = s[start:end]

old = r'''      if (data['found'] != true) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('No encontré correos para ese tracking u orden.')),
          );
        }
        return;
      }
'''

new = r'''      if (data['found'] != true) {
        // "Not found" is a terminal result, not a pending job. Package searches
        // intentionally use autoAcknowledge:false so successful photo results
        // remain durable until persisted. That same behavior previously left a
        // no-result payload in SharedPreferences forever, causing the resume
        // watcher to reopen the exact same finished search again and again.
        _gmailRecoveryPoll?.cancel();
        await GmailBackgroundSearch.acknowledgeFinished(
          orderNumber: order,
          tracking: track,
        );
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'No encontré correos para ese tracking u orden. La búsqueda terminó.',
              ),
            ),
          );
        }
        return;
      }
'''

method = replace_once(method, old, new, 'terminal Gmail not-found handling')
s = s[:start] + method + s[end:]
p.write_text(s)

print('Gmail v22 applied: no-result searches are acknowledged once and never auto-restarted.')
