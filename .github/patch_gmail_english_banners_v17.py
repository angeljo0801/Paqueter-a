from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# v17: hard-reject the exact English utility/promotional banners reported by
# the user: shipment progress and BONUS POINTS. These must lose even if another
# heuristic accidentally sees them as an order row.
p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()

anchor = r'''  final spanishTrackingHelpUi =
      lower.contains('¿quieres rastrear tu paquete?') ||
      lower.contains('quieres rastrear tu paquete') ||
      (lower.contains('añade el widget') &&
          lower.contains('seguimiento del pedido')) ||
      (lower.contains('anade el widget') &&
          lower.contains('seguimiento del pedido')) ||
      (lower.contains('guía de instalación') &&
          lower.contains('seguimiento del pedido')) ||
      (lower.contains('guia de instalacion') &&
          lower.contains('seguimiento del pedido'));

  final carrierTrackingUi =
'''

insert = r'''  final spanishTrackingHelpUi =
      lower.contains('¿quieres rastrear tu paquete?') ||
      lower.contains('quieres rastrear tu paquete') ||
      (lower.contains('añade el widget') &&
          lower.contains('seguimiento del pedido')) ||
      (lower.contains('anade el widget') &&
          lower.contains('seguimiento del pedido')) ||
      (lower.contains('guía de instalación') &&
          lower.contains('seguimiento del pedido')) ||
      (lower.contains('guia de instalacion') &&
          lower.contains('seguimiento del pedido'));

  // English shipment-progress strip seen in Temu/SHEIN email artwork:
  // Order Confirmed -> Shipped -> Delivering -> Delivered -> View more.
  // OCR can miss one label, so combinations are intentionally redundant.
  final englishShipmentUi =
      (lower.contains('order confirmed') &&
          (lower.contains('shipped') ||
              lower.contains('delivering') ||
              lower.contains('delivered'))) ||
      (lower.contains('shipped') &&
          lower.contains('delivering') &&
          lower.contains('delivered')) ||
      (lower.contains('view more') &&
          (lower.contains('delivering') || lower.contains('delivered'))) ||
      (lower.contains('order confirmed') && lower.contains('view more'));

  // Loyalty/reward artwork is promotional UI, never a purchased product.
  final englishLoyaltyUi =
      RegExp(r'\bbonus\s+points?\b', caseSensitive: false).hasMatch(lower) ||
      RegExp(r'\breward\s+points?\b', caseSensitive: false).hasMatch(lower) ||
      RegExp(r'\bloyalty\s+points?\b', caseSensitive: false).hasMatch(lower);

  final carrierTrackingUi =
'''

s = replace_once(s, anchor, insert, 'English shipment and loyalty banner signals')

old = r'''  if (statusOrLogisticsUi ||
      paymentSafetyUi ||
      carrierTrackingUi ||
      spanishShipmentUi ||
      spanishLoyaltyUi ||
      spanishTrackingHelpUi) {
    return true;
  }
'''

new = r'''  if (statusOrLogisticsUi ||
      paymentSafetyUi ||
      carrierTrackingUi ||
      spanishShipmentUi ||
      spanishLoyaltyUi ||
      spanishTrackingHelpUi ||
      englishShipmentUi ||
      englishLoyaltyUi) {
    return true;
  }
'''

s = replace_once(s, old, new, 'hard reject English utility banners')
p.write_text(s)

print('Gmail v17 applied: English shipment-progress and BONUS/REWARD/LOYALTY POINTS banners are hard rejected.')
