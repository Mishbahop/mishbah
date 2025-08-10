import telebot
from users_db import (
    add_user, set_user_games, get_user, get_all_users,
    update_wallet, set_wallet, update_points, set_points
)
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = '8465757264:AAG9BAqpHkuDyRRmFR6DAjzUzNXpwQmazgU'
ADMIN_IDS = [1905864597]  # Replace with your Telegram user ID(s)

bot = telebot.TeleBot(BOT_TOKEN)

users = set()
user_games = {}  # user_id: set of games (e.g. {"BGMI", "Free Fire"})
tournaments = []
payment_qr = None  # Store file_id of QR code
pending_payments = {}  # user_id: {'utr': ..., 'tournament': ...}
verified_users = {}  # tournament_name: set(user_ids)
refund_requests = {}  # user_id: {'tournament': ..., 'upi': ...}
admin_message_targets = {}  # admin_chat_id: target_user_id

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_user_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        KeyboardButton('📝 Register'),
        KeyboardButton('🏆 Tournaments')
    )
    markup.add(
        KeyboardButton('🎮 Games'),
        KeyboardButton('🎫 My Tournaments')
    )
   
    
    markup.add(
        KeyboardButton('✉️ Contact Admin')
    )
    return markup

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        KeyboardButton('📝 Register'),
        KeyboardButton('🏆 Tournaments')
    )
    markup.add(
        KeyboardButton('🎮 Games'),
        KeyboardButton('🎫 My Tournaments')
    )
    markup.add(
        KeyboardButton('➕ Add Tournament'),
        KeyboardButton('❌ Delete Tournament')
    )
    markup.add(
        KeyboardButton('📢 Broadcast'),
        KeyboardButton('💳 Set Payment QR')
    )
    markup.add(
        KeyboardButton('🧾 Verify Payments'),
        KeyboardButton('✉️ Contact Admin')
    )
    markup.add(
        KeyboardButton('📨 Message User')
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    if is_admin(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "👋 <b>Welcome Admin!</b>\n\n"
            "Use the buttons below to manage tournaments and users.",
            reply_markup=get_admin_keyboard(),
            parse_mode='HTML'
        )
    else:
        bot.send_message(
            message.chat.id,
            "👋 <b>Welcome!</b>\n\n"
            "Use the buttons below to register and view tournaments.",
            reply_markup=get_user_keyboard(),
            parse_mode='HTML'
        )

@bot.message_handler(func=lambda m: m.text in ['📝 Register', '/register'])
def register(message):
    is_new = message.from_user.id not in users
    users.add(message.from_user.id)
    add_user(message.from_user.id, message.from_user.first_name)
    # Alert admin if new user
    if is_new:
        for admin_id in ADMIN_IDS:
            bot.send_message(
                admin_id,
                f"🆕 <b>New user joined!</b>\n"
                f"Name: <a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>\n"
                f"User ID: <code>{message.from_user.id}</code>",
                parse_mode='HTML'
            )
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("BGMI", callback_data="reg_BGMI"),
        InlineKeyboardButton("Free Fire", callback_data="reg_Free Fire")
    )
    bot.send_message(
        message.chat.id,
        "✅ You are registered for tournament updates!\n\n"
        "Which game tournaments do you want notifications for?",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('reg_'))
def select_game_notify(call):
    game = call.data.split('_', 1)[1]
    user_id = call.from_user.id
    user_games.setdefault(user_id, set()).add(game)
    set_user_games(user_id, user_games[user_id])
    bot.answer_callback_query(call.id, f"Registered for {game} tournaments!")
    bot.send_message(call.message.chat.id, f"👍 You will be notified about upcoming {game} tournaments.")

@bot.message_handler(func=lambda m: m.text == '💰 My Wallet')
def my_wallet(message):
    user = get_user(message.from_user.id)
    if user:
        bot.reply_to(message, f"💰 Your wallet balance: ₹{user.get('wallet', 0)}")
    else:
        bot.reply_to(message, "❗ User not found.")

@bot.message_handler(func=lambda m: m.text == '⭐ My Points')
def my_points(message):
    user = get_user(message.from_user.id)
    if user:
        bot.reply_to(message, f"⭐ Your points: {user.get('points', 0)}")
    else:
        bot.reply_to(message, "❗ User not found.")

@bot.message_handler(func=lambda m: m.text == '➕ Deposit')
def deposit(message):
    bot.reply_to(message, "Enter the amount you want to deposit (in ₹):")
    bot.register_next_step_handler(message, deposit_amount)

def deposit_amount(message):
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        bot.reply_to(message, "❗ Please enter a valid positive amount:")
        bot.register_next_step_handler(message, deposit_amount)
        return
    # Show payment QR and ask for UTR
    if payment_qr:
        bot.send_photo(message.chat.id, payment_qr, caption=f"Scan this QR to deposit ₹{amount}.")
    else:
        bot.reply_to(message, "No payment QR set by admin yet. Please try again later.")
        return
    bot.send_message(message.chat.id, "After payment, send your 12-digit UTR (transaction reference) below:")
    bot.register_next_step_handler(message, deposit_utr, amount)

def deposit_utr(message, amount):
    utr = message.text.strip()
    if not (utr.isdigit() and len(utr) == 12):
        bot.reply_to(message, "❗ UTR must be a 12-digit number. Please send again:")
        bot.register_next_step_handler(message, deposit_utr, amount)
        return
    # Notify admin for deposit verification
    for admin_id in ADMIN_IDS:
        bot.send_message(
            admin_id,
            f"💰 <b>Deposit Verification Needed</b>\n"
            f"User: <a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>\n"
            f"Amount: ₹{amount}\n"
            f"UTR: <code>{utr}</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Approve", callback_data=f"depapprove_{message.from_user.id}_{amount}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"depreject_{message.from_user.id}_{amount}")]
            ])
        )
    bot.reply_to(message, "🧾 Deposit UTR received. Please wait for admin verification.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('depapprove_') or call.data.startswith('depreject_'))
def verify_deposit(call):
    parts = call.data.split('_')
    user_id = int(parts[1])
    amount = int(parts[2])
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 Only admin can verify deposits.")
        return
    if call.data.startswith('depapprove_'):
        update_wallet(user_id, amount)
        bot.send_message(user_id, f"✅ Your deposit of ₹{amount} has been added to your wallet!")
        bot.edit_message_text(
            f"✅ Deposit approved for user <code>{user_id}</code> (₹{amount}).",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML'
        )
    else:
        bot.send_message(user_id, f"❌ Your deposit of ₹{amount} was rejected. Please contact admin.")
        bot.edit_message_text(
            f"❌ Deposit rejected for user <code>{user_id}</code> (₹{amount}).",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML'
        )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.text in ['🏆 Tournaments', '/tournaments'])
def tournaments_cmd(message):
    if not tournaments:
        bot.reply_to(message, "😔 No tournaments available right now.")
        return
    msg = "🏆 <b>Upcoming Tournaments:</b>\n\n"
    markup = InlineKeyboardMarkup()
    for idx, t in enumerate(tournaments, 1):
        msg += f"• <b>{t['game']}</b>: {t['name']} | {t['date']} | 💰 {t['prize']}\n"
        markup.add(InlineKeyboardButton(f"Join {t['name']}", callback_data=f"join_{idx-1}"))
    bot.send_message(message.chat.id, msg, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('join_'))
def join_tournament(call):
    idx = int(call.data.split('_')[1])
    t = tournaments[idx]
    user = get_user(call.from_user.id)
    # Try to extract entry fee as integer from prize string
    try:
        entry_fee = int(''.join(filter(str.isdigit, t['prize'])))
    except Exception:
        entry_fee = 0
    if user and user.get('wallet', 0) >= entry_fee and entry_fee > 0:
        # Deduct and join directly
        update_wallet(call.from_user.id, -entry_fee)
        update_points(call.from_user.id, 10)  # Example: add 10 points for joining
        verified_users.setdefault(t['name'], set()).add(call.from_user.id)
        bot.send_message(call.message.chat.id, f"✅ Joined <b>{t['name']}</b> using wallet! ₹{entry_fee} deducted.\n⭐ You earned 10 points.", parse_mode='HTML')
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳 Payment", callback_data=f"pay_{idx}"))
        bot.send_message(
            call.message.chat.id,
            f"To join <b>{t['name']}</b>, please pay the entry fee and submit your UTR after payment.",
            parse_mode='HTML',
            reply_markup=markup
        )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('pay_'))
def payment_option(call):
    idx = int(call.data.split('_')[1])
    t = tournaments[idx]
    if payment_qr:
        bot.send_photo(call.message.chat.id, payment_qr, caption="Scan this QR to pay the entry fee.")
    else:
        bot.send_message(call.message.chat.id, "No payment QR set by admin yet. Please try again later.")
        return
    bot.send_message(call.message.chat.id, "After payment, send your 12-digit UTR (transaction reference) below:")
    bot.register_next_step_handler_by_chat_id(call.message.chat.id, receive_utr, t['name'])
    bot.answer_callback_query(call.id)

def receive_utr(message, tournament_name):
    utr = message.text.strip()
    if not (utr.isdigit() and len(utr) == 12):
        bot.reply_to(message, "❗ UTR must be a 12-digit number. Please send again:")
        bot.register_next_step_handler(message, receive_utr, tournament_name)
        return
    pending_payments[message.from_user.id] = {'utr': utr, 'tournament': tournament_name}
    bot.reply_to(message, f"🧾 UTR received for <b>{tournament_name}</b>.\nPlease wait for admin verification.", parse_mode='HTML')
    # Notify admin
    for admin_id in ADMIN_IDS:
        bot.send_message(
            admin_id,
            f"🧾 <b>New Payment Verification Needed</b>\n"
            f"User: <a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>\n"
            f"Tournament: <b>{tournament_name}</b>\n"
            f"UTR: <code>{utr}</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{message.from_user.id}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"reject_{message.from_user.id}")]
            ])
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_') or call.data.startswith('reject_'))
def verify_utr(call):
    user_id = int(call.data.split('_')[1])
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 Only admin can verify payments.")
        return
    if user_id not in pending_payments:
        bot.answer_callback_query(call.id, "❗ No pending payment for this user.")
        return
    tournament = pending_payments[user_id]['tournament']
    if call.data.startswith('approve_'):
        verified_users.setdefault(tournament, set()).add(user_id)
        update_points(user_id, 10)  # Award points for joining via payment
        bot.send_message(user_id, f"✅ Your payment for <b>{tournament}</b> is verified! You are now added to the tournament.\n⭐ You earned 10 points.", parse_mode='HTML')
        bot.edit_message_text(
            f"✅ Payment approved for user <code>{user_id}</code> in <b>{tournament}</b>.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML'
        )
    else:
        bot.send_message(user_id, f"❌ Your payment for <b>{tournament}</b> was rejected. Please contact admin.", parse_mode='HTML')
        bot.edit_message_text(
            f"❌ Payment rejected for user <code>{user_id}</code> in <b>{tournament}</b>.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML'
        )
    del pending_payments[user_id]
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.text in ['💳 Set Payment QR', '/setqr'])
def set_payment_qr(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 Only admin can set the payment QR.")
        return
    bot.reply_to(message, "Please send the QR code image (as a photo).")
    bot.register_next_step_handler(message, save_qr)

def save_qr(message):
    if not message.photo:
        bot.reply_to(message, "❗ Please send a photo.")
        return
    file_id = message.photo[-1].file_id
    global payment_qr
    payment_qr = file_id
    bot.reply_to(message, "✅ Payment QR code updated!")

@bot.message_handler(func=lambda m: m.text in ['🧾 Verify Payments', '/verifypayments'])
def list_pending_payments(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 Only admin can verify payments.")
        return
    if not pending_payments:
        bot.reply_to(message, "No pending payments.")
        return
    msg = "🧾 <b>Pending Payments:</b>\n\n"
    for uid, info in pending_payments.items():
        msg += f"User: <a href='tg://user?id={uid}'>{uid}</a>\nTournament: <b>{info['tournament']}</b>\nUTR: <code>{info['utr']}</code>\n\n"
    bot.send_message(message.chat.id, msg, parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text in ['🎮 Games', '/games'])
def games(message):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("BGMI", callback_data="game_BGMI"),
        InlineKeyboardButton("Free Fire", callback_data="game_Free Fire")
    )
    bot.send_message(message.chat.id, "🎮 <b>Select a game to view tournaments:</b>", reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('game_'))
def show_game_tournaments(call):
    game = call.data.split('_', 1)[1]
    filtered = [t for t in tournaments if t['game'].lower() == game.lower()]
    if not filtered:
        bot.answer_callback_query(call.id, f"No {game} tournaments available.")
        bot.edit_message_text(
            f"😔 No {game} tournaments available.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        return
    msg = f"🏆 <b>{game} Tournaments:</b>\n\n"
    for idx, t in enumerate(filtered, 1):
        msg += f"• {t['name']} | {t['date']} | 💰 {t['prize']}\n"
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        msg,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda m: m.text in ['➕ Add Tournament', '/addtournament'])
def add_tournament(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 You are not authorized to add tournaments.")
        return
    bot.reply_to(message, "🎯 Enter the game name (e.g., BGMI, Free Fire):")
    bot.register_next_step_handler(message, tournament_step_game)

def tournament_step_game(message):
    game = message.text.strip()
    bot.reply_to(message, "🏆 Enter the tournament name:")
    bot.register_next_step_handler(message, tournament_step_name, game)

def tournament_step_name(message, game):
    name = message.text.strip()
    bot.reply_to(message, "📅 Enter the tournament date (YYYY-MM-DD):")
    bot.register_next_step_handler(message, tournament_step_date, game, name)

def tournament_step_date(message, game, name):
    date = message.text.strip()
    bot.reply_to(message, "💰 Enter the prize amount (e.g., ₹1000):")
    bot.register_next_step_handler(message, tournament_step_prize, game, name, date)

def tournament_step_prize(message, game, name, date):
    prize = message.text.strip()
    bot.reply_to(message, "💵 Enter the entry fee (number only):")
    bot.register_next_step_handler(message, save_tournament, game, name, date, prize)

def save_tournament(message, game, name, date, prize):
    try:
        entry_fee = int(message.text.strip())
    except ValueError:
        bot.reply_to(message, "❗ Please enter a valid number for entry fee.")
        bot.register_next_step_handler(message, save_tournament, game, name, date, prize)
        return
    
    tournaments.append({
        "game": game,
        "name": name,
        "date": date,
        "prize": prize,
        "entry_fee": entry_fee
    })
    
    bot.reply_to(
        message,
        f"✅ Tournament Added:\n\n"
        f"🎯 Game: {game}\n"
        f"🏆 Name: {name}\n"
        f"📅 Date: {date}\n"
        f"💰 Prize: {prize}\n"
        f"💵 Entry Fee: ₹{entry_fee}",
        parse_mode='HTML'
    )
    
    # Notify only relevant users
    for uid in users:
        if game in get_user(uid)["games"]:
            try:
                bot.send_message(
                    uid,
                    f"📢 <b>New {game} Tournament!</b>\n\n"
                    f"🏆 {name}\n"
                    f"📅 Date: {date}\n"
                    f"💰 Prize: {prize}\n"
                    f"💵 Entry Fee: ₹{entry_fee}",
                    parse_mode='HTML'
                )
            except:
                pass

@bot.message_handler(func=lambda m: m.text in ['🏆 Tournaments', '/tournaments'])
def tournaments_cmd(message):
    if not tournaments:
        bot.reply_to(message, "😔 No tournaments available right now.")
        return
    
    for idx, t in enumerate(tournaments):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"Join {t['name']}", callback_data=f"join_{idx}"))
        
        bot.send_message(
            message.chat.id,
            f"🎯 Game: {t['game']}\n"
            f"🏆 Name: {t['name']}\n"
            f"📅 Date: {t['date']}\n"
            f"💰 Prize: {t['prize']}\n"
            f"💵 Entry Fee: ₹{t['entry_fee']}",
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('join_'))
def join_tournament(call):
    idx = int(call.data.split('_')[1])
    t = tournaments[idx]
    user = get_user(call.from_user.id)
    entry_fee = t['entry_fee']

    if user and user.get('wallet', 0) >= entry_fee:
        # Deduct from wallet
        update_wallet(call.from_user.id, -entry_fee)
        update_points(call.from_user.id, 10)
        verified_users.setdefault(t['name'], set()).add(call.from_user.id)
        
        bot.send_message(
            call.message.chat.id,
            f"✅ Joined <b>{t['name']}</b> using wallet! ₹{entry_fee} deducted.\n⭐ You earned 10 points.",
            parse_mode='HTML'
        )
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳 Pay Entry Fee", callback_data=f"pay_{idx}"))
        bot.send_message(
            call.message.chat.id,
            f"To join <b>{t['name']}</b>, please pay ₹{entry_fee} and send your UTR after payment.",
            parse_mode='HTML',
            reply_markup=markup
        )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.text in ['❌ Delete Tournament', '/deletetournament'])
def delete_tournament(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 You are not authorized to delete tournaments.")
        return
    if not tournaments:
        bot.reply_to(message, "😔 No tournaments to delete.")
        return
    markup = InlineKeyboardMarkup()
    for idx, t in enumerate(tournaments):
        btn_text = f"{t['game']} | {t['name']} | {t['date']}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"del_{idx}"))
    bot.send_message(message.chat.id, "❌ <b>Select a tournament to delete:</b>", reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def callback_delete_tournament(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 You are not authorized to delete tournaments.")
        return
    idx = int(call.data.split('_')[1])
    if 0 <= idx < len(tournaments):
        deleted = tournaments.pop(idx)
        bot.answer_callback_query(call.id, "✅ Tournament deleted!")
        bot.edit_message_text(
            f"❌ Deleted: <b>{deleted['game']}</b> | {deleted['name']} | {deleted['date']}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML'
        )
    else:
        bot.answer_callback_query(call.id, "❗ Invalid selection.")

@bot.message_handler(func=lambda m: m.text in ['📢 Broadcast', '/broadcast'])
def broadcast(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 You are not authorized to broadcast.")
        return
    msg = "📢 <b>Send the broadcast message:</b>"
    bot.reply_to(message, msg, parse_mode='HTML')
    bot.register_next_step_handler(message, send_broadcast)

def send_broadcast(message):
    for uid in users:
        try:
            bot.send_message(uid, f"📢 <b>Broadcast:</b>\n{message.text}", parse_mode='HTML')
        except Exception:
            pass
    bot.reply_to(message, "✅ Broadcast sent.")

@bot.message_handler(func=lambda m: m.text in ['🎫 My Tournaments', '/mytournaments'])
def my_tournaments(message):
    user_id = message.from_user.id
    joined = []
    for tname, userset in verified_users.items():
        if user_id in userset:
            joined.append(tname)
    if not joined:
        bot.reply_to(message, "😔 You have no approved tournaments.")
        return
    markup = InlineKeyboardMarkup()
    for tname in joined:
        markup.add(InlineKeyboardButton(f"Cancel {tname}", callback_data=f"cancel_{tname}"))
    bot.send_message(message.chat.id, "🎫 <b>Your Approved Tournaments:</b>", reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_'))
def cancel_tournament(call):
    user_id = call.from_user.id
    tname = call.data.split('_', 1)[1]
    if tname in verified_users and user_id in verified_users[tname]:
        verified_users[tname].remove(user_id)
        bot.answer_callback_query(call.id, "Tournament cancelled. Please send your UPI for refund.")
        bot.send_message(call.message.chat.id, f"❗ Please send your UPI ID for refund for tournament: <b>{tname}</b>", parse_mode='HTML')
        bot.register_next_step_handler(call.message, receive_upi, tname)
    else:
        bot.answer_callback_query(call.id, "You are not in this tournament.")

def receive_upi(message, tname):
    upi = message.text.strip()
    if '@' not in upi:
        bot.reply_to(message, "❗ UPI must contain '@'. Please send a valid UPI ID:")
        bot.register_next_step_handler(message, receive_upi, tname)
        return
    user_id = message.from_user.id
    refund_requests[user_id] = {'tournament': tname, 'upi': upi}
    # Notify admin
    for admin_id in ADMIN_IDS:
        bot.send_message(
            admin_id,
            f"🔄 <b>Refund Request</b>\n"
            f"User: <a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>\n"
            f"Tournament: <b>{tname}</b>\n"
            f"UPI: <code>{upi}</code>",
            parse_mode='HTML'
        )
    bot.reply_to(message, "✅ Refund request sent to admin. You will receive your payment in 20-30 minutes.")

# Contact Admin feature
@bot.message_handler(func=lambda m: m.text == '✉️ Contact Admin')
def contact_admin(message):
    bot.reply_to(message, "✍️ Please type your message for the admin:")
    bot.register_next_step_handler(message, forward_to_admin)

def forward_to_admin(message):
    user = message.from_user
    text = message.text
    for admin_id in ADMIN_IDS:
        bot.send_message(
            admin_id,
            f"📩 <b>Message from user</b> <a href='tg://user?id={user.id}'>{user.first_name}</a> (<code>{user.id}</code>):\n\n{text}",
            parse_mode='HTML'
        )
    bot.reply_to(message, "✅ Your message has been sent to the admin. You will get a reply soon.")

# Admin: Send message to user by user ID
@bot.message_handler(func=lambda m: m.text == '📨 Message User')
def admin_message_user(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 Only admin can use this feature.")
        return
    bot.reply_to(message, "Please enter the user ID you want to message:")
    bot.register_next_step_handler(message, get_user_id_for_message)

def get_user_id_for_message(message):
    if not is_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text.strip())
    except ValueError:
        bot.reply_to(message, "❗ Invalid user ID. Please enter a numeric user ID:")
        bot.register_next_step_handler(message, get_user_id_for_message)
        return
    admin_message_targets[message.chat.id] = user_id  # Store in global dict
    bot.reply_to(message, "Now type the message you want to send to this user:")
    bot.register_next_step_handler(message, send_admin_message_to_user)

def send_admin_message_to_user(message):
    if not is_admin(message.from_user.id):
        return
    user_id = admin_message_targets.get(message.chat.id)
    if not user_id:
        bot.reply_to(message, "❗ User ID not found. Please start again.")
        return
    text = message.text
    try:
        bot.send_message(user_id, f"📩 <b>Message from Admin:</b>\n\n{text}", parse_mode='HTML')
        bot.reply_to(message, "✅ Message sent to user.")
    except Exception as e:
        bot.reply_to(message, f"❗ Failed to send message: {e}")
    admin_message_targets.pop(message.chat.id, None)

bot.polling()
