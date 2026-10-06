from pathlib import Path

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)

p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()

# v11: Spanish/Temu UI cards observed in production must never be treated as
# product photos. These are status, loyalty, help or tracking banners.
needle = """  final paymentSafetyUi = <String>[
    'safe payments',
    'payment information is safe',
    'credit card information',
    'does not share your credit card',
    'secure payment',
    'payment protection',
    'learn more',
  ].any(lower.contains);

  final carrierTrackingUi =
"""

insert = """  final paymentSafetyUi = <String>[
    'safe payments',
    'payment information is safe',
    'credit card information',
    'does not share your credit card',
    'secure payment',
    'payment protection',
    'learn more',
  ].any(lower.contains);

  // Spanish UI/status/promotional cards seen in Temu/SHEIN emails.
  // Use strong phrases/combinations so a normal product description is not
  // rejected merely for containing one generic word such as "enviado".
  final spanishShipmentUi =
      lower.contains('pedido confirmado') ||
      (lower.contains('enviado') &&
          lower.contains('en entrega') &&
          lower.contains('entregado')) ||
      (lower.contains('ver más') &&
          (lower.contains('en entrega') || lower.contains('entregado')));

  final spanishLoyaltyUi =
      lower.contains('puntos de bonificación') ||
      lower.contains('puntos de bonificacion');

  final spanishTrackingHelpUi =
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
"""
s = replace_once(s, needle, insert, 'Spanish non-product UI signals')

old = """  if (!orderSignals && (statusOrLogisticsUi || paymentSafetyUi || carrierTrackingUi)) {
    return true;
  }
"""
new = """  if (statusOrLogisticsUi ||
      paymentSafetyUi ||
      carrierTrackingUi ||
      spanishShipmentUi ||
      spanishLoyaltyUi ||
      spanishTrackingHelpUi) {
    return true;
  }
"""
s = replace_once(s, old, new, 'hard reject UI/status/promotional cards')

p.write_text(s)
print('Gmail v11 applied: Spanish shipment/loyalty/tracking banners are hard rejected.')
