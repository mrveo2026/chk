# bot.py
import telebot
import time
import re
import threading
import os
import random
import requests
import sys
from datetime import datetime
from telebot import types
from config import *
from database import *
from credit_system import *
from logger import *
from proxy_manager import proxy_manager

# Fix import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from utils.card_utils import extract_cards_from_text
    from utils.response_classifier import classify_gate_response
    from utils.rate_limiter import mass_rate_limiter
except:
    from card_utils import extract_cards_from_text
    from response_classifier import classify_gate_response
    from rate_limiter import mass_rate_limiter

# ==================== GATE IMPORTS ====================
import importlib

def get_gate_module(gate_file):
    try:
        try:
            module = importlib.import_module(f'gate_modules.{gate_file}')
            return module
        except:
            module = importlib.import_module(gate_file.replace('.py', ''))
            return module
    except Exception as e:
        print(f"Error loading {gate_file}: {e}")
        log_error(f"Failed to load gate module {gate_file}: {e}")
        return None

gate_modules = {}
for g in ['gatet1', 'gatet2', 'gatet3', 'gatet4', 'gatet5', 'gatetHB']:
    mod = get_gate_module(g)
    if mod:
        gate_modules[g] = mod

# ==================== BOT INITIALIZATION ====================
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", num_threads=50)
active_mass_checks = {}
bin_cache = {}

# ==================== BIN LOOKUP ====================
def get_bin_info(bin_num):
    if bin_num in bin_cache:
        return bin_cache[bin_num].copy()
    try:
        response = requests.get(f'https://lookup.binlist.net/{bin_num}', timeout=10)
        if response.status_code == 200:
            data = response.json()
            info = {
                'bank': data.get('bank', {}).get('name', 'Unknown').upper(),
                'emoji': data.get('country', {}).get('emoji', '🏳️'),
                'country': data.get('country', {}).get('name', 'Unknown').upper(),
                'scheme': data.get('scheme', 'UNKNOWN').upper(),
                'type': data.get('type', 'UNKNOWN').upper(),
                'level': data.get('brand', 'STANDARD').upper(),
            }
            bin_cache[bin_num] = info.copy()
            return info
    except:
        pass
    first_digit = bin_num[0] if bin_num else '4'
    scheme_map = {'4': 'VISA', '5': 'MASTERCARD', '3': 'AMEX', '6': 'DISCOVER'}
    info = {
        'bank': 'UNKNOWN BANK', 'emoji': '🏳️', 'country': 'UNKNOWN',
        'scheme': scheme_map.get(first_digit, 'UNKNOWN'), 'type': 'CREDIT', 'level': 'STANDARD',
    }
    bin_cache[bin_num] = info.copy()
    return info

# ==================== GET IP INFO ====================
ip_cache = {'ip': 'Loading...', 'city': 'Unknown', 'country': 'Unknown', 'country_emoji': '🏳️', 'isp': 'Unknown'}
last_ip_fetch = 0

def get_ip_info():
    global ip_cache, last_ip_fetch
    current_time = time.time()
    if current_time - last_ip_fetch < 60:
        return ip_cache
    try:
        apis = ['http://ip-api.com/json/', 'https://ipinfo.io/json']
        for api in apis:
            try:
                response = requests.get(api, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if 'ip-api.com' in api:
                        ip_cache = {
                            'ip': data.get('query', 'Unknown'),
                            'city': data.get('city', 'Unknown'),
                            'country': data.get('country', 'Unknown'),
                            'country_emoji': get_country_emoji(data.get('countryCode', '')),
                            'isp': data.get('isp', 'Unknown')
                        }
                    elif 'ipinfo.io' in api:
                        ip_cache = {
                            'ip': data.get('ip', 'Unknown'),
                            'city': data.get('city', 'Unknown'),
                            'country': data.get('country', 'Unknown'),
                            'country_emoji': get_country_emoji(data.get('country', '')),
                            'isp': data.get('org', 'Unknown')
                        }
                    last_ip_fetch = current_time
                    return ip_cache
            except:
                continue
    except Exception as e:
        log_error(f"IP fetch error: {str(e)}")
    return ip_cache

def get_country_emoji(country_code):
    if not country_code or len(country_code) != 2:
        return '🏳️'
    try:
        offset = 127397
        return chr(ord(country_code[0].upper()) + offset) + chr(ord(country_code[1].upper()) + offset)
    except:
        return '🏳️'

# ==================== FORWARD RESULT ====================
def forward_card_result(chat_id, card, result, gate_name, amount, elapsed, username, user_id):
    try:
        if not FORWARD_CHANNEL:
            return
        if FORWARD_HITS_ONLY and result['status_code'] not in FORWARD_STATUS_CODES:
            return
        if result['status_code'] in ['INSUFFICIENT', 'LOW FUNDS'] and not FORWARD_INCLUDE_LOW_FUNDS:
            return
        if result['status_code'] in ['EXPIRED'] and not FORWARD_INCLUDE_EXPIRED:
            return
        
        parts = card.split('|')
        cc_number = parts[0]
        bin_num = cc_number[:6]
        last_four = cc_number[-4:]
        masked_cc = f"{bin_num}...{last_four}|{parts[1]}|{parts[2]}|{parts[3]}"
        bin_info = get_bin_info(bin_num)
        
        status_icons = {
            'HIT': '🔥', 'CHARGED': '🔥', 'CCN': '✅', 'CCN LIVE': '✅',
            'CVV': '✅', 'CVV LIVE': '✅', '3DS': '🔐', 'OTP REQUIRED': '🔐',
            'INSUFFICIENT': '💰', 'LOW FUNDS': '💰', 'EXPIRED': '📅',
            'DEAD': '❌', 'DECLINED': '❌', 'ERROR': '⚠️', 'NETWORK ERROR': '⚠️'
        }
        icon = status_icons.get(result['status_code'], '❓')
        
        ip_section = ""
        if FORWARD_SHOW_IP:
            ip_info = get_ip_info()
            ip_section = f"""<b>🌐 IP:</b> <code>{ip_info['ip']}</code>
<b>📍 Location:</b> {ip_info['city']}, {ip_info['country']} {ip_info['country_emoji']}
<b>📡 ISP:</b> {ip_info['isp']}
"""
        
        forward_text = f"""<b>{icon} {result['status']}</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>💳 Card:</b> <code>{masked_cc}</code>
<b>🚪 Gate:</b> {gate_name} ${amount}
<b>🏦 BIN:</b> {bin_info['scheme']} - {bin_info['type']} - {bin_info['level']}
<b>🌍 Country:</b> {bin_info['country']} {bin_info['emoji']}
<b>🏛 Bank:</b> {bin_info['bank']}
<b>💬 Response:</b> <i>{result['response'][:100]}</i>
<b>━━━━━━━━━━━━━━━━━━</b>
{ip_section}<b>⏱ Time:</b> {elapsed:.1f}s | 👤 @{username}
<b>🤖 Bot:</b> @{bot.get_me().username}"""
        
        try:
            bot.send_message(FORWARD_CHANNEL, forward_text)
        except Exception as e:
            log_error(f"Failed to forward: {str(e)}")
    except Exception as e:
        log_error(f"Forward error: {str(e)}")

# ==================== CARD CHECKING ====================
def check_single_card(cc, gate_module, amount, user_id, refund_list):
    """Check single card - shows actual gate response"""
    for attempt in range(2):
        try:
            time.sleep(random.uniform(0.5, 1.0))
            bin_info = get_bin_info(cc[:6])
            
            proxies = None
            if USE_PROXY and proxy_manager.has_proxies():
                proxies = proxy_manager.get_random_proxy()
            
            # ===== CALL GATE MODULE =====
            try:
                gate_result = gate_module.Tele(cc, amount, proxies=proxies)
            except TypeError:
                gate_result = gate_module.Tele(cc, amount)
            except Exception as e:
                if attempt == 0:
                    time.sleep(2)
                    continue
                raise e
            
            # ===== PARSE GATE RESULT =====
            # Gate returns: (response_text, gateway_name)
            if isinstance(gate_result, tuple) and len(gate_result) >= 1:
                raw_response = str(gate_result[0])
                gateway_name = str(gate_result[1]) if len(gate_result) > 1 else "Gate"
            elif isinstance(gate_result, str):
                raw_response = gate_result
                gateway_name = "Gate"
            else:
                raw_response = str(gate_result)
                gateway_name = "Gate"
            
            # Clean response
            raw_response = raw_response.strip()
            if not raw_response or len(raw_response) < 3:
                if attempt == 0:
                    time.sleep(2)
                    continue
                raw_response = "No response from gateway"
            
            # ===== CLASSIFY USING GATE MODULE FIRST =====
            if hasattr(gate_module, 'classify_response'):
                try:
                    status_code, detail = gate_module.classify_response(raw_response)
                except:
                    status_code, detail = "UNKNOWN", raw_response[:50]
                
                # Map gate status codes to display
                gate_status_map = {
                    'HIT': ('HIT', 'CHARGED', '🔥'),
                    'CCN': ('CCN', 'CCN LIVE', '✅'),
                    'CVV': ('CVV', 'CVV LIVE', '✅'),
                    '3DS': ('3DS', 'OTP REQUIRED', '🔐'),
                    'INSUFFICIENT': ('INSUFFICIENT', 'LOW FUNDS', '💰'),
                    'EXPIRED': ('EXPIRED', 'EXPIRED', '📅'),
                    'DEAD': ('DEAD', 'DECLINED', '❌'),
                }
                
                if status_code in gate_status_map:
                    sc, sd, icon = gate_status_map[status_code]
                else:
                    sc, sd, icon = classify_gate_response(raw_response)
            else:
                sc, sd, icon, _ = classify_gate_response(raw_response)
            
            # Refund for expired/error
            if sc in ["EXPIRED", "ERROR"] and cc in refund_list:
                try:
                    add_credits(user_id, COST_PER_CHECK, None, f"Refund: {sc}")
                except:
                    pass
            
            parts = cc.split("|")
            return {
                'cc': cc,
                'card_display': f"{parts[0]}|{parts[1]}|{parts[2]}|{parts[3]}",
                'status': sd,
                'icon': icon,
                'status_code': sc,
                'response': raw_response[:200],  # Actual gate response
                'gateway': gateway_name,
                'bin_info': bin_info,
            }
            
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            log_error(f"Check error for {cc[:6]}: {str(e)}")
            parts = cc.split("|")
            if cc in refund_list:
                try:
                    add_credits(user_id, COST_PER_CHECK, None, "Refund: exception")
                except:
                    pass
            return {
                'cc': cc,
                'card_display': f"{parts[0]}|{parts[1]}|{parts[2]}|{parts[3]}",
                'status': 'ERROR',
                'icon': '⚠️',
                'status_code': 'ERROR',
                'response': f"Error: {str(e)[:150]}",
                'gateway': 'Unknown',
                'bin_info': {'scheme': 'UNKNOWN', 'type': 'UNKNOWN', 'level': 'UNKNOWN',
                           'country': 'UNKNOWN', 'emoji': '🏳️', 'bank': 'UNKNOWN'},
            }
    
    parts = cc.split("|")
    return {
        'cc': cc,
        'card_display': f"{parts[0]}|{parts[1]}|{parts[2]}|{parts[3]}",
        'status': 'UNKNOWN',
        'icon': '❓',
        'status_code': 'UNKNOWN',
        'response': 'Check failed after retries',
        'gateway': 'Unknown',
        'bin_info': {'scheme': 'UNKNOWN', 'type': 'UNKNOWN', 'level': 'UNKNOWN',
                   'country': 'UNKNOWN', 'emoji': '🏳️', 'bank': 'UNKNOWN'},
    }

# ==================== MASS CHECK EXECUTION ====================
def run_mass_check(chat_id, user_id, username, cards, gate_info, gate_key, refund_list, progress_msg_id):
    gate_name = gate_info['name']
    gate_module = gate_modules[gate_info['gate_file']]
    total = len(cards)
    start_time = time.time()
    
    if chat_id not in active_mass_checks:
        active_mass_checks[chat_id] = {}
    active_mass_checks[chat_id]['stop'] = False
    
    stats = {'charged': 0, 'otp': 0, 'low_funds': 0, 'declined': 0, 'network_error': 0, 'checked': 0}
    results = []
    
    for idx, cc in enumerate(cards):
        # Check stop flag
        if chat_id in active_mass_checks and active_mass_checks[chat_id].get('stop', False):
            print(f"🛑 Stopped at card {idx+1}/{total}")
            break
        
        amount = round(random.uniform(gate_info['amount_min'], gate_info['amount_max']), 2)
        result = check_single_card(cc, gate_module, str(amount), user_id, refund_list)
        results.append(result)
        
        # Forward
        card_elapsed = time.time() - start_time
        forward_card_result(chat_id, cc, result, gate_name, amount, card_elapsed, username, user_id)
        
        # Save to DB
        try:
            save_card_result(user_id, cc, gate_name, amount, result['status_code'], result['response'], result['bin_info'])
        except:
            pass
        
        # Update stats
        stats['checked'] += 1
        sc = result['status_code']
        if sc == 'HIT':
            stats['charged'] += 1
        elif sc == '3DS':
            stats['otp'] += 1
        elif sc == 'INSUFFICIENT':
            stats['low_funds'] += 1
        elif sc in ['DEAD', 'EXPIRED']:
            stats['declined'] += 1
        elif sc == 'ERROR':
            stats['network_error'] += 1
        else:
            stats['declined'] += 1
        
        # Progress bar
        elapsed = time.time() - start_time
        progress_percent = (idx + 1) / total * 100
        filled = min(int(progress_percent / 16.67), 6)
        empty = max(6 - filled, 0)
        bar = "▬" * filled + "▭" * empty
        
        # Card display
        current_card = cc.split('|')
        card_display = f"{current_card[0][:6]}...{current_card[0][-4:]}|{current_card[1]}|{current_card[2]}|{current_card[3]}"
        
        # Show actual gate response
        response_show = result['response'][:80]
        
        progress_text = f"""<b>📂 FILE CHECK - LIVE</b>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🚪 Gate:</b> <code>{gate_name}</code>
<b>⏱️ Elapsed:</b> <code>{elapsed:.1f}s</code>

<b>💳 Card:</b>
<code>{card_display}</code>
<b>📊 Status:</b> {result['icon']} <code>{result['status']}</code>
<b>💬 Response:</b> <i>{response_show}</i>

<b>┏━━━━━━━━━━━━━━━━━━━━┓</b>
<b>┃ {bar} {progress_percent:.1f}%</b>
<b>┗━━━━━━━━━━━━━━━━━━━━┛</b>"""
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(f"🔥Charged : {stats['charged']}", callback_data="none"),
            types.InlineKeyboardButton(f"🔐OTP: {stats['otp']}", callback_data="none")
        )
        markup.add(
            types.InlineKeyboardButton(f"💰Low : {stats['low_funds']}", callback_data="none"),
            types.InlineKeyboardButton(f"❌Declined: {stats['declined']}", callback_data="none")
        )
        markup.add(
            types.InlineKeyboardButton(f"⚠️Error :{stats['network_error']}", callback_data="none"),
            types.InlineKeyboardButton(f"📊 {idx+1}/{total}", callback_data="none")
        )
        markup.add(types.InlineKeyboardButton("🛑 STOP CHECK", callback_data="stop_check"))
        
        try:
            bot.edit_message_text(progress_text, chat_id, progress_msg_id, reply_markup=markup)
        except:
            pass
        
        # Check stop again
        if active_mass_checks.get(chat_id, {}).get('stop', False):
            break
        
        time.sleep(random.uniform(0.3, 0.7))
    
    # ===== COMPLETION =====
    elapsed = time.time() - start_time
    
    if chat_id in active_mass_checks:
        active_mass_checks[chat_id]['stop'] = False
    
    update_user_stats(user_id, {
        'total_checked': stats['checked'],
        'total_charged': stats['charged'],
        'total_otp': stats['otp'],
        'total_lowfunds': stats['low_funds'],
        'total_declined': stats['declined'],
        'total_network_error': stats['network_error']
    })
    
    hit_rate = (stats['charged'] / stats['checked'] * 100) if stats['checked'] > 0 else 0
    
    summary_text = f"""<b>✅ FILE CHECK COMPLETED!</b>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>📅 Date:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M')}</code>
<b>⏱️ Time:</b> <code>{elapsed:.2f}s</code>
<b>🚪 Gate:</b> <code>{gate_name}</code>

<b>━━━━ 📊 SUMMARY REPORT ━━━━</b>
<b>💳 Total:</b> <code>{stats['checked']}</code>
<b>🔥 Charged:</b> <code>{stats['charged']}</code>
<b>🔐 OTP:</b> <code>{stats['otp']}</code>
<b>💰 Low Funds:</b> <code>{stats['low_funds']}</code>
<b>❌ Declined:</b> <code>{stats['declined']}</code>
<b>⚠️ Error:</b> <code>{stats['network_error']}</code>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🎯 HIT RATE:</b> <code>{hit_rate:.1f}%</code>"""

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"🔥Charged : {stats['charged']}", callback_data="none"),
        types.InlineKeyboardButton(f"🔐OTP: {stats['otp']}", callback_data="none")
    )
    markup.add(
        types.InlineKeyboardButton(f"💰Low : {stats['low_funds']}", callback_data="none"),
        types.InlineKeyboardButton(f"❌Declined: {stats['declined']}", callback_data="none")
    )
    markup.add(
        types.InlineKeyboardButton(f"⚠️Error :{stats['network_error']}", callback_data="none"),
        types.InlineKeyboardButton(f"💳Total: {stats['checked']}", callback_data="none")
    )
    markup.add(
        types.InlineKeyboardButton("🔄 RE-CHECK", callback_data="recheck"),
        types.InlineKeyboardButton("🏠 MAIN MENU", callback_data="main_menu")
    )
    
    try:
        bot.edit_message_text(summary_text, chat_id, progress_msg_id, reply_markup=markup)
    except:
        bot.send_message(chat_id, summary_text, reply_markup=markup)
    
    # Auto export
    if AUTO_EXPORT_RESULTS:
        export_files = export_card_results(user_id, username, results, gate_name)
        for label, filepath in export_files:
            try:
                with open(filepath, 'rb') as f:
                    bot.send_document(chat_id, f, caption=f"📤 {label} - {gate_name}")
            except:
                pass
    
    log_check(user_id, username, gate_name, "MASS_CHECK", 
              f"Completed: {stats['checked']} cards, {stats['charged']} charged", "")

def export_card_results(user_id, username, results, gate_name):
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        export_dir = f'data/exports/{user_id}'
        os.makedirs(export_dir, exist_ok=True)
        
        charged_cards = []
        otp_cards = []
        low_funds_cards = []
        all_cards = []
        
        for r in results:
            card_info = f"{r['cc']} | {r['status']} | {r['response'][:50]}"
            all_cards.append(card_info)
            if r['status_code'] in ['HIT', 'CHARGED']:
                charged_cards.append(card_info)
            elif r['status_code'] in ['3DS', 'OTP REQUIRED']:
                otp_cards.append(card_info)
            elif r['status_code'] in ['INSUFFICIENT', 'LOW FUNDS']:
                low_funds_cards.append(card_info)
        
        files = []
        if charged_cards:
            fpath = f'{export_dir}/charged_{timestamp}.txt'
            with open(fpath, 'w') as f:
                f.write(f"# 🔥 Charged Cards - {gate_name}\n# Count: {len(charged_cards)}\n" + "="*40 + "\n\n")
                f.write("\n".join(charged_cards))
            files.append((f'🔥 Charged ({len(charged_cards)})', fpath))
        
        if otp_cards:
            fpath = f'{export_dir}/otp_{timestamp}.txt'
            with open(fpath, 'w') as f:
                f.write(f"# 🔐 OTP Cards - {gate_name}\n# Count: {len(otp_cards)}\n" + "="*40 + "\n\n")
                f.write("\n".join(otp_cards))
            files.append((f'🔐 OTP ({len(otp_cards)})', fpath))
        
        if low_funds_cards:
            fpath = f'{export_dir}/lowfunds_{timestamp}.txt'
            with open(fpath, 'w') as f:
                f.write(f"# 💰 Low Funds - {gate_name}\n# Count: {len(low_funds_cards)}\n" + "="*40 + "\n\n")
                f.write("\n".join(low_funds_cards))
            files.append((f'💰 Low Funds ({len(low_funds_cards)})', fpath))
        
        return files
    except Exception as e:
        log_error(f"Export error: {str(e)}")
        return []

# ==================== COMMANDS ====================
@bot.message_handler(commands=["start"])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    first_name = message.from_user.first_name or "User"
    
    if create_user(user_id, username, first_name):
        add_credits(user_id, WELCOME_BONUS, username, "Welcome bonus")
    
    credits = get_user_credits(user_id)
    
    text = f"""<b>🔥 {BOT_NAME}</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>👤 User:</b> @{username}
<b>🆔 ID:</b> <code>{user_id}</code>
<b>💎 Plan:</b> Free
<b>💰 Credits:</b> <code>{credits}</code>

<b>📊 System Status:</b>
<b>⚡ Operational:</b> ✅
<b>🌐 Gateways:</b> 6/6 Online

<b>📌 Send .txt file to start checking!</b>"""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Stats", callback_data="stats"),
        types.InlineKeyboardButton("💎 Premium", callback_data="premium")
    )
    markup.add(
        types.InlineKeyboardButton("👥 Invite", callback_data="invite"),
        types.InlineKeyboardButton("🌐 Proxy", callback_data="proxy_menu")
    )
    markup.add(
        types.InlineKeyboardButton("💸 Transfer", callback_data="transfer_menu"),
        types.InlineKeyboardButton("🔧 Tools", callback_data="tools")
    )
    
    bot.reply_to(message, text, reply_markup=markup)

@bot.message_handler(commands=["v1", "v2", "v3", "v4", "v5", "v6"])
def mass_check_command(message):
    user_id = message.from_user.id
    cmd = message.text.split()[0].replace('/', '').lower()
    
    if not mass_rate_limiter.is_allowed(user_id):
        wait_time = mass_rate_limiter.time_until_reset(user_id)
        bot.reply_to(message, f"⏳ Rate limit! Wait {wait_time:.0f}s")
        return
    
    if cmd not in MASS_GATES:
        bot.reply_to(message, "❌ Invalid gate! Use: /v1 to /v6")
        return
    
    gate_info = MASS_GATES[cmd]
    
    if gate_info['gate_file'] not in gate_modules:
        bot.reply_to(message, f"❌ Gate module not found!")
        return
    
    # Only accept TXT file - prompt user
    text = f"""<b>📥 Send .txt file for {gate_info['name']}</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>💵 Amount:</b> ${gate_info['amount_min']} - ${gate_info['amount_max']}
<b>💳 Cost:</b> {COST_PER_CHECK} credit/card

<b>📌 Send a .txt file with cards!</b>
<b>Format:</b> <code>4111111111111111|12|25|123</code>"""
    
    sent_msg = bot.reply_to(message, text)
    bot.register_next_step_handler(sent_msg, process_file_input, gate_info, cmd, user_id)

def process_file_input(message, gate_info, gate_key, original_user_id):
    """Process only TXT file input"""
    if message.from_user.id != original_user_id:
        return
    
    cards = []
    
    if message.document:
        if message.document.file_name.endswith('.txt'):
            try:
                file_info = bot.get_file(message.document.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                text = downloaded_file.decode('utf-8', errors='ignore')
                cards = extract_cards_from_text(text)
            except Exception as e:
                bot.reply_to(message, f"❌ Error reading file: {str(e)}")
                return
        else:
            bot.reply_to(message, "❌ Please send a .txt file only!")
            return
    else:
        bot.reply_to(message, "❌ Please send a .txt file only!\nUse /v1 to /v6 then send file.")
        return
    
    if not cards:
        bot.reply_to(message, "❌ No valid cards found in file!")
        return
    
    handle_mass_check_start(message, cards, gate_key, gate_info)

def handle_mass_check_start(message, cards, gate_key, gate_info):
    user_id = message.from_user.id
    chat_id = message.chat.id
    is_private = chat_id == user_id
    is_admin = str(user_id) == SUBSCRIBER
    
    if len(cards) > MAX_CARDS_PER_CHECK:
        cards = cards[:MAX_CARDS_PER_CHECK]
        bot.reply_to(message, f"⚠️ Limited to {MAX_CARDS_PER_CHECK} cards!")
    
    total_cost = len(cards) * COST_PER_CHECK
    credits = get_user_credits(user_id)
    
    if is_private and not is_admin and credits < total_cost:
        bot.reply_to(message, f"""<b>❌ Insufficient Credits!</b>
<b>💳 Cards:</b> {len(cards)}
<b>💰 Cost:</b> {total_cost} credits
<b>💎 Balance:</b> {credits} credits""")
        return
    
    text = f"""<b>📋 Confirmation</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>🚪 Gate:</b> {gate_info['name']}
<b>💳 Cards:</b> <code>{len(cards)}</code>
<b>💰 Cost:</b> <code>{total_cost}</code> credits
<b>💎 Balance:</b> <code>{credits}</code> credits

<b>Start?</b>"""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Start", callback_data=f"start_check_{gate_key}"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_check")
    )
    
    sent_msg = bot.reply_to(message, text, reply_markup=markup)
    
    if chat_id not in active_mass_checks:
        active_mass_checks[chat_id] = {}
    active_mass_checks[chat_id][str(sent_msg.message_id)] = {
        'cards': cards, 'gate_info': gate_info, 'gate_key': gate_key, 'user_id': user_id
    }

@bot.message_handler(commands=["stop"])
def stop_command(message):
    chat_id = message.chat.id
    if chat_id in active_mass_checks:
        active_mass_checks[chat_id]['stop'] = True
        bot.reply_to(message, "🛑 <b>Stopping...</b>")
    else:
        bot.reply_to(message, "❌ No active check!")

@bot.message_handler(commands=["balance"])
def balance_command(message):
    credits = get_user_credits(message.from_user.id)
    bot.reply_to(message, f"💰 <b>Balance:</b> <code>{credits}</code> credits")

@bot.message_handler(commands=["transfer"])
def transfer_command(message):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, f"<b>💸 Transfer:</b> /transfer @user amount\n<b>💰 Balance:</b> {get_user_credits(user_id)}")
        return
    receiver_input = parts[1].replace('@', '')
    try:
        amount = int(parts[2])
    except:
        bot.reply_to(message, "❌ Invalid amount!")
        return
    if amount < MIN_TRANSFER:
        bot.reply_to(message, f"❌ Min: {MIN_TRANSFER}")
        return
    if get_user_credits(user_id) < amount:
        bot.reply_to(message, "❌ Insufficient credits!")
        return
    
    receiver = get_user_by_username(receiver_input) if not receiver_input.isdigit() else None
    if not receiver and receiver_input.isdigit():
        receiver_id = int(receiver_input)
        create_user(receiver_id, None, None)
        receiver = {'user_id': receiver_id, 'username': f'User{receiver_id}'}
    
    if not receiver:
        bot.reply_to(message, f"❌ User @{receiver_input} not found!")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Confirm", callback_data=f"transfer_confirm_{receiver['user_id']}_{amount}"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="transfer_cancel")
    )
    bot.reply_to(message, f"<b>💸 Transfer {amount} credits to @{receiver['username']}?</b>", reply_markup=markup)

@bot.message_handler(commands=["addcredits"])
def add_credits_command(message):
    if str(message.from_user.id) != SUBSCRIBER:
        return
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "/addcredits user_id amount")
        return
    try:
        target_id = int(parts[1])
        amount = int(parts[2])
        add_credits(target_id, amount, None, f"Admin added {amount}")
        bot.reply_to(message, f"✅ Added {amount} credits to {target_id}")
    except:
        bot.reply_to(message, "❌ Error")

# ==================== CALLBACKS ====================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    username = call.from_user.username or call.from_user.first_name
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    if call.data == "none":
        bot.answer_callback_query(call.id)
        return
    
    elif call.data.startswith("transfer_confirm_"):
        parts = call.data.split("_")
        receiver_id = int(parts[2])
        amount = int(parts[3])
        success, msg = transfer_credits(user_id, receiver_id, amount)
        bot.answer_callback_query(call.id, msg)
        if success:
            bot.edit_message_text(f"<b>✅ Transferred {amount} credits!</b>", chat_id, message_id)
        else:
            bot.edit_message_text(f"<b>❌ {msg}</b>", chat_id, message_id)
    
    elif call.data == "transfer_cancel":
        bot.answer_callback_query(call.id, "❌ Cancelled")
        bot.edit_message_text("❌ <b>Cancelled!</b>", chat_id, message_id)
    
    elif call.data == "transfer_menu":
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, f"<b>💸 Transfer:</b> /transfer @user amount\n<b>💰 Balance:</b> {get_user_credits(user_id)}")
    
    elif call.data.startswith("start_check_"):
        gate_key = call.data.replace("start_check_", "")
        stored = active_mass_checks.get(chat_id, {}).get(str(message_id), {})
        cards = stored.get('cards', [])
        gate_info = stored.get('gate_info', MASS_GATES.get(gate_key))
        
        if not cards:
            bot.answer_callback_query(call.id, "❌ Session expired!")
            bot.edit_message_text("❌ Expired!", chat_id, message_id)
            return
        
        active_mass_checks.get(chat_id, {}).pop(str(message_id), None)
        
        refund_list = []
        is_private = chat_id == user_id
        is_admin = str(user_id) == SUBSCRIBER
        if is_private and not is_admin:
            for card in cards:
                if deduct_credit(user_id, COST_PER_CHECK):
                    refund_list.append(card)
        
        bot.answer_callback_query(call.id, "✅ Starting...")
        bot.edit_message_text("🚀 <b>Starting...</b>", chat_id, message_id)
        progress_msg = bot.send_message(chat_id, "⏳ <b>Initializing...</b>")
        
        thread = threading.Thread(target=run_mass_check, args=(chat_id, user_id, username, cards, gate_info, gate_key, refund_list, progress_msg.message_id))
        thread.start()
    
    elif call.data == "cancel_check":
        active_mass_checks.get(chat_id, {}).pop(str(message_id), None)
        bot.answer_callback_query(call.id, "❌ Cancelled")
        bot.edit_message_text("❌ <b>Cancelled!</b>", chat_id, message_id)
    
    elif call.data == "stop_check":
        if chat_id in active_mass_checks:
            active_mass_checks[chat_id]['stop'] = True
        else:
            active_mass_checks[chat_id] = {'stop': True}
        bot.answer_callback_query(call.id, "🛑 Stopping...")
        try:
            bot.edit_message_text("🛑 <b>Stopping...</b>", chat_id, message_id)
        except:
            pass
    
    elif call.data == "main_menu":
        credits = get_user_credits(user_id)
        text = f"""<b>🔥 {BOT_NAME}</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>👤 User:</b> @{username}
<b>💰 Credits:</b> <code>{credits}</code>"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📊 Stats", callback_data="stats"),
            types.InlineKeyboardButton("💎 Premium", callback_data="premium")
        )
        markup.add(
            types.InlineKeyboardButton("👥 Invite", callback_data="invite"),
            types.InlineKeyboardButton("🌐 Proxy", callback_data="proxy_menu")
        )
        markup.add(
            types.InlineKeyboardButton("💸 Transfer", callback_data="transfer_menu"),
            types.InlineKeyboardButton("🔧 Tools", callback_data="tools")
        )
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data == "stats":
        stats = get_user_stats(user_id)
        total = stats['total_checked']
        charged = stats['total_charged']
        hit_rate = (charged / total * 100) if total > 0 else 0
        text = f"""<b>📊 Statistics</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>💳 Checked:</b> <code>{stats['total_checked']}</code>
<b>🔥 Charged:</b> <code>{stats['total_charged']}</code>
<b>🔐 OTP:</b> <code>{stats['total_otp']}</code>
<b>💰 Low:</b> <code>{stats['total_lowfunds']}</code>
<b>❌ Declined:</b> <code>{stats['total_declined']}</code>
<b>⚠️ Error:</b> <code>{stats['total_network_error']}</code>
<b>🎯 Hit Rate:</b> <code>{hit_rate:.1f}%</code>"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Menu", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data == "tools":
        text = """<b>🔧 Gateway Selection</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>Send .txt file with:</b>
/v1 - /v6"""
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("v1", callback_data="gate_v1"),
            types.InlineKeyboardButton("v2", callback_data="gate_v2"),
            types.InlineKeyboardButton("v3", callback_data="gate_v3")
        )
        markup.add(
            types.InlineKeyboardButton("v4", callback_data="gate_v4"),
            types.InlineKeyboardButton("v5", callback_data="gate_v5"),
            types.InlineKeyboardButton("v6", callback_data="gate_v6")
        )
        markup.add(types.InlineKeyboardButton("⬅️ Menu", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data == "premium":
        text = f"""<b>💎 Premium Plans</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>🌟 Starter:</b> 4,000 cr | $6 | 31d
<b>⭐ Basic:</b> 10,000 cr | $11 | 31d
<b>💫 Medium:</b> 20,000 cr | $19 | 31d
<b>🔥 Pro:</b> 30,000 cr | $25 | 60d
<b>👑 Super:</b> 50,000 cr | $30 | 99d
<b>💎 Ultra:</b> 150,000 cr | $70 | 999d
<b>📞:</b> {ADMIN_USERNAME}"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📞 Contact", url=f"https://t.me/{ADMIN_USERNAME.replace('@', '')}"))
        markup.add(types.InlineKeyboardButton("⬅️ Menu", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data == "invite":
        link = f"https://t.me/{bot.get_me().username}?start={user_id}"
        text = f"""<b>👥 Referral</b>
<b>💰 +100 Credits per invite</b>
<b>🔗 Link:</b> <code>{link}</code>"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Menu", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data.startswith("gate_"):
        gate_key = call.data.replace("gate_", "")
        gate_info = MASS_GATES.get(gate_key)
        if not gate_info:
            bot.answer_callback_query(call.id, "❌ Invalid!")
            return
        text = f"""<b>📥 Send .txt file for {gate_info['name']}</b>
<b>💵:</b> ${gate_info['amount_min']}-${gate_info['amount_max']}
<b>Format:</b> <code>cc|mm|yy|cvv</code>"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="tools"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        bot.register_next_step_handler_by_chat_id(chat_id, lambda msg: process_file_input(msg, gate_info, gate_key, user_id))
    
    elif call.data == "recheck":
        bot.answer_callback_query(call.id, "🔄 Send file again with /v1 to /v6")
    
    # Proxy callbacks
    elif call.data == "proxy_menu":
        count = proxy_manager.count_proxies()
        status = "🟢 ON" if USE_PROXY else "🔴 OFF"
        text = f"""<b>🌐 Proxy</b>
<b>Status:</b> {status}
<b>Total:</b> <code>{count}</code>"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📋 List", callback_data="proxy_list"),
            types.InlineKeyboardButton("🔍 Check", callback_data="proxy_check_all")
        )
        markup.add(
            types.InlineKeyboardButton("🗑 Clear", callback_data="proxy_clear"),
            types.InlineKeyboardButton("🔄 Toggle", callback_data="proxy_toggle")
        )
        markup.add(types.InlineKeyboardButton("⬅️ Menu", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif call.data == "proxy_list":
        proxies = proxy_manager.get_all_proxies()
        if not proxies:
            bot.answer_callback_query(call.id, "📭 Empty!")
            return
        text = f"<b>📋 Proxies</b> ({len(proxies)})\n" + "\n".join([f"<code>{p}</code>" for p in proxies[:30]])
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="proxy_menu"))
        bot.edit_message_text(text[:4000], chat_id, message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif call.data == "proxy_check_all":
        total = proxy_manager.count_proxies()
        if total == 0:
            bot.answer_callback_query(call.id, "📭 Empty!")
            return
        bot.answer_callback_query(call.id, "🔍 Checking...")
        bot.edit_message_text(f"🔍 <b>Checking {total} proxies...</b>", chat_id, message_id)
        thread = threading.Thread(target=run_proxy_check, args=(chat_id, message_id, user_id))
        thread.start()
    
    elif call.data == "proxy_clear":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Yes", callback_data="proxy_clear_confirm"),
            types.InlineKeyboardButton("❌ No", callback_data="proxy_cancel")
        )
        bot.edit_message_text("⚠️ <b>Clear all?</b>", chat_id, message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif call.data == "proxy_clear_confirm":
        proxy_manager.clear_proxies()
        bot.edit_message_text("✅ <b>Cleared!</b>", chat_id, message_id)
        bot.answer_callback_query(call.id, "✅ Done")
    
    elif call.data == "proxy_cancel":
        bot.edit_message_text("❌ <b>Cancelled!</b>", chat_id, message_id)
        bot.answer_callback_query(call.id)
    
    elif call.data == "proxy_toggle":
        global USE_PROXY
        USE_PROXY = not USE_PROXY
        bot.answer_callback_query(call.id, f"{'🟢 ON' if USE_PROXY else '🔴 OFF'}")

def run_proxy_check(chat_id, message_id, user_id):
    total = proxy_manager.count_proxies()
    w = [0]; d = [0]; c = [0]
    
    def cb(checked, total, proxy, ok, msg):
        if ok: w[0] += 1
        else: d[0] += 1
        c[0] = checked
        if c[0] % 10 == 0 or c[0] == total:
            pct = c[0]/total*100
            bar = "▬"*int(pct/16.67) + "▭"*(6-int(pct/16.67))
            try:
                bot.edit_message_text(f"🔍 Checking...\n┃ {bar} {pct:.1f}%\n✅{w[0]} ❌{d[0]} 📊{c[0]}/{total}", chat_id, message_id)
            except: pass
    
    working, dead = proxy_manager.check_all_proxies(callback=cb, max_workers=20)
    bot.edit_message_text(f"✅ Done!\n📦{total} | ✅{len(working)} | ❌{len(dead)}", chat_id, message_id)

# ==================== FILE HANDLER ====================
@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Handle TXT file upload for proxy or cards"""
    user_id = message.from_user.id
    
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        text = downloaded_file.decode('utf-8', errors='ignore')
        caption = (message.caption or '').lower().strip()
        
        # Proxy file
        if 'proxy' in caption:
            if str(user_id) != SUBSCRIBER and message.chat.type != 'private':
                return
            added, skipped = proxy_manager.add_proxies_from_text(text)
            bot.reply_to(message, f"✅ Added: {added} | Skipped: {skipped} | Total: {proxy_manager.count_proxies()}")
            return
        
        # Card file - check for gate in caption
        gate_key = None
        for cmd in ['v1', 'v2', 'v3', 'v4', 'v5', 'v6']:
            if cmd in caption:
                gate_key = cmd
                break
        
        if gate_key and gate_key in MASS_GATES:
            gate_info = MASS_GATES[gate_key]
            if gate_info['gate_file'] not in gate_modules:
                bot.reply_to(message, "❌ Gate module not found!")
                return
            cards = extract_cards_from_text(text)
            if cards:
                handle_mass_check_start(message, cards, gate_key, gate_info)
            else:
                bot.reply_to(message, "❌ No valid cards found!")
        else:
            # No gate specified - show gate selection
            cards = extract_cards_from_text(text)
            if cards:
                markup = types.InlineKeyboardMarkup(row_width=3)
                markup.add(
                    types.InlineKeyboardButton("v1", callback_data="gate_v1"),
                    types.InlineKeyboardButton("v2", callback_data="gate_v2"),
                    types.InlineKeyboardButton("v3", callback_data="gate_v3")
                )
                markup.add(
                    types.InlineKeyboardButton("v4", callback_data="gate_v4"),
                    types.InlineKeyboardButton("v5", callback_data="gate_v5"),
                    types.InlineKeyboardButton("v6", callback_data="gate_v6")
                )
                bot.reply_to(message, f"<b>📋 Found {len(cards)} cards. Select gate:</b>", reply_markup=markup)
            else:
                bot.reply_to(message, "❌ No valid cards in file!")
                
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_unknown(message):
    if message.chat.type == 'private':
        bot.reply_to(message, "📌 Send a .txt file to start! Use /start for menu.")

# ==================== STARTUP ====================
if __name__ == "__main__":
    print("=" * 50)
    print(f"🔥 {BOT_NAME} CC CHECKER BOT")
    print("=" * 50)
    init_database()
    print(f"✅ DB initialized")
    print(f"🔌 Gates: {list(gate_modules.keys())}")
    print(f"📢 Channel: {FORWARD_CHANNEL}")
    print("=" * 50)
    
    while True:
        try:
            print("✅ Bot running...")
            bot.polling(non_stop=True, interval=1, timeout=30, long_polling_timeout=60)
        except requests.exceptions.ReadTimeout:
            print("⚠️ Timeout - retry...")
            time.sleep(5)
        except requests.exceptions.ConnectionError:
            print("⚠️ Connection lost - retry...")
            time.sleep(10)
        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(10)
