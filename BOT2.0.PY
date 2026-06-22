import telebot
from telebot import types
import sqlite3
import schedule
import time
import threading
import os
from datetime import datetime, timedelta

# Токен из переменных окружения (для Railway)
BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

# ============================================
# БАЗА ДАННЫХ (все связи между таблицами)
# ============================================
def init_db():
    conn = sqlite3.connect('restbank.db')
    cursor = conn.cursor()
    
    # Таблица пользователей (основная)
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY,
                       username TEXT,
                       balance INTEGER DEFAULT 0,
                       passes INTEGER DEFAULT 3,
                       start_hour INTEGER DEFAULT 23,
                       amount_per_interval INTEGER DEFAULT 20,
                       interval_minutes INTEGER DEFAULT 30,
                       streak_days INTEGER DEFAULT 0,
                       last_active_date TEXT,
                       goal_amount INTEGER DEFAULT 0,
                       goal_name TEXT DEFAULT '',
                       emergency_mode INTEGER DEFAULT 0,
                       emergency_until TEXT,
                       pet_level INTEGER DEFAULT 1,
                       created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица транзакций (связь с users через user_id)
    cursor.execute('''CREATE TABLE IF NOT EXISTS transactions
                      (id INTEGER PRIMARY KEY AUTOINCREMENT,
                       user_id INTEGER,
                       amount INTEGER,
                       type TEXT,  -- 'earn' или 'spend'
                       description TEXT,
                       timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                       FOREIGN KEY (user_id) REFERENCES users(user_id))''')
    
    # Таблица достижений (связь с users через user_id)
    cursor.execute('''CREATE TABLE IF NOT EXISTS achievements
                      (id INTEGER PRIMARY KEY AUTOINCREMENT,
                       user_id INTEGER,
                       achievement_name TEXT,
                       unlocked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                       FOREIGN KEY (user_id) REFERENCES users(user_id))''')
    
    # Таблица друзей (связь users-users)
    cursor.execute('''CREATE TABLE IF NOT EXISTS friends
                      (id INTEGER PRIMARY KEY AUTOINCREMENT,
                       user_id INTEGER,
                       friend_id INTEGER,
                       added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                       FOREIGN KEY (user_id) REFERENCES users(user_id),
                       FOREIGN KEY (friend_id) REFERENCES users(user_id))''')
    
    conn.commit()
    conn.close()

init_db()

# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================
def get_user(user_id):
    conn = sqlite3.connect('restbank.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user(user_id, **kwargs):
    conn = sqlite3.connect('restbank.db')
    cursor = conn.cursor()
    for key, value in kwargs.items():
        cursor.execute(f'UPDATE users SET {key} = ? WHERE user_id = ?', (value, user_id))
    conn.commit()
    conn.close()

def add_transaction(user_id, amount, type, description):
    conn = sqlite3.connect('restbank.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)',
                   (user_id, amount, type, description))
    conn.commit()
    conn.close()

def check_achievements(user_id):
    """Проверяет и выдаёт достижения"""
    user = get_user(user_id)
    if not user:
        return
    
    balance = user[2]
    streak = user[7]
    
    achievements_to_check = [
        (balance >= 100, "Первые 100₽", "Накопил первые 100₽ в копилке!"),
        (balance >= 500, "Полтинник", "Накопил 500₽ — ты мастер отдыха!"),
        (streak >= 7, "Неделя без скроллинга", "7 дней подряд ложишься вовремя! 🔥"),
        (streak >= 30, "Мастер сна", "30 дней без ночного скроллинга! 🏆"),
    ]
    
    for condition, name, message in achievements_to_check:
        if condition:
            conn = sqlite3.connect('restbank.db')
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM achievements WHERE user_id = ? AND achievement_name = ?',
                          (user_id, name))
            if not cursor.fetchone():
                cursor.execute('INSERT INTO achievements (user_id, achievement_name) VALUES (?, ?)',
                              (user_id, name))
                conn.commit()
                bot.send_message(user_id, f"🏆 Достижение разблокировано: {name}!\n{message}")
            conn.close()

def update_streak(user_id):
    """Обновляет стрик (серию дней)"""
    user = get_user(user_id)
    if not user:
        return
    
    today = datetime.now().date()
    last_active = user[8]
    
    if last_active:
        last_date = datetime.strptime(last_active, '%Y-%m-%d').date()
        if last_date == today - timedelta(days=1):
            # Вчера был активен — увеличиваем стрик
            update_user(user_id, streak_days=user[7] + 1, last_active_date=today.isoformat())
        elif last_date < today - timedelta(days=1):
            # Пропустил день — сбрасываем стрик
            update_user(user_id, streak_days=1, last_active_date=today.isoformat())
    else:
        # Первый раз
        update_user(user_id, streak_days=1, last_active_date=today.isoformat())

def get_pet_emoji(level):
    """Возвращает эмодзи питомца в зависимости от уровня"""
    pets = {
        1: "🐷 Малыш",
        2: "🐖 Подросток",
        3: "🐗 Взрослый",
        4: "🦄 Единорог"
    }
    return pets.get(level, "🐷 Малыш")

def update_pet_level(user_id):
    """Обновляет уровень питомца в зависимости от баланса"""
    user = get_user(user_id)
    if not user:
        return
    
    balance = user[2]
    if balance >= 500:
        level = 4
    elif balance >= 300:
        level = 3
    elif balance >= 100:
        level = 2
    else:
        level = 1
    
    update_user(user_id, pet_level=level)

# ============================================
# КОМАНДЫ БОТА
# ============================================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    if not get_user(user_id):
        conn = sqlite3.connect('restbank.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (user_id, username) VALUES (?, ?)', (user_id, username))
        conn.commit()
        conn.close()
    
    bot.send_message(message.chat.id, 
                     "Привет! Я твой помощник по борьбе с ночным скроллингом 🐷\n\n"
                     "Я буду писать тебе ночью и предлагать списать деньги в копилку отдыха. "
                     "Эти деньги не пропадают — ты сможешь потратить их на кофе, кино или прогулку!\n\n"
                     "Команды:\n"
                     "/balance — посмотреть баланс\n"
                     "/settings — настроить параметры\n"
                     "/shop — потратить накопленное\n"
                     "/goal — установить цель накопления\n"
                     "/stats — статистика\n"
                     "/session — экстренный режим (на время сессии)\n"
                     "/achievements — мои достижения")

@bot.message_handler(commands=['balance'])
def balance(message):
    user = get_user(message.from_user.id)
    if user:
        balance = user[2]
        passes = user[3]
        streak = user[7]
        goal_amount = user[9]
        goal_name = user[10]
        pet_level = user[13]
        
        pet = get_pet_emoji(pet_level)
        
        text = f"🐷 Твоя копилка: {balance}₽\n"
        text += f"🎟 Пропусков осталось: {passes}\n"
        text += f"🔥 Стрик: {streak} дней\n"
        text += f"🐾 Питомец: {pet}\n"
        
        if goal_amount > 0:
            progress = min(100, int((balance / goal_amount) * 100))
            text += f"\n🎯 Цель: {goal_name} ({goal_amount}₽)\n"
            text += f"Прогресс: {balance}/{goal_amount}₽ ({progress}%)"
        
        bot.send_message(message.chat.id, text)
    else:
        bot.send_message(message.chat.id, "Сначала нажми /start")

@bot.message_handler(commands=['settings'])
def settings(message):
    user = get_user(message.from_user.id)
    if user:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"⏰ Время начала: {user[4]}:00", callback_data="set_time"),
            types.InlineKeyboardButton(f"💰 Сумма: {user[5]}₽", callback_data="set_amount"),
            types.InlineKeyboardButton(f"🎟 Пропуски: {user[3]}", callback_data="set_passes"),
            types.InlineKeyboardButton(f"⏱ Интервал: {user[6]} мин", callback_data="set_interval")
        )
        bot.send_message(message.chat.id, "Настройки:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_'))
def settings_callback(call):
    if call.data == 'set_time':
        markup = types.InlineKeyboardMarkup(row_width=3)
        for hour in range(20, 24):
            markup.add(types.InlineKeyboardButton(f"{hour}:00", callback_data=f"time_{hour}"))
        bot.send_message(call.message.chat.id, "Выбери время начала режима:", reply_markup=markup)
    elif call.data == 'set_amount':
        markup = types.InlineKeyboardMarkup(row_width=2)
        for amount in [10, 20, 30, 50]:
            markup.add(types.InlineKeyboardButton(f"{amount}₽", callback_data=f"amount_{amount}"))
        bot.send_message(call.message.chat.id, "Выбери сумму списания:", reply_markup=markup)
    elif call.data == 'set_passes':
        markup = types.InlineKeyboardMarkup(row_width=2)
        for passes in [1, 3, 5, 7]:
            markup.add(types.InlineKeyboardButton(f"{passes}", callback_data=f"passes_{passes}"))
        bot.send_message(call.message.chat.id, "Выбери количество пропусков в неделю:", reply_markup=markup)
    elif call.data.startswith('time_'):
        hour = int(call.data.split('_')[1])
        update_user(call.from_user.id, start_hour=hour)
        bot.answer_callback_query(call.id, f"Время установлено на {hour}:00!")
    elif call.data.startswith('amount_'):
        amount = int(call.data.split('_')[1])
        update_user(call.from_user.id, amount_per_interval=amount)
        bot.answer_callback_query(call.id, f"Сумма установлена на {amount}₽!")
    elif call.data.startswith('passes_'):
        passes = int(call.data.split('_')[1])
        update_user(call.from_user.id, passes=passes)
        bot.answer_callback_query(call.id, f"Пропуски установлены на {passes}!")

@bot.message_handler(commands=['shop'])
def shop(message):
    user = get_user(message.from_user.id)
    if user:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("☕ Кофе в Biofood (20 ₽)", callback_data="spend_20"),
            types.InlineKeyboardButton("🎬 Билет в кино (100 ₽)", callback_data="spend_100"),
            types.InlineKeyboardButton("🌊 Прогулка по набережной (0 ₽)", callback_data="spend_0")
        )
        bot.send_message(message.chat.id, "На что потратим накопленное?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('spend_'))
def spend_callback(call):
    amount = int(call.data.split('_')[1])
    user = get_user(call.from_user.id)
    
    if user[2] < amount:
        bot.answer_callback_query(call.id, "Недостаточно средств в копилке! 😔", show_alert=True)
        return
    
    update_user(call.from_user.id, balance=user[2] - amount)
    add_transaction(call.from_user.id, -amount, 'spend', 'Покупка в магазине')
    update_pet_level(call.from_user.id)
    
    bot.answer_callback_query(call.id, "Успешно потрачено!", show_alert=True)
    bot.send_message(call.message.chat.id, f"Отлично! Ты потратил {amount}₽. Приятного отдыха! 🎬🌊")

@bot.message_handler(commands=['goal'])
def goal(message):
    bot.send_message(message.chat.id, "Введи название цели и сумму через пробел.\nПример: Концерт 500")

@bot.message_handler(func=lambda message: True)
def handle_goal(message):
    user = get_user(message.from_user.id)
    if user and user[9] == 0:  # Если цель не установлена
        parts = message.text.split()
        if len(parts) >= 2:
            goal_name = ' '.join(parts[:-1])
            goal_amount = int(parts[-1])
            update_user(message.from_user.id, goal_name=goal_name, goal_amount=goal_amount)
            bot.send_message(message.chat.id, f"🎯 Цель установлена: {goal_name} ({goal_amount}₽)")
        else:
            bot.send_message(message.chat.id, "Неправильный формат. Пример: Концерт 500")

@bot.message_handler(commands=['stats'])
def stats(message):
    user = get_user(message.from_user.id)
    if user:
        conn = sqlite3.connect('restbank.db')
        cursor = conn.cursor()
        
        # Общая сумма заработано
        cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = ?',
                      (message.from_user.id, 'earn'))
        total_earned = cursor.fetchone()[0] or 0
        
        # Количество транзакций
        cursor.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ?',
                      (message.from_user.id,))
        total_transactions = cursor.fetchone()[0]
        
        conn.close()
        
        text = f"📊 Твоя статистика:\n"
        text += f"💰 Всего заработано: {total_earned}₽\n"
        text += f"🔥 Стрик: {user[7]} дней\n"
        text += f"📝 Транзакций: {total_transactions}\n"
        text += f"🐾 Уровень питомца: {user[13]}"
        
        bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['session'])
def session(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("7 дней", callback_data="session_7"),
        types.InlineKeyboardButton("14 дней", callback_data="session_14"),
        types.InlineKeyboardButton("30 дней", callback_data="session_30"),
        types.InlineKeyboardButton("Отменить режим", callback_data="session_0")
    )
    bot.send_message(message.chat.id, "Экстренный режим (сессия/дедлайны). На сколько дней отключить бота?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('session_'))
def session_callback(call):
    days = int(call.data.split('_')[1])
    if days == 0:
        update_user(call.from_user.id, emergency_mode=0, emergency_until=None)
        bot.answer_callback_query(call.id, "Экстренный режим отключён!")
    else:
        until = (datetime.now() + timedelta(days=days)).isoformat()
        update_user(call.from_user.id, emergency_mode=1, emergency_until=until)
        bot.answer_callback_query(call.id, f"Экстренный режим включён на {days} дней!")
    bot.send_message(call.message.chat.id, f"Режим обновлён. До {'отключения' if days == 0 else until[:10]}")

@bot.message_handler(commands=['achievements'])
def achievements(message):
    conn = sqlite3.connect('restbank.db')
    cursor = conn.cursor()
    cursor.execute('SELECT achievement_name, unlocked_at FROM achievements WHERE user_id = ?',
                  (message.from_user.id,))
    achs = cursor.fetchall()
    conn.close()
    
    if achs:
        text = "🏆 Твои достижения:\n\n"
        for name, date in achs:
            text += f"✅ {name} ({date[:10]})\n"
        bot.send_message(message.chat.id, text)
    else:
        bot.send_message(message.chat.id, "Пока нет достижений. Копи больше и ложишься вовремя! 💪")

# ============================================
# НОЧНОЙ ТРИГГЕР
# ============================================
def night_check():
    current_hour = datetime.now().hour
    conn = sqlite3.connect('restbank.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, start_hour, passes, emergency_mode, emergency_until, amount_per_interval FROM users')
    users = cursor.fetchall()
    conn.close()

    for user in users:
        user_id, start_hour, passes, emergency_mode, emergency_until, amount = user
        
        # Проверяем экстренный режим
        if emergency_mode and emergency_until:
            until_date = datetime.fromisoformat(emergency_until)
            if datetime.now() < until_date:
                continue  # Пропускаем пользователя в экстренном режиме
        
        if current_hour >= start_hour:
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton(f"💰 Списать {amount}₽ в копилку", callback_data="add_money"),
                types.InlineKeyboardButton("😴 Я уже сплю", callback_data="sleep"),
                types.InlineKeyboardButton(f"🎟 Использовать пропуск ({passes} ост.)", callback_data="use_pass")
            )
            
            try:
                bot.send_message(user_id, 
                                f"🌙 Эй, ты ещё не спишь? Сейчас {current_hour}:00. "
                                f"Списать {amount}₽ в копилку отдыха?", 
                                reply_markup=markup)
            except:
                pass

@bot.callback_query_handler(func=lambda call: call.data == 'add_money')
def add_money_callback(call):
    user = get_user(call.from_user.id)
    amount = user[5]
    
    update_user(call.from_user.id, balance=user[2] + amount)
    add_transaction(call.from_user.id, amount, 'earn', 'Ночное списание')
    update_streak(call.from_user.id)
    update_pet_level(call.from_user.id)
    check_achievements(call.from_user.id)
    
    bot.answer_callback_query(call.id, f"+{amount}₽ в копилку!", show_alert=True)
    bot.send_message(call.message.chat.id, f"Окей, +{amount}₽! Копилка растет. Ложись спать! 🐷")

@bot.callback_query_handler(func=lambda call: call.data == 'sleep')
def sleep_callback(call):
    update_streak(call.from_user.id)
    check_achievements(call.from_user.id)
    
    bot.answer_callback_query(call.id, "Спокойной ночи!", show_alert=True)
    bot.send_message(call.message.chat.id, "Отлично! Сладких снов 🌙✨")

@bot.callback_query_handler(func=lambda call: call.data == 'use_pass')
def pass_callback(call):
    user = get_user(call.from_user.id)
    if user[3] > 0:
        update_user(call.from_user.id, passes=user[3] - 1)
        bot.answer_callback_query(call.id, "Пропуск использован!", show_alert=True)
        bot.send_message(call.message.chat.id, "Понял, работаешь? Окей, сегодня без списаний. 😉")
    else:
        bot.answer_callback_query(call.id, "Пропуски закончились!", show_alert=True)

# ============================================
# ПЛАНИРОВЩИК
# ============================================
def run_scheduler():
    schedule.every().day.at("23:00").do(night_check)
    schedule.every().day.at("23:30").do(night_check)
    schedule.every().day.at("00:00").do(night_check)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == '__main__':
    threading.Thread(target=run_scheduler, daemon=True).start()
    print("Бот запущен!")
    bot.infinity_polling(skip_pending=True)