# utils/response_classifier.py

def classify_gate_response(response_text):
    if not response_text:
        return "ERROR", "ERROR", "⚠️", False
    last_lower = response_text.lower()
    if any(kw in last_lower for kw in ['thank', 'success', 'succeeded', 'charged', 
                                         'hit', 'payment success', 'approved', 'completed']):
        return "HIT", "CHARGED", "🔥", True
    if any(kw in last_lower for kw in ['security code is incorrect', 'incorrect_cvv', 
                                         'incorrect_cvc', 'cvv mismatch']):
        return "CCN", "CCN LIVE", "✅", True
    if any(kw in last_lower for kw in ['transaction_not_allowed', 'do_not_honor',
                                         'transaction not permitted']):
        return "CVV", "CVV LIVE", "✅", True
    if any(kw in last_lower for kw in ['verifying', 'action_required', 'requires_action',
                                         '3ds', 'otp', 'authentication', 'verify']):
        return "3DS", "OTP REQUIRED", "🔐", True
    if any(kw in last_lower for kw in ['insufficient funds', 'insufficient_funds',
                                         'not sufficient funds', 'insufficient balance']):
        return "INSUFFICIENT", "LOW FUNDS", "💰", True
    if any(kw in last_lower for kw in ['expired', 'card has expired', 'card expired']):
        return "EXPIRED", "EXPIRED", "📅", False
    if any(kw in last_lower for kw in ['network_error', 'timeout', 'stripe_error',
                                         'wp_error', 'connection', 'gateway']):
        return "ERROR", "NETWORK ERROR", "⚠️", False
    return "DEAD", "DECLINED", "❌", False
