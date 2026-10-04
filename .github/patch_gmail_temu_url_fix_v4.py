from pathlib import Path

p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()

old = r'''bool _gmailUrlClearlyNotProduct(String url) {
  final lower = url.toLowerCase();
  const blocked = <String>[
    'logo', 'icon', 'sprite', 'pixel', 'beacon', 'tracking', 'spacer',
    'header', 'footer', 'social', 'facebook', 'instagram', 'tiktok',
    'youtube', 'twitter', 'appstore', 'googleplay', 'play-store',
    'badge', 'avatar', 'separator', 'divider', 'marketing-banner',
    'promo-banner', 'email-banner', 'newsletter-banner',
  ];
  return blocked.any(lower.contains);
}'''

new = r'''bool _gmailUrlClearlyNotProduct(String url) {
  final lower = url.toLowerCase();
  // v4: Temu and other stores may use logo/banner/icon in the CDN path of a
  // genuine product photo. Those words are therefore NOT safe reject signals.
  // Keep only infrastructure/social assets that are overwhelmingly non-product.
  const blocked = <String>[
    'sprite', 'pixel', 'beacon', 'tracking-pixel', 'spacer',
    'facebook', 'instagram', 'tiktok', 'youtube', 'twitter',
    'appstore', 'googleplay', 'play-store',
    'separator', 'divider',
  ];
  return blocked.any(lower.contains);
}'''

if old not in s:
    raise SystemExit('No se encontró _gmailUrlClearlyNotProduct esperado para v4')
s = s.replace(old, new, 1)
p.write_text(s)
print('Gmail/Temu photo filter v4 applied: logo/banner/icon URL words no longer auto-reject product photos.')
