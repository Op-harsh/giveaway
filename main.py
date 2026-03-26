import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatJoinRequest
import threading
import time
import random
import logging
import json
import os
from datetime import datetime
import pytz
import html

# --- SYSTEM SETTINGS ---
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = '8787373138:AAF8DYw6_29_6Y_L4jRHU8uZTmhZg-L0G4o'
OWNER_ID = 5524906942
DB_FILE = 'multi_giveaway_db.json'
IST = pytz.timezone('Asia/Kolkata')

bot = telebot.TeleBot(BOT_TOKEN)
db_lock = threading.Lock() 
user_captcha = {}

# --- DATABASE ENGINE ---
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                for k in ['giveaways', 'admins', 'force_chans', 'join_reqs', 'users', 'banned']:
                    if k not in data: data[k] = {} if k not in ['admins', 'banned'] else []
                if 'settings' not in data: data['settings'] = {'ref_on': False, 'ref_req': 3, 'ref_type': 'forced', 'antibot_on': False}
                return data
        except Exception as e: logging.error(f"DB Load Error: {e}")
    return {'giveaways': {}, 'admins': [], 'force_chans': {}, 'join_reqs': {}, 'users': {}, 'banned': [], 'settings': {'ref_on': False, 'ref_req': 3, 'ref_type': 'forced', 'antibot_on': False}}

def save_db(data):
    with db_lock:
        with open(DB_FILE, 'w') as f: json.dump(data, f, indent=4)

db = load_db()
bot_admins, banned_users = set(db.get('admins', [])), set(db.get('banned', []))
force_sub_chans, active_gws = db.get('force_chans', {}), db.get('giveaways', {})
admin_setup = {}

# --- TIME FIX ---
def is_active(now_str, start_str, end_str):
    if start_str < end_str: return start_str <= now_str < end_str
    else: return now_str >= start_str or now_str < end_str 

# --- SECURITY, UTILS & ANTI-CRASH SHIELDS ---
def is_auth(uid): return uid == OWNER_ID or uid in bot_admins
def is_owner(uid): return uid == OWNER_ID
def is_banned(uid): return uid in banned_users
def safe_html(t): return html.escape(str(t))

def safe_reply(message, text, reply_markup=None, parse_mode="HTML"):
    try: bot.reply_to(message, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception: pass

def ghost_reply(message, text, reply_markup=None):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    try:
        sent = bot.send_message(message.chat.id, text, reply_markup=reply_markup, parse_mode="HTML")
        threading.Timer(12.0, lambda: bot.delete_message(message.chat.id, sent.message_id)).start()
    except: pass

def init_user(uid):
    uid = str(uid)
    if uid not in db['users']: db['users'][uid] = {'refs': [], 'participated': 0, 'won': 0}
    for k in ['participated', 'won']:
        if k not in db['users'][uid]: db['users'][uid][k] = 0

def get_unjoined(uid):
    unjoined = {}
    for cid, data in force_sub_chans.items():
        link = data['link'] if isinstance(data, dict) else data
        c_type = data['type'] if isinstance(data, dict) else 'public'
        if c_type == 'req':
            if uid not in db.get('join_reqs', {}).get(str(cid), []):
                try:
                    if bot.get_chat_member(int(cid), uid).status not in ['member', 'administrator', 'creator']: unjoined[cid] = link
                except: unjoined[cid] = link
        else:
            try:
                if bot.get_chat_member(int(cid), uid).status not in ['member', 'administrator', 'creator']: unjoined[cid] = link
            except: unjoined[cid] = link
    return unjoined

# --- PREMIUM ADMIN CONTROLS ---
@bot.message_handler(commands=['ban', 'unban', 'addadmin', 'adminlist'])
def owner_controls(m):
    if not is_owner(m.from_user.id): return safe_reply(m, "⛔ <b>ACCESS DENIED:</b> Owner clearance required.")
    cmd = m.text.split()
    
    if cmd[0] in ['/ban', '/unban']:
        if len(cmd) != 2 or not cmd[1].isdigit(): return safe_reply(m, "⚠️ <b>Syntax:</b> <code>/ban <ID></code>")
        tid = int(cmd[1])
        if cmd[0] == '/ban': banned_users.add(tid); safe_reply(m, f"🔨 <b>BANNED:</b> Target <code>{tid}</code> is blacklisted.")
        else: banned_users.discard(tid); safe_reply(m, f"✅ <b>RESTORED:</b> Target <code>{tid}</code> is unbanned.")
        db['banned'] = list(banned_users); save_db(db)
        
    elif cmd[0] == '/addadmin':
        if len(cmd) != 2 or not cmd[1].isdigit(): return safe_reply(m, "⚠️ <b>Syntax:</b> <code>/addadmin <ID></code>")
        bot_admins.add(int(cmd[1])); save_db(db)
        safe_reply(m, f"🎖️ <b>PROMOTED:</b> Agent <code>{cmd[1]}</code> granted Admin status.")
        
    elif cmd[0] == '/adminlist':
        kb = InlineKeyboardMarkup()
        for a in bot_admins: kb.add(InlineKeyboardButton(f"👮 {a}", callback_data="ignore"), InlineKeyboardButton("❌ Revoke", callback_data=f"rmadm_{a}"))
        safe_reply(m, "👑 <b>AUTHORIZED COMMANDERS</b>", reply_markup=kb)

@bot.message_handler(commands=['vipsetup'])
def vip_setup_cmd(m):
    if not is_owner(m.from_user.id): return
    send_vip_menu(m.chat.id)

def send_vip_menu(chat_id, msg_id=None):
    st = db['settings']
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🟢 REF: ON" if st['ref_on'] else "🔴 REF: OFF", callback_data="vip_ref_toggle"), InlineKeyboardButton("⚠️ FORCED" if st.get('ref_type', 'forced') == 'forced' else "🎁 BONUS (3x)", callback_data="vip_ref_mode"))
    kb.row(InlineKeyboardButton("➖", callback_data="vip_dec"), InlineKeyboardButton(f"Target: {st['ref_req']}", callback_data="ignore"), InlineKeyboardButton("➕", callback_data="vip_inc"))
    kb.row(InlineKeyboardButton("🛡️ ANTI-BOT SHIELD: ON" if st.get('antibot_on', False) else "🔴 ANTI-BOT SHIELD: OFF", callback_data="vip_bot_toggle"))
    text = "⚙️ <b>MASTER VIP CONTROL TERMINAL</b> 👑\n━━━━━━━━━━━━━━━━━━\n<i>Fine-tune your growth hacks and security protocols below:</i>"
    try:
        if msg_id: bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb, parse_mode="HTML")
        else: bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")
    except Exception: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith('vip_'))
def vip_cb(c):
    if not is_owner(c.from_user.id): return bot.answer_callback_query(c.id, "Owner Access Required!", show_alert=True)
    if c.data == 'vip_ref_toggle': db['settings']['ref_on'] = not db['settings']['ref_on']
    elif c.data == 'vip_ref_mode': db['settings']['ref_type'] = 'bonus' if db['settings'].get('ref_type', 'forced') == 'forced' else 'forced'
    elif c.data == 'vip_bot_toggle': db['settings']['antibot_on'] = not db['settings'].get('antibot_on', False)
    elif c.data == 'vip_inc': db['settings']['ref_req'] += 1
    elif c.data == 'vip_dec' and db['settings']['ref_req'] > 1: db['settings']['ref_req'] -= 1
    save_db(db); send_vip_menu(c.message.chat.id, c.message.message_id)

@bot.message_handler(commands=['myprofile'])
def my_profile_cmd(m):
    uid = str(m.from_user.id)
    if is_banned(m.from_user.id): return
    init_user(uid)
    u = db['users'][uid]
    msg = (f"👤 <b>PREMIUM VIP DOSSIER</b> 👤\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"📛 <b>Agent:</b> {safe_html(m.from_user.first_name)}\n"
           f"🆔 <b>ID:</b> <code>{uid}</code>\n\n"
           f"📊 <b>BATTLE STATS:</b>\n"
           f" ├ 🔗 <b>Recruits:</b> {len(u['refs'])}\n"
           f" ├ 🎟️ <b>Events Entered:</b> {u['participated']}\n"
           f" └ 🏆 <b>Glorious Wins:</b> {u['won']}\n"
           f"━━━━━━━━━━━━━━━━━━")
    safe_reply(m, msg)

# --- ADMIN EVENT CONTROLS (RESTORED PLAYERDETAILS) ---
@bot.message_handler(commands=['gwstatus', 'endnow', 'cancelgw', 'forcelist', 'addforce', 'playerdetails'])
def admin_events(m):
    if not is_auth(m.from_user.id): return
    cmd = m.text.lower().split()
    
    if cmd[0] == '/addforce':
        if not is_owner(m.from_user.id): return safe_reply(m, "⛔ <b>ACCESS DENIED!</b>")
        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("🌍 Public Node", callback_data="fsub_public"), InlineKeyboardButton("🔐 Private Node", callback_data="fsub_private"))
        kb.row(InlineKeyboardButton("📩 Join Request Node", callback_data="fsub_req"))
        safe_reply(m, "⚙️ <b>SECURITY NODE CONFIGURATION</b>\n━━━━━━━━━━━━━━━━━━\n<i>Select the type of Force Sub channel to add below:</i>", reply_markup=kb)
        
    elif cmd[0] == '/forcelist':
        if not is_owner(m.from_user.id): return
        kb = InlineKeyboardMarkup()
        for c_id, data in force_sub_chans.items():
            ctype = data['type'].upper() if isinstance(data, dict) else 'PUBLIC'
            kb.add(InlineKeyboardButton(f"[{ctype}] {c_id}", url=data['link'] if isinstance(data, dict) else data), InlineKeyboardButton("❌ Disconnect", callback_data=f"rmfsub_{c_id}"))
        safe_reply(m, "🛡️ <b>ACTIVE SECURITY NODES</b>", reply_markup=kb)
        
    elif cmd[0] == '/gwstatus':
        msg = "📊 <b>LIVE SYSTEM OVERVIEW:</b>\n━━━━━━━━━━━━━━━━━━\n"
        for c, d in active_gws.items(): 
            st = '🏃 LIVE' if d['is_running'] else '⏳ SCHED'
            msg += f"\n🔹 <b>{c}</b> | {st}\n├ Type: {d['type'].upper()}\n├ Prize: {safe_html(d['prize'])}\n├ Entries: {len(d['entries'])}\n└ Time: {d['s_disp']} to {d['e_disp']}\n"
        safe_reply(m, msg if active_gws else "📭 <b>ALL CLEAR:</b> No active events in the system.")
        
    elif cmd[0] in ['/endnow', '/cancelgw'] and len(cmd) >= 2:
        code = cmd[1]
        if code in active_gws:
            if cmd[0] == '/endnow': 
                safe_reply(m, f"⚡ <b>INITIATING FORCE END:</b> <code>{code}</code>")
                threading.Thread(target=end_logic, args=(code,)).start()
            elif cmd[0] == '/cancelgw': 
                del active_gws[code]; save_db(db)
                safe_reply(m, f"🗑️ <b>EVENT TERMINATED:</b> <code>{code}</code> has been deleted.")
        else: safe_reply(m, "❌ <b>ERROR:</b> Event Code not found in database.")

    elif cmd[0] == '/playerdetails':
        if len(cmd) < 2: return safe_reply(m, "⚠️ <b>Syntax:</b> <code>/playerdetails <CODE></code>")
        code = cmd[1]
        if code in active_gws:
            d = active_gws[code]
            if not d['entries']: return safe_reply(m, "📭 <b>NO DATA:</b> No players have entered yet.")
            kb = InlineKeyboardMarkup()
            for val, u in d['entries'].items():
                disp_val = val.split('_')[0] if '_' in val else val
                kb.add(InlineKeyboardButton(f"{u['name']} (Entry: {disp_val})", callback_data="ignore"),
                       InlineKeyboardButton("🏆 Force Win", callback_data=f"fw_{code}_{val}"))
            safe_reply(m, f"📋 <b>PLAYER ROSTER FOR {code}:</b>\n━━━━━━━━━━━━━━━━━━", reply_markup=kb)
        else: safe_reply(m, "❌ <b>ERROR:</b> Event Code not found.")

@bot.callback_query_handler(func=lambda c: c.data.startswith('fw_') or c.data.startswith('fwi_') or c.data.startswith('fws_'))
def force_win_logic(c):
    if not is_auth(c.from_user.id): return
    parts = c.data.split('_', 2)
    action, code, val = parts[0], parts[1], parts[2]
    
    if code not in active_gws: return bot.answer_callback_query(c.id, "Event Expired!", show_alert=True)
    
    if action == 'fw':
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("⚡ Instant Win", callback_data=f"fwi_{code}_{val}"), InlineKeyboardButton("⏳ Scheduled Win", callback_data=f"fws_{code}_{val}"))
        disp_val = val.split('_')[0] if '_' in val else val
        try: bot.edit_message_text(f"⚙️ <b>ACTION FOR ENTRY: {disp_val}</b>", c.message.chat.id, c.message.message_id, reply_markup=kb, parse_mode="HTML")
        except: pass
    elif action == 'fwi':
        try: bot.edit_message_text(f"⚡ <b>INSTANT OVERRIDE TRIGGERED!</b>", c.message.chat.id, c.message.message_id, parse_mode="HTML")
        except: pass
        threading.Thread(target=end_logic, args=(code, val)).start()
    elif action == 'fws':
        active_gws[code]['win_mode'] = 'manual'
        active_gws[code]['win_num'] = [val]
        active_gws[code]['win_count'] = 1
        save_db(db)
        try: bot.edit_message_text(f"⏳ <b>SCHEDULED OVERRIDE LOCKED.</b>\nThey will win when time ends.", c.message.chat.id, c.message.message_id, parse_mode="HTML")
        except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith('fsub_'))
def addforce_step1(c):
    if not is_owner(c.from_user.id): return
    ctype = c.data.split('_')[1]
    try: bot.delete_message(c.message.chat.id, c.message.message_id)
    except: pass
    bot.register_next_step_handler(bot.send_message(c.message.chat.id, f"📝 <b>Node Type: {ctype.upper()}</b>\n━━━━━━━━━━━━━━━━━━\nSend the Channel ID and Invite Link separated by space.\n💡 <i>Example: -100123456789 https://t.me/joinchat/...</i>", parse_mode="HTML"), process_addforce, ctype)

def process_addforce(m, ctype):
    try:
        cid, link = m.text.split()[0], m.text.split()[1]
        force_sub_chans[cid] = {'link': link, 'type': ctype}
        save_db(db)
        safe_reply(m, f"✅ <b>SUCCESS:</b> Security Node <code>{cid}</code> linked and active.")
    except: safe_reply(m, "❌ <b>FORMAT ERROR!</b> Setup failed.")

@bot.callback_query_handler(func=lambda c: c.data.startswith('rmadm_') or c.data.startswith('rmfsub_'))
def rm_logic(c):
    if not is_owner(c.from_user.id): return
    if c.data.startswith('rmadm_'): bot_admins.discard(int(c.data.split('_')[1]))
    else: force_sub_chans.pop(c.data.replace('rmfsub_', ''), None)
    save_db(db)
    try: bot.delete_message(c.message.chat.id, c.message.message_id)
    except: pass

# --- MULTI-MODE SETUP ---
@bot.message_handler(commands=['setgw'])
def start_setup(m):
    if not is_auth(m.from_user.id): return
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🔢 Number Pick", callback_data="gwt_number"), InlineKeyboardButton("🕵️‍♂️ Code Hunt", callback_data="gwt_code"))
    kb.row(InlineKeyboardButton("⚡ Fast Quiz", callback_data="gwt_quiz"), InlineKeyboardButton("🎰 Power Gacha", callback_data="gwt_gacha"))
    safe_reply(m, "👑 <b>EVENT DEPLOYMENT PROTOCOL</b> 👑\n━━━━━━━━━━━━━━━━━━\n<i>Select the mission type for your audience:</i>", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith('gwt_'))
def gw_type_select(c):
    aid = c.from_user.id
    if not is_auth(aid): return
    gtype = c.data.split('_')[1]
    host_name = f"@{c.from_user.username}" if c.from_user.username else c.from_user.first_name
    admin_setup[aid] = {'chans': [], 'type': gtype, 'host': host_name}
    try: bot.delete_message(c.message.chat.id, c.message.message_id)
    except: pass
    msg = bot.send_message(c.message.chat.id, f"📝 Mode Locked: <b>{gtype.upper()}</b>\n\n🕒 <b>Phase 1:</b> Send Start Time (e.g. 08:00 PM)", parse_mode="HTML")
    bot.register_next_step_handler(msg, get_t1)

def get_t1(m):
    try:
        t24 = datetime.strptime(m.text.strip().upper(), "%I:%M %p").strftime("%H:%M")
        admin_setup[m.from_user.id].update({'t1': t24, 'd1': m.text.strip().upper()})
        bot.register_next_step_handler(bot.reply_to(m, "🛑 <b>Phase 2:</b> Send End Time (e.g. 09:30 PM)", parse_mode="HTML"), get_t2)
    except: bot.register_next_step_handler(bot.reply_to(m, "❌ <b>Format Error!</b> Use proper format (HH:MM AM/PM)"), get_t1)

def get_t2(m):
    try:
        t24 = datetime.strptime(m.text.strip().upper(), "%I:%M %p").strftime("%H:%M")
        admin_setup[m.from_user.id].update({'t2': t24, 'd2': m.text.strip().upper()})
        bot.register_next_step_handler(bot.reply_to(m, "🎁 <b>Phase 3:</b> Send the Prize Pool (e.g. Netflix 1 Month):", parse_mode="HTML"), get_prize)
    except: bot.register_next_step_handler(bot.reply_to(m, "❌ <b>Format Error!</b>"), get_t2)

def get_prize(m):
    admin_setup[m.from_user.id]['prize'] = m.text.strip()
    bot.register_next_step_handler(bot.reply_to(m, "👥 <b>Phase 4:</b> Number of Winners? (e.g. 1, 3, 5)", parse_mode="HTML"), get_win_count)

def get_win_count(m):
    try:
        c = int(m.text.strip())
        admin_setup[m.from_user.id]['win_count'] = c
        gtype = admin_setup[m.from_user.id]['type']
        if gtype == 'number': bot.register_next_step_handler(bot.reply_to(m, "🔢 <b>Phase 5: Send Range</b>\nSend two numbers separated by a hyphen (e.g. 1-500)", parse_mode="HTML"), get_num_range)
        elif gtype == 'code': bot.register_next_step_handler(bot.reply_to(m, "🕵️‍♂️ <b>Phase 5: Send Secret Code</b>\nType the hidden code users need to find (e.g. KURAMA99)", parse_mode="HTML"), get_code_val)
        elif gtype == 'quiz': bot.register_next_step_handler(bot.reply_to(m, "⚡ <b>Phase 5: Send Question & Answer</b>\nSeparate them with `|` (e.g. Who is 7th Hokage? | Naruto)", parse_mode="HTML"), get_quiz_val)
        elif gtype == 'gacha': bot.register_next_step_handler(bot.reply_to(m, "🎰 <b>Phase 5: Max Power Level</b>\nHighest possible spin (e.g. 10000)", parse_mode="HTML"), get_gacha_val)
    except: bot.register_next_step_handler(bot.reply_to(m, "❌ <b>Error!</b> Send a valid number."), get_win_count)

def get_num_range(m):
    try:
        nums = m.text.replace('-', ' ').split()
        admin_setup[m.from_user.id].update({'min': int(nums[0]), 'max': int(nums[1]), 'win_mode': 'auto'})
        bot.register_next_step_handler(bot.reply_to(m, "📢 <b>Phase 6:</b> Forward an announcement post from your Channel or type DONE.", parse_mode="HTML"), get_chans)
    except: bot.register_next_step_handler(bot.reply_to(m, "❌ Range Error! Try again."), get_num_range)

def get_code_val(m):
    admin_setup[m.from_user.id]['secret_code'] = m.text.strip().lower() 
    bot.register_next_step_handler(bot.reply_to(m, "📢 <b>Phase 6:</b> Forward post or type DONE.", parse_mode="HTML"), get_chans)

def get_quiz_val(m):
    if '|' not in m.text: return bot.register_next_step_handler(bot.reply_to(m, "❌ <b>Format Error!</b> Use `|`", parse_mode="HTML"), get_quiz_val)
    q, a = m.text.split('|', 1)
    admin_setup[m.from_user.id].update({'question': q.strip(), 'answer': a.strip().lower()}) 
    bot.register_next_step_handler(bot.reply_to(m, "📢 <b>Phase 6:</b> Forward post or type DONE.", parse_mode="HTML"), get_chans)

def get_gacha_val(m):
    try:
        admin_setup[m.from_user.id]['max_power'] = int(m.text.strip())
        bot.register_next_step_handler(bot.reply_to(m, "📢 <b>Phase 6:</b> Forward post or type DONE.", parse_mode="HTML"), get_chans)
    except: bot.register_next_step_handler(bot.reply_to(m, "❌ Number only!"), get_gacha_val)

def get_chans(m):
    s = admin_setup.get(m.from_user.id)
    if m.text and m.text.upper() == "DONE":
        if not s['chans']: return bot.register_next_step_handler(bot.reply_to(m, "⚠️ Add channel first!"), get_chans)
        btn = InlineKeyboardMarkup().add(InlineKeyboardButton("✅ DEPLOY THE EVENT 🔥", callback_data=f"savegw_{m.from_user.id}"))
        rev = (f"💎 <b>PRE-DEPLOYMENT REVIEW: {s['type'].upper()}</b> 💎\n"
               f"━━━━━━━━━━━━━━━━━━\n"
               f"🎁 <b>Bounty:</b> {safe_html(s['prize'])}\n"
               f"🏆 <b>Slots:</b> {s['win_count']} Winner(s)\n"
               f"⏳ <b>Window:</b> {s['d1']} ➔ {s['d2']}\n"
               f"━━━━━━━━━━━━━━━━━━\n"
               f"<i>All nodes linked. Ready for launch?</i>")
        return bot.reply_to(m, rev, reply_markup=btn, parse_mode="HTML")
    cid = m.forward_from_chat.id if m.forward_from_chat else (int(m.text) if '-100' in m.text else None)
    if cid: s['chans'].append(cid); bot.register_next_step_handler(bot.reply_to(m, f"✅ <b>Channel Linked!</b>\nForward another or type DONE.", parse_mode="HTML"), get_chans)
    else: bot.register_next_step_handler(bot.reply_to(m, "❌ <b>Link Failed!</b>", parse_mode="HTML"), get_chans)

@bot.callback_query_handler(func=lambda c: c.data.startswith('savegw_'))
def finalize_setup(call):
    aid = int(call.data.split('_')[1])
    if call.from_user.id != aid or not admin_setup.get(aid): return
    s = admin_setup[aid]
    gw_code = str(random.randint(1000, 9999))
    while gw_code in active_gws: gw_code = str(random.randint(1000, 9999))
    link = f"https://t.me/{bot.get_me().username}?start=gw_{gw_code}"
    
    gw_data = {
        'code': gw_code, 'type': s['type'], 'host': s.get('host', 'Admin'), 't1': s['t1'], 't2': s['t2'], 's_disp': s['d1'], 'e_disp': s['d2'],
        'prize': s['prize'], 'win_count': s['win_count'], 'link': link, 'chans': s['chans'], 
        'is_running': False, 'is_scheduled': True, 'entries': {}
    }
    if s['type'] == 'number': gw_data.update({'min': s['min'], 'max': s['max'], 'win_mode': 'auto'})
    elif s['type'] == 'code': gw_data.update({'secret_code': s['secret_code']})
    elif s['type'] == 'quiz': gw_data.update({'question': s['question'], 'answer': s['answer']})
    elif s['type'] == 'gacha': gw_data.update({'max_power': s['max_power']})
    
    active_gws[gw_code] = gw_data; save_db(db)
    
    msg = (f"🚀 <b>SYSTEM OVERRIDE: DEPLOYMENT SUCCESSFUL!</b> 🚀\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"<i>Your premium event is now locked and loaded.</i>\n\n"
           f"🆔 <b>Event Code:</b> <code>{gw_code}</code>\n"
           f"🔗 <b>Exclusive Portal Link:</b>\n{link}\n\n"
           f"<i>Share this portal to your network. The arena awaits!</i> 😈")
    try: bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, parse_mode="HTML")
    except Exception: pass
    del admin_setup[aid]

# --- START MENU (VIP UI) ---
@bot.message_handler(commands=['start'])
def welcome(m):
    uid = str(m.from_user.id)
    if is_banned(m.from_user.id): return safe_reply(m, "⛔ <b>SECURITY ALERT:</b> You are permanently blacklisted.")
    init_user(uid)
    args = m.text.split()
    
    if len(args) > 1 and args[1].startswith('ref_'):
        ref_by = args[1].replace('ref_', '')
        if ref_by != uid and uid not in db['users'].get(ref_by, {}).get('refs', []):
            if ref_by in db['users']: 
                db['users'][ref_by]['refs'].append(uid); save_db(db)
                try: bot.send_message(int(ref_by), f"🎉 <b>BOOM! New Recruit!</b>\nSomeone joined using your link. Total: {len(db['users'][ref_by]['refs'])}/{db['settings']['ref_req']}", parse_mode="HTML")
                except: pass

    if len(args) > 1 and args[1].startswith('gw_'):
        c = args[1].split('_')[1]
        if c in active_gws and active_gws[c]['is_running']:
            d = active_gws[c]
            ref_link = f"https://t.me/{bot.get_me().username}?start=ref_{uid}"
            
            if db['settings']['ref_on']:
                req_refs = db['settings']['ref_req']
                ref_count = len(db['users'][uid]['refs'])
                if ref_count < req_refs:
                    if db['settings'].get('ref_type', 'forced') == 'forced': 
                        return safe_reply(m, f"🛑 <b>ACCESS DENIED - REFERRAL REQUIRED!</b> 🛑\n━━━━━━━━━━━━━━━━━━\n<i>You must recruit <b>{req_refs}</b> allies to unlock this premium drop.</i>\n\n📊 <b>Your Progress:</b> {ref_count}/{req_refs}\n🔗 <b>Share this intel:</b>\n<code>{ref_link}</code>")
                    else: 
                        try: bot.send_message(m.chat.id, f"🎁 <b>LUCK MULTIPLIER DETECTED!</b> 🎁\n━━━━━━━━━━━━━━━━━━\n<i>Invite <b>{req_refs}</b> friends to get a <b>3X WINNING CHANCE!</b></i>\n🔗 <b>Your Link:</b>\n<code>{ref_link}</code>", parse_mode="HTML")
                        except: pass
            
            head = f"🔥 <b>VIP MISSION: {d['type'].upper()}</b> 🔥\n━━━━━━━━━━━━━━━━━━\n🎁 <b>BOUNTY:</b> {safe_html(d['prize'])}\n👑 <b>HOST:</b> {d.get('host', 'Admin')}\n"
            
            if d['type'] == 'number':
                kb = InlineKeyboardMarkup().add(InlineKeyboardButton("📊 CHECK AVAILABLE NUMBERS", callback_data=f"gwinfo_{c}"))
                safe_reply(m, f"{head}🎯 <b>OBJECTIVE:</b> Pick a lucky number between <b>{d['min']} and {d['max']}</b>.\n\n<i>Type your number below to lock it in!</i> 👇", reply_markup=kb)
            elif d['type'] == 'code': 
                safe_reply(m, f"{head}🕵️‍♂️ <b>OBJECTIVE:</b> We hid a secret code in the channel. Find it and type it here FAST!\n\n<i>First {d['win_count']} to get it, win!</i> 👇")
            elif d['type'] == 'quiz': 
                safe_reply(m, f"{head}⚡ <b>OBJECTIVE:</b> Answer the question below faster than anyone else!\n❓ <b>Question:</b> <i>{safe_html(d['question'])}</i>\n\n<i>Type your answer below!</i> 👇")
            elif d['type'] == 'gacha':
                kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🎰 CLICK TO SPIN POWER 🎰", callback_data=f"gacha_{c}"))
                safe_reply(m, f"{head}🎰 <b>OBJECTIVE:</b> Tap the spin button to generate your Raw Power Level. Highest power dominates the arena!\n\n<i>(Max Power: {d['max_power']})</i>", reply_markup=kb)
        else: safe_reply(m, "⏳ <b>ERROR:</b> Event is either finished or pending deployment.")
        return
        
    if is_auth(m.from_user.id): 
        safe_reply(m, f"👑 <b>WELCOME BACK, COMMANDER</b> 👑\n━━━━━━━━━━━━━━━━━━\n👤 <b>Agent:</b> {safe_html(m.from_user.first_name)}\n🟢 <b>Status:</b> AUTHORIZED & ONLINE\n\n<i>Access your Control Panel using /vipsetup or deploy a drop via /setgw.</i>")
    else: 
        safe_reply(m, f"🔥 <b>WELCOME TO THE VIP ARENA</b> 🔥\n━━━━━━━━━━━━━━━━━━\nGreetings, <b>{safe_html(m.from_user.first_name)}</b>!\nYou have entered the most exclusive drop zone.\n\n<i>📡 Standby... The next premium event will be deployed soon. Keep notifications ON!</i>")

# --- THE LOGIC ENGINE ---
@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/'))
def handle_text(m):
    uid, uid_str = m.from_user.id, str(m.from_user.id)
    text = m.text.strip().lower() 
    if is_banned(uid): return

    if uid_str in user_captcha:
        if text == str(user_captcha[uid_str]['ans']):
            data = user_captcha.pop(uid_str)
            ghost_reply(m, "✅ <b>SECURITY CLEARED!</b> Locking your entry...")
            process_entry(m, uid, uid_str, data['code'], data['val'])
        else: user_captcha.pop(uid_str); ghost_reply(m, "❌ <b>FAILED!</b> Incorrect verification sequence.")
        return

    for c, d in active_gws.items():
        if not d['is_running'] or str(uid) in [str(u['user_id']) for u in d['entries'].values()]: continue
        match_found, val_to_save = False, text
        
        if d['type'] == 'number' and text.isdigit() and d['min'] <= int(text) <= d['max']:
            if text in d['entries']: return ghost_reply(m, "⚡ <b>TOO LATE!</b> That number was just snatched. Pick another!")
            match_found = True
        elif d['type'] == 'code' and text == d['secret_code']: match_found, val_to_save = True, uid_str
        elif d['type'] == 'quiz' and text == d['answer']: match_found, val_to_save = True, uid_str
        
        if match_found:
            if db['settings']['ref_on'] and db['settings'].get('ref_type', 'forced') == 'forced':
                if len(db['users'].get(uid_str, {}).get('refs', [])) < db['settings']['ref_req']: return ghost_reply(m, "🛑 <b>WAIT!</b> You haven't recruited your squad yet! Check /start")
            
            if db['settings'].get('antibot_on', False):
                a, b = random.randint(1, 10), random.randint(1, 10)
                user_captcha[uid_str] = {'ans': a+b, 'code': c, 'val': val_to_save}
                return ghost_reply(m, f"🛡️ <b>SECURITY CHECKPOINT</b> 🛡️\n\nProve you are human to lock your entry:\n<b>{a} + {b} = ?</b>\n\n<i>Type the answer:</i>")
            
            process_entry(m, uid, uid_str, c, val_to_save)
            return

@bot.callback_query_handler(func=lambda c: c.data.startswith('gacha_'))
def handle_gacha(c):
    code = c.data.split('_')[1]
    uid, uid_str = c.from_user.id, str(c.from_user.id)
    d = active_gws.get(code)
    if not d or not d['is_running'] or d['type'] != 'gacha': return bot.answer_callback_query(c.id, "Event Expired!", show_alert=True)
    if str(uid) in [str(u['user_id']) for u in d['entries'].values()]: return bot.answer_callback_query(c.id, "You already spun!", show_alert=True)
    
    if db['settings']['ref_on'] and db['settings'].get('ref_type', 'forced') == 'forced':
        if len(db['users'].get(uid_str, {}).get('refs', [])) < db['settings']['ref_req']: return bot.answer_callback_query(c.id, "Complete your referrals first!", show_alert=True)
    
    raw_power = random.randint(1, d['max_power'])
    secure_val = f"{raw_power}_{uid_str}"
        
    if db['settings'].get('antibot_on', False):
        a, b = random.randint(1, 10), random.randint(1, 10)
        user_captcha[uid_str] = {'ans': a+b, 'code': code, 'val': secure_val}
        ghost_reply(c.message, f"🛡️ <b>SECURITY CHECKPOINT</b> 🛡️\n\nProve you are human to spin:\n<b>{a} + {b} = ?</b>")
    else: process_entry(c.message, uid, uid_str, code, secure_val, c.from_user.first_name)
    bot.answer_callback_query(c.id)

def process_entry(m, uid, uid_str, code, val, first_name=None):
    d = active_gws.get(code)
    if not d or not d['is_running']: return ghost_reply(m, "❌ Event has already ended.")
    un = get_unjoined(uid)
    fname = first_name or m.from_user.first_name
    if un:
        kb = InlineKeyboardMarkup()
        for i, (cid, data) in enumerate(un.items(), 1): kb.add(InlineKeyboardButton(f"🔗 JOIN NODE {i}", url=data['link'] if isinstance(data, dict) else data))
        kb.add(InlineKeyboardButton("✅ VERIFY CLEARANCE", callback_data=f"v_{code}_{val}"))
        return ghost_reply(m, "🛑 <b>ACCESS DENIED!</b>\n<i>You must join our VIP network first.</i>", kb)
        
    d['entries'][val] = {'user_id': uid, 'name': fname}
    db['users'][uid_str]['participated'] += 1; save_db(db)
    
    if d['type'] == 'number': ghost_reply(m, f"🎯 <b>MISSION ACCOMPLISHED!</b>\nNumber <b>{val}</b> locked in successfully.")
    elif d['type'] in ['code', 'quiz']: ghost_reply(m, f"⚡ <b>FLASH SPEED!</b>\nTarget acquired. Your answer is secured!")
    elif d['type'] == 'gacha': ghost_reply(m, f"🎰 <b>SPIN COMPLETE!</b>\n💥 Your Raw Power Level: <b>{val.split('_')[0]}</b> / {d['max_power']}\n<i>Sit tight for the final rankings!</i>")

    if d['type'] in ['code', 'quiz'] and len(d['entries']) >= d['win_count']: threading.Thread(target=end_logic, args=(code,)).start()

@bot.callback_query_handler(func=lambda c: c.data.startswith('v_'))
def verify_cb(c):
    parts = c.data.split('_', 2)
    code = parts[1]
    val = parts[2]
    uid_str, uid = str(c.from_user.id), c.from_user.id
    if code in active_gws and not get_unjoined(uid):
        if val in active_gws[code]['entries'] and active_gws[code]['type'] == 'number': return bot.answer_callback_query(c.id, "Number got snatched!", show_alert=True)
        active_gws[code]['entries'][val] = {'user_id': uid, 'name': c.from_user.first_name}
        db['users'][uid_str]['participated'] += 1; save_db(db)
        if active_gws[code]['type'] == 'gacha': text = f"🎰 <b>VERIFIED!</b> Your Power is {val.split('_')[0]}"
        else: text = f"🎯 <b>VERIFIED!</b> Entry Locked."
        try: bot.edit_message_text(text, c.message.chat.id, c.message.message_id, parse_mode="HTML")
        except: pass
        threading.Timer(5.0, lambda: bot.delete_message(c.message.chat.id, c.message.message_id)).start()
        
        if active_gws[code]['type'] in ['code', 'quiz'] and len(active_gws[code]['entries']) >= active_gws[code]['win_count']: threading.Thread(target=end_logic, args=(code,)).start()
    else: bot.answer_callback_query(c.id, "You missed a channel! Join all to proceed.", show_alert=True)

# --- AUTO ENGINE (Channel VIP Announcements) ---
def end_logic(code, forced_winner=None):
    d = active_gws.get(code)
    if not d: return
    win_count = d.get('win_count', 1)
    winners = []
    
    entries = list(d['entries'].keys())
    
    if forced_winner and forced_winner in entries:
        winners.append(forced_winner)
        entries.remove(forced_winner)
        
    remaining = win_count - len(winners)
    
    if remaining > 0 and entries:
        if d['type'] in ['code', 'quiz']: 
            winners.extend(entries[:remaining])
        elif d['type'] == 'gacha':
            sorted_ents = sorted(entries, key=lambda x: int(x.split('_')[0]), reverse=True)
            winners.extend(sorted_ents[:remaining])
        elif d['type'] == 'number':
            if d.get('win_mode') == 'manual' and d.get('win_num'):
                for n in d['win_num']:
                    if n in entries and n not in winners: 
                        winners.append(n)
                        entries.remove(n)
                        remaining -= 1
            if remaining > 0 and entries:
                pool = list(entries)
                if db['settings'].get('ref_on', False) and db['settings'].get('ref_type', 'forced') == 'bonus':
                    for n in entries:
                        if len(db['users'].get(str(d['entries'][n]['user_id']), {}).get('refs', [])) >= db['settings']['ref_req']: pool.extend([n, n])
                while remaining > 0 and pool:
                    pick = random.choice(pool)
                    if pick not in winners: winners.append(pick); remaining -= 1
                    pool = [x for x in pool if x != pick]
        
    if winners:
        txt = (f"🚨 <b>DRUMROLL PLEASE... RESULTS ARE IN!</b> 🚨\n"
               f"━━━━━━━━━━━━━━━━━━\n"
               f"🎮 <b>Event Type:</b> {d['type'].upper()}\n"
               f"🎁 <b>Ultimate Prize:</b> {safe_html(d['prize'])}\n"
               f"👑 <b>Host:</b> {d.get('host', 'Admin')}\n"
               f"━━━━━━━━━━━━━━━━━━\n"
               f"🏆 <b>THE CHAMPIONS:</b>\n")
        medals = ['🥇', '🥈', '🥉', '🏅', '🎖']
        for i, w in enumerate(winners):
            medal = medals[i] if i < len(medals) else '🏅'
            u = d['entries'][w]
            db['users'][str(u['user_id'])]['won'] += 1
            if d['type'] == 'gacha': txt += f"{medal} <a href='tg://user?id={u['user_id']}'>{safe_html(u['name'])}</a> (Power: {w.split('_')[0]})\n"
            elif d['type'] == 'number': txt += f"{medal} <a href='tg://user?id={u['user_id']}'>{safe_html(u['name'])}</a> (Lucky No: {w})\n"
            else: txt += f"{medal} <a href='tg://user?id={u['user_id']}'>{safe_html(u['name'])}</a> (Lightning Fast! ⚡)\n"
        txt += "\n<i>🎉 Massive congratulations! Claim your bounty from the Host immediately!</i>"
    else: 
        txt = (f"🚨 <b>EVENT CONCLUDED!</b> 🚨\n"
               f"━━━━━━━━━━━━━━━━━━\n"
               f"🎁 <b>Bounty:</b> {safe_html(d['prize'])}\n"
               f"😔 <b>Status:</b> No Winners this time! The treasure remains unclaimed.\n"
               f"<i>Better luck on the next drop!</i> 🍀")

    for ch in d['chans']: 
        try: bot.send_message(ch, txt, parse_mode="HTML")
        except: pass
    
    if code in active_gws: del active_gws[code]
    save_db(db)

def timer_loop():
    while 1:
        now_str = datetime.now(IST).strftime("%H:%M")
        for c, d in list(active_gws.items()):
            active = is_active(now_str, d['t1'], d['t2'])
            if d['is_scheduled'] and active:
                d['is_running'], d['is_scheduled'] = True, False
                for ch in d['chans']: 
                    try: 
                        btn = InlineKeyboardMarkup().add(InlineKeyboardButton(f"🚀 ENTER THE ARENA 🚀", url=d['link']))
                        msg = (f"🔴 <b>LIVE DROP: {d['type'].upper()} EVENT!</b> 🔴\n"
                               f"━━━━━━━━━━━━━━━━━━\n"
                               f"🎁 <b>Bounty:</b> {safe_html(d['prize'])}\n"
                               f"👑 <b>Host:</b> {d.get('host', 'Admin')}\n"
                               f"🏆 <b>Total Winners:</b> {d['win_count']}\n"
                               f"⏳ <b>Ends At:</b> {d['e_disp']}\n"
                               f"━━━━━━━━━━━━━━━━━━\n"
                               f"👇 <b>CLICK TO PARTICIPATE BEFORE IT'S TOO LATE</b> 👇")
                        bot.send_message(ch, msg, reply_markup=btn, parse_mode="HTML")
                    except: pass
            elif d['is_running'] and not active: end_logic(c)
        time.sleep(15)

@bot.chat_join_request_handler()
def handle_join_request(message: ChatJoinRequest):
    cid, uid = str(message.chat.id), message.from_user.id
    if cid not in db['join_reqs']: db['join_reqs'][cid] = []
    if uid not in db['join_reqs'][cid]: db['join_reqs'][cid].append(uid); save_db(db)

@bot.callback_query_handler(func=lambda c: c.data == 'ignore')
def ignore_cb(c): bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('gwinfo_'))
def gw_info_cb(c):
    code = c.data.split('_')[1]
    if code in active_gws and active_gws[code]['is_running']:
        d = active_gws[code]
        avail = [str(n) for n in range(d['min'], d['max']+1) if str(n) not in d['entries']]
        av_str = ", ".join(avail[:40]) + f" ...(+{len(avail)-40})" if len(avail)>40 else (", ".join(avail) or "None!")
        ghost_reply(c.message, f"📊 <b>AVAILABLE INTEL:</b>\n<code>{av_str}</code>")
        bot.answer_callback_query(c.id)

if __name__ == '__main__':
    threading.Thread(target=timer_loop, daemon=True).start()
    bot.infinity_polling(allowed_updates=['message', 'callback_query', 'chat_join_request'])


