# bot.py
import telebot
import time
import re
import threading
import os
import random
import requests
from datetime import datetime
from telebot import types
from config import *
from database import *
from credit_system import *
from logger import *
from proxy_manager import proxy_manager
from utils.card_utils import *
from utils.response_classifier import classify_gate_response
from utils.rate_limiter import mass_rate_limiter
# bot.py အပေါ်ဆုံးမှာ ထည့်ပါ
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ==================== GATE IMPORTS ====================
import importlib

def get_gate_module(gate_file):
    try:
        module = importlib.import_module(f'gate_modules.{gate_file}')
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
        emoji = chr(ord(country_code[0].upper()) + offset) + chr(ord(country_code[1].upper()) + offset)
        return emoji
    except:
        return '🏳️'

# ==================== FORWARD RESULT ====================
def forward_card_result(chat_id, card, result, gate_name, amount, elapsed, username, user_id):
    try:
        if not FORWARD_CHANNEL:
            return
        if FORWARD_HITS_ONLY:
            if result['status_code'] not in FORWARD_STATUS_CODES:
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
        status_title = result['status']
        
        ip_section = ""
        if FORWARD_SHOW_IP:
            ip_info = get_ip_info()
            ip_section = f"""<b>🌐 IP:</b> <code>{ip_info['ip']}</code>
<b>📍 Location:</b> {ip_info['city']}, {ip_info['country']} {ip_info['country_emoji']}
<b>📡 ISP:</b> {ip_info['isp']}
"""
        
        forward_text = f"""<b>{icon} {status_title}</b>
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

# ==================== EXPORT RESULTS ====================
def export_card_results(user_id, username, results, gate_name):
    """Export card results to files and send to user"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        export_dir = f'data/exports/{user_id}'
        os.makedirs(export_dir, exist_ok=True)
        
        # Separate results by status
        charged_cards = []
        otp_cards = []
        low_funds_cards = []
        declined_cards = []
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
            else:
                declined_cards.append(card_info)
        
        files_to_send = []
        
        # All results
        if all_cards:
            all_file = f'{export_dir}/all_results_{timestamp}.txt'
            with open(all_file, 'w') as f:
                f.write(f"# All Results - {gate_name}\n")
                f.write(f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                f.write(f"# User: @{username}\n")
                f.write("#" + "=" * 40 + "\n\n")
                for card in all_cards:
                    f.write(f"{card}\n")
            files_to_send.append(('📋 All Results', all_file))
        
        # Charged cards
        if charged_cards and EXPORT_CHARGED:
            charged_file = f'{export_dir}/charged_{timestamp}.txt'
            with open(charged_file, 'w') as f:
                f.write(f"# 🔥 Charged Cards - {gate_name}\n")
                f.write(f"# Count: {len(charged_cards)}\n")
                f.write("#" + "=" * 40 + "\n\n")
                for card in charged_cards:
                    f.write(f"{card}\n")
            files_to_send.append((f'🔥 Charged ({len(charged_cards)})', charged_file))
        
        # OTP/3DS cards
        if otp_cards and EXPORT_3DS:
            otp_file = f'{export_dir}/otp_3ds_{timestamp}.txt'
            with open(otp_file, 'w') as f:
                f.write(f"# 🔐 OTP/3DS Cards - {gate_name}\n")
                f.write(f"# Count: {len(otp_cards)}\n")
                f.write("#" + "=" * 40 + "\n\n")
                for card in otp_cards:
                    f.write(f"{card}\n")
            files_to_send.append((f'🔐 OTP/3DS ({len(otp_cards)})', otp_file))
        
        # Low Funds cards
        if low_funds_cards and EXPORT_LOW_FUNDS:
            low_file = f'{export_dir}/low_funds_{timestamp}.txt'
            with open(low_file, 'w') as f:
                f.write(f"# 💰 Low Funds Cards - {gate_name}\n")
                f.write(f"# Count: {len(low_funds_cards)}\n")
                f.write("#" + "=" * 40 + "\n\n")
                for card in low_funds_cards:
                    f.write(f"{card}\n")
            files_to_send.append((f'💰 Low Funds ({len(low_funds_cards)})', low_file))
        
        return files_to_send
        
    except Exception as e:
        log_error(f"Export error: {str(e)}")
        return []

# ==================== CARD CHECKING ====================
def check_single_card(cc, gate_module, amount, user_id, refund_list):
    for attempt in range(2):
        try:
            time.sleep(random.uniform(0.5, 1.0))
            bin_info = get_bin_info(cc[:6])
            
            proxies = None
            if USE_PROXY and proxy_manager.has_proxies():
                proxies = proxy_manager.get_random_proxy()
            
            try:
                result = gate_module.Tele(cc, amount, proxies=proxies)
            except TypeError:
                result = gate_module.Tele(cc, amount)
            
            if isinstance(result, tuple) and len(result) >= 2:
                response_text = result[0]
            else:
                response_text = str(result)
            
            if not response_text or len(response_text.strip()) < 5:
                if attempt == 0:
                    time.sleep(2)
                    continue
                response_text = "No response from gateway"
            
            if hasattr(gate_module, 'classify_response'):
                sc, detail = gate_module.classify_response(response_text)
                status_map = {
                    'HIT': ('HIT', 'CHARGED', '🔥', True),
                    'CCN': ('CCN', 'CCN LIVE', '✅', True),
                    'CVV': ('CVV', 'CVV LIVE', '✅', True),
                    '3DS': ('3DS', 'OTP REQUIRED', '🔐', True),
                    'INSUFFICIENT': ('INSUFFICIENT', 'LOW FUNDS', '💰', True),
                    'DEAD': ('DEAD', 'DECLINED', '❌', False),
                }
                if sc in status_map:
                    status_code, status_display, icon, is_live = status_map[sc]
                else:
                    status_code, status_display, icon, is_live = classify_gate_response(response_text)
            else:
                status_code, status_display, icon, is_live = classify_gate_response(response_text)
            
            if status_code in ["EXPIRED", "ERROR"] and cc in refund_list:
                try:
                    add_credits(user_id, COST_PER_CHECK, None, f"Refund: {status_code}")
                except:
                    pass
            
            parts = cc.split("|")
            return {
                'cc': cc,
                'card_display': f"{parts[0]}|{parts[1]}|{parts[2]}|{parts[3]}",
                'status': status_display, 'icon': icon, 'status_code': status_code,
                'response': response_text[:100], 'bin_info': bin_info, 'is_live': is_live
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
                'cc': cc, 'card_display': f"{parts[0]}|{parts[1]}|{parts[2]}|{parts[3]}",
                'status': 'ERROR', 'icon': '⚠️', 'status_code': 'ERROR',
                'response': str(e)[:100],
                'bin_info': {'scheme': 'UNKNOWN', 'type': 'UNKNOWN', 'level': 'UNKNOWN',
                           'country': 'UNKNOWN', 'emoji': '🏳️', 'bank': 'UNKNOWN'},
                'is_live': False
            }
    
    parts = cc.split("|")
    return {
        'cc': cc, 'card_display': f"{parts[0]}|{parts[1]}|{parts[2]}|{parts[3]}",
        'status': 'UNKNOWN', 'icon': '❓', 'status_code': 'UNKNOWN',
        'response': 'Check failed after retries',
        'bin_info': {'scheme': 'UNKNOWN', 'type': 'UNKNOWN', 'level': 'UNKNOWN',
                   'country': 'UNKNOWN', 'emoji': '🏳️', 'bank': 'UNKNOWN'},
        'is_live': False
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
        if active_mass_checks.get(chat_id, {}).get('stop', False):
            break
        
        amount = round(random.uniform(gate_info['amount_min'], gate_info['amount_max']), 2)
        result = check_single_card(cc, gate_module, str(amount), user_id, refund_list)
        results.append(result)
        
        # Forward result
        card_elapsed = time.time() - start_time
        forward_card_result(chat_id, cc, result, gate_name, amount, card_elapsed, username, user_id)
        
        # Save result to database
        save_card_result(user_id, cc, gate_name, amount, result['status_code'], result['response'], result['bin_info'])
        
        stats['checked'] += 1
        if result['status_code'] == 'HIT':
            stats['charged'] += 1
        elif result['status_code'] == '3DS':
            stats['otp'] += 1
        elif result['status_code'] == 'INSUFFICIENT':
            stats['low_funds'] += 1
        elif result['status_code'] in ['DEAD', 'EXPIRED']:
            stats['declined'] += 1
        elif result['status_code'] == 'ERROR':
            stats['network_error'] += 1
        else:
            stats['declined'] += 1
        
        # Progress update
        elapsed = time.time() - start_time
        progress_percent = (idx + 1) / total * 100
        filled = int(progress_percent / 16.67)
        empty = 6 - filled
        bar = "▬" * filled + "▭" * empty
        
        current_card = cc.split('|')
        card_display = f"{current_card[0][:6]}...{current_card[0][-4:]}|{current_card[1]}|{current_card[2]}|{current_card[3]}"
        
        progress_text = f"""<b>📂 FILE CHECK - LIVE</b>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🚪 Gate:</b> <code>{gate_name}</code>
<b>⏱️ Elapsed:</b> <code>{elapsed:.1f}s</code>

<b>💳 Card:</b>
<code>{card_display}</code>
<b>📊 Status:</b> {result['icon']} <code>{result['status']}</code>
<b>💬 Response:</b> <i>{result['response'][:50]}</i>

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
        
        time.sleep(random.uniform(0.3, 0.7))
    
    # Completion
    elapsed = time.time() - start_time
    active_mass_checks.get(chat_id, {}).pop('stop', None)
    
    update_user_stats(user_id, {
        'total_checked': stats['checked'], 'total_charged': stats['charged'],
        'total_otp': stats['otp'], 'total_lowfunds': stats['low_funds'],
        'total_declined': stats['declined'], 'total_network_error': stats['network_error']
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
        types.InlineKeyboardButton("📋 COPY CODE", callback_data="copy_code"),
        types.InlineKeyboardButton("🔄 RE-CHECK", callback_data="recheck")
    )
    markup.add(
        types.InlineKeyboardButton("📤 EXPORT", callback_data=f"export_results_{gate_key}"),
        types.InlineKeyboardButton("🏠 MAIN MENU", callback_data="main_menu")
    )
    
    try:
        bot.edit_message_text(summary_text, chat_id, progress_msg_id, reply_markup=markup)
    except:
        bot.send_message(chat_id, summary_text, reply_markup=markup)
    
    # Auto export if enabled
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

# ==================== COMMAND HANDLERS ====================
@bot.message_handler(commands=["start"])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    first_name = message.from_user.first_name or "User"
    
    if create_user(user_id, username, first_name):
        add_credits(user_id, WELCOME_BONUS, username, "Welcome bonus")
    
    credits = get_user_credits(user_id)
    
    welcome_text = f"""<b>🔥 {BOT_NAME}</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>👤 User:</b> @{username}
<b>🆔 ID:</b> <code>{user_id}</code>
<b>💎 Plan:</b> Free
<b>💰 Credits:</b> <code>{credits}</code>

<b>📊 System Status:</b>
<b>⚡ Operational:</b> ✅
<b>🌐 Gateways:</b> 6/6 Online

<b>Select an option below:</b>"""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚀 Start Checking", callback_data="start_checking"),
        types.InlineKeyboardButton("📊 Stats", callback_data="stats")
    )
    markup.add(
        types.InlineKeyboardButton("🔧 Tools", callback_data="tools"),
        types.InlineKeyboardButton("💎 Premium", callback_data="premium")
    )
    markup.add(
        types.InlineKeyboardButton("👥 Invite", callback_data="invite"),
        types.InlineKeyboardButton("🌐 Proxy", callback_data="proxy_menu")
    )
    
    bot.reply_to(message, welcome_text, reply_markup=markup)

@bot.message_handler(commands=["v1", "v2", "v3", "v4", "v5", "v6"])
def mass_check_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    cmd = message.text.split()[0].replace('/', '').lower()
    
    if not mass_rate_limiter.is_allowed(user_id):
        wait_time = mass_rate_limiter.time_until_reset(user_id)
        bot.reply_to(message, f"⏳ Rate limit! Please wait {wait_time:.0f}s")
        return
    
    if cmd not in MASS_GATES:
        bot.reply_to(message, "❌ Invalid gate! Use: /v1 to /v6")
        return
    
    gate_info = MASS_GATES[cmd]
    
    if gate_info['gate_file'] not in gate_modules:
        bot.reply_to(message, f"❌ Gate module not found!")
        return
    
    cards_text = message.text.replace(f'/{cmd}', '', 1).strip()
    
    if cards_text:
        cards = extract_cards_from_text(cards_text)
        if cards:
            handle_mass_check_start(message, cards, cmd, gate_info)
            return
    
    if message.reply_to_message:
        replied_text = message.reply_to_message.text or message.reply_to_message.caption or ''
        cards = extract_cards_from_text(replied_text)
        if cards:
            handle_mass_check_start(message, cards, cmd, gate_info)
            return
    
    prompt_text = f"""<b>📥 Mass Check - Send Cards</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>🚪 Gate:</b> {gate_info['name']}
<b>💵 Amount:</b> ${gate_info['amount_min']} - ${gate_info['amount_max']}
<b>💳 Cost:</b> {COST_PER_CHECK} credit/card

<b>Send cards in format:</b>
<code>4111111111111111|12|25|123</code>

<b>Or send a .txt file</b>"""
    
    sent_msg = bot.reply_to(message, prompt_text)
    bot.register_next_step_handler(sent_msg, process_mass_cards_input, gate_info, cmd, message.from_user.id)

def process_mass_cards_input(message, gate_info, gate_key, original_user_id):
    if message.from_user.id != original_user_id:
        return
    cards = []
    if message.document and message.document.file_name.endswith('.txt'):
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            text = downloaded_file.decode('utf-8')
            cards = extract_cards_from_text(text)
        except Exception as e:
            bot.reply_to(message, f"❌ Error reading file: {str(e)}")
            return
    elif message.text:
        cards = extract_cards_from_text(message.text)
    if not cards:
        bot.reply_to(message, "❌ No valid cards found!")
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
<b>━━━━━━━━━━━━━━━━━━</b>
<b>💳 Cards:</b> {len(cards)}
<b>💰 Cost:</b> {total_cost} credits
<b>💎 Your Balance:</b> {credits} credits

<b>Get Premium for more credits!</b>""")
        return
    
    confirm_text = f"""<b>📋 Credit Confirmation</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>🚪 Gate:</b> {gate_info['name']}
<b>💵 Amount:</b> ${gate_info['amount_min']} - ${gate_info['amount_max']}
<b>💳 Cards:</b> <code>{len(cards)}</code>
<b>💰 Cost:</b> <code>{total_cost}</code> credits
<b>💎 Balance:</b> <code>{credits}</code> credits
{'<b>⚡ Admin Mode:</b> Free' if is_admin or not is_private else ''}

<b>Start checking?</b>"""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Start Check", callback_data=f"start_check_{gate_key}_{len(cards)}"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_check")
    )
    
    sent_msg = bot.reply_to(message, confirm_text, reply_markup=markup)
    
    if chat_id not in active_mass_checks:
        active_mass_checks[chat_id] = {}
    active_mass_checks[chat_id][str(sent_msg.message_id)] = {
        'cards': cards, 'gate_info': gate_info, 'gate_key': gate_key, 'user_id': user_id
    }

@bot.message_handler(commands=["stop"])
def stop_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id in active_mass_checks:
        for msg_id, data in active_mass_checks[chat_id].items():
            if isinstance(data, dict) and data.get('user_id') == user_id:
                data['stop'] = True
        bot.reply_to(message, "🛑 <b>Check stopped!</b>")
    else:
        bot.reply_to(message, "❌ No active check to stop!")

@bot.message_handler(commands=["balance"])
def balance_command(message):
    credits = get_user_credits(message.from_user.id)
    bot.reply_to(message, f"💰 <b>Balance:</b> <code>{credits}</code> credits")

@bot.message_handler(commands=["transfer"])
def transfer_command(message):
    """Transfer credits to another user"""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    parts = message.text.split()
    
    if len(parts) < 3:
        bot.reply_to(message, f"""<b>💸 Credit Transfer</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>📌 Usage:</b> /transfer @username amount

<b>Examples:</b>
<code>/transfer @friend 100</code>
<code>/transfer 123456789 50</code>

<b>💰 Your Balance:</b> <code>{get_user_credits(user_id)}</code> credits
<b>📌 Min Transfer:</b> <code>{MIN_TRANSFER}</code> credits""")
        return
    
    # Parse receiver and amount
    receiver_input = parts[1].replace('@', '')
    
    try:
        amount = int(parts[2])
    except ValueError:
        bot.reply_to(message, "❌ Invalid amount! Must be a number.")
        return
    
    if amount < MIN_TRANSFER:
        bot.reply_to(message, f"❌ Minimum transfer amount is {MIN_TRANSFER} credits!")
        return
    
    # Check sender balance
    sender_credits = get_user_credits(user_id)
    if sender_credits < amount:
        bot.reply_to(message, f"❌ Insufficient credits! You have {sender_credits} credits.")
        return
    
    # Find receiver
    receiver = None
    if receiver_input.isdigit():
        receiver_id = int(receiver_input)
        create_user(receiver_id, None, None)
        receiver = {'user_id': receiver_id, 'username': f'User{receiver_id}'}
    else:
        receiver = get_user_by_username(receiver_input)
        if not receiver:
            bot.reply_to(message, f"❌ User @{receiver_input} not found! They need to start the bot first.")
            return
    
    receiver_id = receiver['user_id']
    
    if receiver_id == user_id:
        bot.reply_to(message, "❌ You cannot transfer credits to yourself!")
        return
    
    # Confirm transfer
    receiver_username = receiver['username'] or f"User{receiver_id}"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Confirm", callback_data=f"transfer_confirm_{receiver_id}_{amount}"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="transfer_cancel")
    )
    
    confirm_text = f"""<b>💸 Transfer Confirmation</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>👤 From:</b> @{username}
<b>👤 To:</b> @{receiver_username}
<b>💰 Amount:</b> <code>{amount}</code> credits
<b>💎 Your Balance After:</b> <code>{sender_credits - amount}</code> credits

<b>Confirm transfer?</b>"""
    
    bot.reply_to(message, confirm_text, reply_markup=markup)

@bot.message_handler(commands=["addcredits"])
def add_credits_command(message):
    if str(message.from_user.id) != SUBSCRIBER:
        return
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /addcredits user_id amount")
        return
    try:
        target_id = int(parts[1])
        amount = int(parts[2])
        add_credits(target_id, amount, None, f"Admin added {amount}")
        bot.reply_to(message, f"✅ Added {amount} credits to user {target_id}")
        log_transaction(target_id, amount, 'credit', 'Admin manual addition')
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

@bot.message_handler(commands=["admin_stats"])
def admin_stats(message):
    if str(message.from_user.id) != SUBSCRIBER:
        return
    stats = get_total_stats()
    text = f"""<b>📊 Bot Statistics</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>👥 Total Users:</b> <code>{stats['total_users']}</code>
<b>💰 Total Credits:</b> <code>{stats['total_credits']}</code>
<b>💳 Total Checks:</b> <code>{stats['total_checks']}</code>"""
    bot.reply_to(message, text)

@bot.message_handler(commands=["admin_users"])
def admin_users(message):
    if str(message.from_user.id) != SUBSCRIBER:
        return
    users = get_all_users()
    text = f"<b>👥 User List</b> (Top 20)\n<b>━━━━━━━━━━━━━━━━━━</b>\n"
    for i, user in enumerate(users[:20]):
        uname = user['username'] or f"User{user['user_id']}"
        text += f"<b>{i+1}.</b> @{uname} - <code>{user['credits']}</code> cr\n"
    bot.reply_to(message, text[:4000])

@bot.message_handler(commands=["admin_broadcast"])
def admin_broadcast(message):
    if str(message.from_user.id) != SUBSCRIBER:
        return
    broadcast_text = message.text.replace('/admin_broadcast', '', 1).strip()
    if not broadcast_text:
        bot.reply_to(message, "Usage: /admin_broadcast Your message here")
        return
    users = get_all_users()
    sent_count = 0
    for user in users:
        try:
            bot.send_message(user['user_id'], f"📢 <b>Announcement</b>\n\n{broadcast_text}")
            sent_count += 1
            time.sleep(0.1)
        except:
            pass
    bot.reply_to(message, f"✅ Broadcast sent to {sent_count}/{len(users)} users")

# ==================== PROXY COMMANDS ====================
@bot.message_handler(commands=["proxy"])
def proxy_command(message):
    user_id = message.from_user.id
    if str(user_id) != SUBSCRIBER and message.chat.type != 'private':
        return
    proxy_count = proxy_manager.count_proxies()
    status = "🟢 ENABLED" if USE_PROXY else "🔴 DISABLED"
    text = f"""<b>🌐 Proxy Management</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>📊 Status:</b> {status}
<b>📦 Total Proxies:</b> <code>{proxy_count}</code>

<b>📌 Commands:</b>
<b>/addproxy</b> ip:port - Add single proxy
<b>/removeproxy</b> ip:port - Remove proxy
<b>/proxylist</b> - View all proxies
<b>/checkproxy</b> - Check all proxies
<b>/clearproxy</b> - Clear all proxies
<b>/toggleproxy</b> - Enable/Disable proxy"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 View Proxies", callback_data="proxy_list"),
        types.InlineKeyboardButton("🔍 Check All", callback_data="proxy_check_all")
    )
    markup.add(
        types.InlineKeyboardButton("🗑 Clear All", callback_data="proxy_clear"),
        types.InlineKeyboardButton("🔄 Toggle ON/OFF", callback_data="proxy_toggle")
    )
    markup.add(types.InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu"))
    bot.reply_to(message, text, reply_markup=markup)

@bot.message_handler(commands=["addproxy"])
def add_proxy_command(message):
    user_id = message.from_user.id
    if str(user_id) != SUBSCRIBER and message.chat.type != 'private':
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "<b>📌 Usage:</b> /addproxy ip:port or /addproxy ip:port:user:pass")
        return
    proxy_string = parts[1]
    if ':' not in proxy_string:
        bot.reply_to(message, "❌ Invalid format!")
        return
    success, msg = proxy_manager.add_proxy(proxy_string)
    bot.reply_to(message, msg)

@bot.message_handler(commands=["removeproxy"])
def remove_proxy_command(message):
    user_id = message.from_user.id
    if str(user_id) != SUBSCRIBER and message.chat.type != 'private':
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "<b>📌 Usage:</b> /removeproxy ip:port")
        return
    success, msg = proxy_manager.remove_proxy(parts[1])
    bot.reply_to(message, msg)

@bot.message_handler(commands=["proxylist"])
def proxy_list_command(message):
    user_id = message.from_user.id
    if str(user_id) != SUBSCRIBER and message.chat.type != 'private':
        return
    proxies = proxy_manager.get_all_proxies()
    if not proxies:
        bot.reply_to(message, "📭 No proxies added yet!")
        return
    text = f"<b>📋 Proxy List</b> ({len(proxies)} total)\n<b>━━━━━━━━━━━━━━━━━━</b>\n"
    for i, proxy in enumerate(proxies[:50], 1):
        parts = proxy.split(':')
        masked = f"{parts[0]}:{parts[1]}:{parts[2][:3]}***:***" if len(parts) == 4 else proxy
        text += f"<b>{i}.</b> <code>{masked}</code>\n"
    if len(proxies) > 50:
        text += f"\n<b>... and {len(proxies) - 50} more</b>"
    bot.reply_to(message, text[:4000])

@bot.message_handler(commands=["checkproxy"])
def check_proxy_command(message):
    user_id = message.from_user.id
    if str(user_id) != SUBSCRIBER and message.chat.type != 'private':
        return
    total = proxy_manager.count_proxies()
    if total == 0:
        bot.reply_to(message, "📭 No proxies to check!")
        return
    status_msg = bot.reply_to(message, f"🔍 <b>Checking {total} proxies...</b>")
    thread = threading.Thread(target=run_proxy_check, args=(message.chat.id, status_msg.message_id, user_id))
    thread.start()

def run_proxy_check(chat_id, message_id, user_id):
    total = proxy_manager.count_proxies()
    working_count = [0]
    dead_count = [0]
    checked = [0]
    
    def update_progress(checked_count, total_count, proxy, is_working, msg):
        if is_working:
            working_count[0] += 1
        else:
            dead_count[0] += 1
        checked[0] = checked_count
        if checked[0] % 5 == 0 or checked[0] == total_count:
            progress_percent = checked[0] / total_count * 100
            filled = int(progress_percent / 16.67)
            empty = 6 - filled
            bar = "▬" * filled + "▭" * empty
            parts = proxy.split(':')
            display_proxy = f"{parts[0]}:{parts[1]}:{parts[2][:3]}***:***" if len(parts) == 4 else proxy
            status_icon = "✅" if is_working else "❌"
            progress_text = f"""<b>🔍 Proxy Checker - Running</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>📦 Total Proxies:</b> <code>{total_count}</code>
<b>┏━━━━━━━━━━━━━━━━━━━━┓</b>
<b>┃ {bar} {progress_percent:.1f}%</b>
<b>┗━━━━━━━━━━━━━━━━━━━━┛</b>
<b>✅ Working:</b> <code>{working_count[0]}</code>
<b>❌ Dead:</b> <code>{dead_count[0]}</code>
<b>📊 Checked:</b> <code>{checked[0]}/{total_count}</code>
<b>🔄 Last:</b> {status_icon} <code>{display_proxy}</code>
<b>💬:</b> <i>{msg[:50]}</i>"""
            try:
                bot.edit_message_text(progress_text, chat_id, message_id)
            except:
                pass
    
    working, dead = proxy_manager.check_all_proxies(callback=update_progress, max_workers=20)
    completion_text = f"""<b>✅ Proxy Check Completed!</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>📦 Total:</b> <code>{total}</code>
<b>✅ Working:</b> <code>{len(working)}</code> ({len(working)/total*100:.1f}%)
<b>❌ Dead:</b> <code>{len(dead)}</code> ({len(dead)/total*100:.1f}%)"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"✅ Working ({len(working)})", callback_data="proxy_show_working"),
        types.InlineKeyboardButton(f"❌ Dead ({len(dead)})", callback_data="proxy_show_dead")
    )
    markup.add(
        types.InlineKeyboardButton("💾 Save Working", callback_data="proxy_save_working"),
        types.InlineKeyboardButton("🗑 Remove Dead", callback_data="proxy_remove_dead")
    )
    markup.add(types.InlineKeyboardButton("⬅️ Menu", callback_data="proxy_menu"))
    try:
        bot.edit_message_text(completion_text, chat_id, message_id, reply_markup=markup)
    except:
        pass

@bot.message_handler(commands=["clearproxy"])
def clear_proxy_command(message):
    user_id = message.from_user.id
    if str(user_id) != SUBSCRIBER and message.chat.type != 'private':
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Yes, Clear All", callback_data="proxy_clear_confirm"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="proxy_cancel")
    )
    bot.reply_to(message, "⚠️ <b>Are you sure you want to clear ALL proxies?</b>", reply_markup=markup)

@bot.message_handler(commands=["toggleproxy"])
def toggle_proxy_command(message):
    global USE_PROXY
    user_id = message.from_user.id
    if str(user_id) != SUBSCRIBER and message.chat.type != 'private':
        return
    USE_PROXY = not USE_PROXY
    status = "🟢 ENABLED" if USE_PROXY else "🔴 DISABLED"
    bot.reply_to(message, f"<b>🌐 Proxy:</b> {status}")

# ==================== CALLBACK HANDLERS ====================
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
        if success:
            bot.answer_callback_query(call.id, "✅ Transfer successful!")
            bot.edit_message_text(f"<b>✅ Transfer Successful!</b>\n<b>━━━━━━━━━━━━━━━━━━</b>\n<b>💰 Amount:</b> <code>{amount}</code> credits\n<b>👤 To:</b> <code>{receiver_id}</code>", chat_id, message_id)
        else:
            bot.answer_callback_query(call.id, f"❌ {msg}")
            bot.edit_message_text(f"<b>❌ Transfer Failed!</b>\n{msg}", chat_id, message_id)
    
    elif call.data == "transfer_cancel":
        bot.answer_callback_query(call.id, "❌ Transfer cancelled")
        bot.edit_message_text("❌ <b>Transfer cancelled!</b>", chat_id, message_id)
    
    elif call.data.startswith("start_check_"):
        parts = call.data.split("_")
        gate_key = parts[2]
        stored_data = active_mass_checks.get(chat_id, {}).get(str(message_id), {})
        cards = stored_data.get('cards', [])
        gate_info = stored_data.get('gate_info', MASS_GATES.get(gate_key))
        if not cards or not gate_info:
            bot.answer_callback_query(call.id, "❌ Session expired!")
            bot.edit_message_text("❌ Session expired!", chat_id, message_id)
            return
        active_mass_checks.get(chat_id, {}).pop(str(message_id), None)
        refund_list = []
        is_private = chat_id == user_id
        is_admin = str(user_id) == SUBSCRIBER
        if is_private and not is_admin:
            for card in cards:
                if deduct_credit(user_id, COST_PER_CHECK):
                    refund_list.append(card)
        bot.answer_callback_query(call.id, "✅ Starting check...")
        bot.edit_message_text("🚀 <b>Starting mass check...</b>", chat_id, message_id)
        progress_msg = bot.send_message(chat_id, "⏳ <b>Initializing...</b>")
        thread = threading.Thread(target=run_mass_check, args=(chat_id, user_id, username, cards, gate_info, gate_key, refund_list, progress_msg.message_id))
        thread.start()
    
    elif call.data == "cancel_check":
        active_mass_checks.get(chat_id, {}).pop(str(message_id), None)
        bot.answer_callback_query(call.id, "❌ Check cancelled")
        bot.edit_message_text("❌ <b>Check cancelled!</b>", chat_id, message_id)
    
    elif call.data == "stop_check":
        if chat_id in active_mass_checks:
            for key, data in active_mass_checks[chat_id].items():
                if isinstance(data, dict):
                    data['stop'] = True
        bot.answer_callback_query(call.id, "🛑 Stopping check...")
    
    elif call.data.startswith("export_results_"):
        gate_key = call.data.replace("export_results_", "")
        bot.answer_callback_query(call.id, "📤 Export started, check your files!")
        bot.send_message(chat_id, "📤 <b>Export files are being sent to you...</b>")
    
    elif call.data == "main_menu":
        credits = get_user_credits(user_id)
        text = f"""<b>🔥 {BOT_NAME}</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>👤 User:</b> @{username}
<b>🆔 ID:</b> <code>{user_id}</code>
<b>💎 Plan:</b> Free
<b>💰 Credits:</b> <code>{credits}</code>

<b>📊 System Status:</b>
<b>⚡ Operational:</b> ✅
<b>🌐 Gateways:</b> 6/6 Online"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🚀 Start Checking", callback_data="start_checking"),
            types.InlineKeyboardButton("📊 Stats", callback_data="stats")
        )
        markup.add(
            types.InlineKeyboardButton("🔧 Tools", callback_data="tools"),
            types.InlineKeyboardButton("💎 Premium", callback_data="premium")
        )
        markup.add(
            types.InlineKeyboardButton("👥 Invite", callback_data="invite"),
            types.InlineKeyboardButton("🌐 Proxy", callback_data="proxy_menu")
        )
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data == "start_checking":
        text = f"""<b>🚀 Start Mass Checking</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>💡 Send cards directly or select a gate first:</b>"""
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
        markup.add(types.InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data == "stats":
        stats = get_user_stats(user_id)
        total = stats['total_checked']
        charged = stats['total_charged']
        hit_rate = (charged / total * 100) if total > 0 else 0
        text = f"""<b>📊 Personal Statistics</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>💳 Total Checked:</b> <code>{stats['total_checked']}</code>
<b>🔥 Charged:</b> <code>{stats['total_charged']}</code>
<b>🔐 OTP/Action:</b> <code>{stats['total_otp']}</code>
<b>💰 Low Funds:</b> <code>{stats['total_lowfunds']}</code>
<b>❌ Declined/CCN:</b> <code>{stats['total_declined']}</code>
<b>⚠️ Network Err:</b> <code>{stats['total_network_error']}</code>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>🎯 Hit Rate:</b> <code>{hit_rate:.1f}%</code>"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data == "tools":
        text = f"""<b>🔧 Gateway Selection</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>Status:</b> All Free
<b>Page:</b> [1/1]"""
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("v1 ($0.5-$1)", callback_data="gate_v1"),
            types.InlineKeyboardButton("v2 ($0.7-$1.4)", callback_data="gate_v2"),
            types.InlineKeyboardButton("v3 ($0.9-$2)", callback_data="gate_v3")
        )
        markup.add(
            types.InlineKeyboardButton("v4 ($1-$2)", callback_data="gate_v4"),
            types.InlineKeyboardButton("v5 ($5-$5.5)", callback_data="gate_v5"),
            types.InlineKeyboardButton("v6 ($20-$25)", callback_data="gate_v6")
        )
        markup.add(types.InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data == "premium":
        text = f"""<b>💎 Premium Plans</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>🌟 Starter:</b> 4,000 cr | $6 | 31 days
<b>⭐ Basic:</b> 10,000 cr | $11 | 31 days
<b>💫 Medium:</b> 20,000 cr | $19 | 31 days
<b>🔥 Pro:</b> 30,000 cr | $25 | 60 days
<b>👑 Super:</b> 50,000 cr | $30 | 99 days
<b>💎 Ultra:</b> 150,000 cr | $70 | 999 days
<b>━━━━━━━━━━━━━━━━━━</b>
<b>💵 Payment:</b> USDT (TRC20/BEP20)
<b>📞 Contact:</b> {ADMIN_USERNAME}"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{ADMIN_USERNAME.replace('@', '')}"))
        markup.add(types.InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data == "invite":
        invite_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
        text = f"""<b>👥 Referral Program</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>🎁 Invite friends and earn rewards!</b>

<b>Per invited user:</b>
<b>⏰ +3 Days Premium</b>
<b>💰 +100 Credits</b>

<b>🔗 Your invite link:</b>
<code>{invite_link}</code>"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={invite_link}"))
        markup.add(types.InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data.startswith("gate_"):
        gate_key = call.data.replace("gate_", "")
        gate_info = MASS_GATES.get(gate_key)
        if not gate_info:
            bot.answer_callback_query(call.id, "❌ Invalid gate!")
            return
        text = f"""<b>📥 Send Cards for {gate_info['name']}</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>💵 Amount:</b> ${gate_info['amount_min']} - ${gate_info['amount_max']}
<b>💳 Cost:</b> {COST_PER_CHECK} credit/card"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="start_checking"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        bot.register_next_step_handler_by_chat_id(chat_id, lambda msg: process_mass_cards_input(msg, gate_info, gate_key, user_id))
    
    elif call.data == "recheck":
        bot.answer_callback_query(call.id, "🔄 Send cards again or use /v1 to /v6")
    
    elif call.data == "copy_code":
        bot.answer_callback_query(call.id, "📋 Results displayed below")
    
    elif call.data == "export":
        bot.answer_callback_query(call.id, "📤 Export feature coming soon")
    
    elif call.data == "contact_admin":
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, f"📞 Contact admin: {ADMIN_USERNAME}")
    
    elif call.data == "back_to_menu":
        credits = get_user_credits(user_id)
        text = f"""<b>🔥 {BOT_NAME}</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>👤 User:</b> @{username}
<b>💰 Credits:</b> <code>{credits}</code>"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🚀 Start Checking", callback_data="start_checking"),
            types.InlineKeyboardButton("📊 Stats", callback_data="stats")
        )
        markup.add(
            types.InlineKeyboardButton("🔧 Tools", callback_data="tools"),
            types.InlineKeyboardButton("💎 Premium", callback_data="premium")
        )
        markup.add(
            types.InlineKeyboardButton("👥 Invite", callback_data="invite"),
            types.InlineKeyboardButton("🌐 Proxy", callback_data="proxy_menu")
        )
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    # Proxy callbacks
    elif call.data == "proxy_list":
        proxies = proxy_manager.get_all_proxies()
        if not proxies:
            bot.answer_callback_query(call.id, "📭 No proxies added!")
            return
        text = f"<b>📋 Proxy List</b> ({len(proxies)} total)\n<b>━━━━━━━━━━━━━━━━━━</b>\n"
        for i, proxy in enumerate(proxies[:30], 1):
            parts = proxy.split(':')
            masked = f"{parts[0]}:{parts[1]}:{parts[2][:3]}***:***" if len(parts) == 4 else proxy
            text += f"<b>{i}.</b> <code>{masked}</code>\n"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="proxy_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif call.data == "proxy_clear":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Yes, Clear All", callback_data="proxy_clear_confirm"),
            types.InlineKeyboardButton("❌ Cancel", callback_data="proxy_cancel")
        )
        bot.edit_message_text("⚠️ <b>Are you sure?</b>", chat_id, message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif call.data == "proxy_clear_confirm":
        success, msg = proxy_manager.clear_proxies()
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Menu", callback_data="proxy_menu"))
        bot.edit_message_text(f"<b>{msg}</b>", chat_id, message_id, reply_markup=markup)
        bot.answer_callback_query(call.id, "✅ Cleared")
    
    elif call.data == "proxy_cancel":
        bot.edit_message_text("❌ <b>Cancelled!</b>", chat_id, message_id)
        bot.answer_callback_query(call.id, "❌ Cancelled")
    
    elif call.data == "proxy_toggle":
        global USE_PROXY
        USE_PROXY = not USE_PROXY
        status = "🟢 ENABLED" if USE_PROXY else "🔴 DISABLED"
        bot.answer_callback_query(call.id, f"Proxy {status}")
        proxy_count = proxy_manager.count_proxies()
        text = f"""<b>🌐 Proxy Management</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>📊 Status:</b> {status}
<b>📦 Total Proxies:</b> <code>{proxy_count}</code>"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📋 View", callback_data="proxy_list"),
            types.InlineKeyboardButton("🔍 Check", callback_data="proxy_check_all")
        )
        markup.add(
            types.InlineKeyboardButton("🗑 Clear", callback_data="proxy_clear"),
            types.InlineKeyboardButton("🔄 Toggle", callback_data="proxy_toggle")
        )
        markup.add(types.InlineKeyboardButton("⬅️ Menu", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data == "proxy_check_all":
        total = proxy_manager.count_proxies()
        if total == 0:
            bot.answer_callback_query(call.id, "📭 No proxies!")
            return
        bot.answer_callback_query(call.id, "🔍 Checking...")
        bot.edit_message_text(f"🔍 <b>Checking {total} proxies...</b>", chat_id, message_id)
        thread = threading.Thread(target=run_proxy_check, args=(chat_id, message_id, user_id))
        thread.start()
    
    elif call.data == "proxy_show_working":
        working = proxy_manager.working_proxies
        if not working:
            bot.answer_callback_query(call.id, "📭 No working proxies!")
            return
        text = f"<b>✅ Working Proxies</b> ({len(working)})\n<b>━━━━━━━━━━━━━━━━━━</b>\n"
        for i, proxy in enumerate(working[:30], 1):
            parts = proxy.split(':')
            masked = f"{parts[0]}:{parts[1]}:{parts[2][:3]}***:***" if len(parts) == 4 else proxy
            text += f"<b>{i}.</b> <code>{masked}</code>\n"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💾 Save", callback_data="proxy_save_working"))
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="proxy_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif call.data == "proxy_show_dead":
        dead = proxy_manager.dead_proxies
        if not dead:
            bot.answer_callback_query(call.id, "🎉 No dead proxies!")
            return
        text = f"<b>❌ Dead Proxies</b> ({len(dead)})\n<b>━━━━━━━━━━━━━━━━━━</b>\n"
        for i, item in enumerate(dead[:20], 1):
            proxy = item['proxy']
            parts = proxy.split(':')
            masked = f"{parts[0]}:{parts[1]}:{parts[2][:3]}***:***" if len(parts) == 4 else proxy
            text += f"<b>{i}.</b> <code>{masked}</code>\n   <i>└ {item['reason']}</i>\n"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🗑 Remove", callback_data="proxy_remove_dead"))
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="proxy_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif call.data == "proxy_save_working":
        success, msg = proxy_manager.save_working_proxies()
        bot.answer_callback_query(call.id, msg)
        if success and proxy_manager.working_proxies:
            file_text = "\n".join(proxy_manager.working_proxies)
            with open('data/working_proxies.txt', 'w') as f:
                f.write("# Working Proxies\n" + file_text)
            try:
                with open('data/working_proxies.txt', 'rb') as f:
                    bot.send_document(chat_id, f, caption=f"✅ {len(proxy_manager.working_proxies)} Working Proxies")
            except:
                pass
    
    elif call.data == "proxy_remove_dead":
        success, msg = proxy_manager.remove_dead_proxies()
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="proxy_menu"))
        bot.edit_message_text(f"<b>{msg}</b>\n<b>📦 Remaining:</b> <code>{proxy_manager.count_proxies()}</code>", chat_id, message_id, reply_markup=markup)
        bot.answer_callback_query(call.id, msg)
    
    elif call.data == "proxy_menu":
        proxy_count = proxy_manager.count_proxies()
        status = "🟢 ENABLED" if USE_PROXY else "🔴 DISABLED"
        text = f"""<b>🌐 Proxy Management</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>📊 Status:</b> {status}
<b>📦 Total Proxies:</b> <code>{proxy_count}</code>"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📋 View", callback_data="proxy_list"),
            types.InlineKeyboardButton("🔍 Check", callback_data="proxy_check_all")
        )
        markup.add(
            types.InlineKeyboardButton("🗑 Clear", callback_data="proxy_clear"),
            types.InlineKeyboardButton("🔄 Toggle", callback_data="proxy_toggle")
        )
        markup.add(types.InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)

# ==================== FILE HANDLER ====================
@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        text = downloaded_file.decode('utf-8')
        
        caption = (message.caption or '').lower()
        
        if 'proxy' in caption:
            if str(user_id) != SUBSCRIBER and message.chat.type != 'private':
                return
            added, skipped = proxy_manager.add_proxies_from_text(text)
            bot.reply_to(message, f"""<b>✅ Proxies Added!</b>
<b>━━━━━━━━━━━━━━━━━━</b>
<b>➕ Added:</b> <code>{added}</code>
<b>⏭ Skipped:</b> <code>{skipped}</code>
<b>📦 Total:</b> <code>{proxy_manager.count_proxies()}</code>""")
        else:
            cards = extract_cards_from_text(text)
            if cards:
                gate_key = None
                for cmd in ['v1', 'v2', 'v3', 'v4', 'v5', 'v6']:
                    if f'/{cmd}' in caption:
                        gate_key = cmd
                        break
                if gate_key and gate_key in MASS_GATES:
                    handle_mass_check_start(message, cards, gate_key, MASS_GATES[gate_key])
                else:
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
                bot.reply_to(message, "❌ No valid cards found!")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_unknown(message):
    if message.chat.type == 'private':
        cards = extract_cards_from_text(message.text or '')
        if cards:
            text = f"<b>📋 Cards Detected!</b>\n<b>💳 Found:</b> <code>{len(cards)}</code> cards\n\nUse /v1 to /v6 or /start for menu"
            bot.reply_to(message, text)
        else:
            bot.reply_to(message, "Use /start to see the menu!")

# ==================== STARTUP ====================
if __name__ == "__main__":
    print("=" * 50)
    print(f"🔥 {BOT_NAME} CC CHECKER BOT")
    print("=" * 50)
    print("📦 Initializing database...")
    init_database()
    print("✅ Database initialized")
    print(f"🔌 Loaded gates: {list(gate_modules.keys())}")
    print(f"🌐 Gateways: {len(gate_modules)}/6 Online")
    print(f"📢 Forward Channel: {FORWARD_CHANNEL}")
    print(f"📤 Auto Export: {AUTO_EXPORT_RESULTS}")
    print("=" * 50)
    print("🤖 Bot starting...")
    
    while True:
        try:
            print("✅ Bot is running...")
            bot.polling(non_stop=True, interval=1, timeout=30, long_polling_timeout=60)
        except requests.exceptions.ReadTimeout:
            print("⚠️ Timeout - reconnecting...")
            time.sleep(5)
        except requests.exceptions.ConnectionError:
            print("⚠️ Connection lost - reconnecting...")
            time.sleep(10)
        except Exception as e:
            print(f"⚠️ Error: {e} - restarting in 10s...")
            time.sleep(10)
