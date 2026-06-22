import telebot
from telebot import types
import sqlite3
import schedule
import time
import threading
from datetime import datetime

# ВСТАВЬ СЮДА СВОЙ ТОКЕН ОТ BOTFATHER
import os
BOT_TOKEN = os.environ.get('BOT_TOKEN')

bot = telebot.TeleBot(BOT_TOKEN)

# --- НАСТРОЙКА БАЗЫ ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect('restbank.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, 
                       balance INTEGER DEFAULT 0, 
                       passes INTEGER DEFAULT 3, 
                       start_hour INTEGER DEFAULT 23)''')
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect('restbank.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_balance(user_id, amount):
    conn = sqlite3.connect('restbank.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def use_pass(user_id):
    conn = sqlite3.connect('restbank.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET passes = passes - 1 WHERE user_id = ? AND passes > 0', (user_id,))
    conn.commit()
    conn.close()

# --- КОМАНДЫ БОТА ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if not get_user(user_id):
        conn = sqlite3.connect('restbank.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
    
    bot.send_message(message.chat.id, 
                     "Привет! Я твой помощник по борьбе с ночным скроллингом 🐷\n\n"
                     "По умолчанию я буду писать тебе в 23:00. Если ты не спишь — я буду списывать 20₽ в твою виртуальную копилку отдыха.\n\n"
                     "Жми /balance, чтобы проверить баланс, или /shop, чтобы потратить накопленное!")

@bot.message_handler(commands=['balance'])
def balance(message):
    user = get_user(message.from_user.id)
    if user:
        bot.send_message(message.chat.id, f"🐷 В твоей копилке сейчас: {user[1]} ₽\n🎟 Бесплатных пропусков осталось: {user[2]}")
    else:
        bot.send_message(message.chat.id, "Сначала нажми /start")

@bot.message_handler(commands=['shop'])
def shop(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn1 = types.InlineKeyboardButton("☕ Кофе в Biofood (20 ₽)", callback_data="spend_20")
    btn2 = types.InlineKeyboardButton("🎬 Билет в кино (100 ₽)", callback_data="spend_100")
    btn3 = types.InlineKeyboardButton("🌊 Прогулка по набережной (0 ₽)", callback_data="spend_0")
    markup.add(btn1, btn2, btn3)
    bot.send_message(message.chat.id, "На что потратим накопленное?", reply_markup=markup)

# --- ОБРАБОТКА КНОПОК МАГАЗИНА ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('spend_'))
def spend_callback(call):
    amount = int(call.data.split('_')[1])
    user = get_user(call.from_user.id)
    
    if user[1] < amount:
        bot.answer_callback_query(call.id, "Недостаточно средств в копилке! 😔", show_alert=True)
        return
        
    update_balance(call.from_user.id, -amount)
    bot.answer_callback_query(call.id, "Успешно потрачено!", show_alert=True)
    bot.send_message(call.message.chat.id, f"Отлично! Ты потратил {amount}₽. Приятного отдыха! 🎬🌊")

# --- НОЧНОЙ ТРИГГЕР (Планировщик) ---
def night_check():
    current_hour = datetime.now().hour
    # Проверяем всех пользователей (в реальном боте тут был бы цикл по БД)
    # Для теста мы просто эмулируем проверку для конкретного юзера, если он есть
    conn = sqlite3.connect('restbank.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, start_hour, passes FROM users')
    users = cursor.fetchall()
    conn.close()

    for user in users:
        user_id, start_hour, passes = user
        if current_hour >= start_hour:
            markup = types.InlineKeyboardMarkup(row_width=1)
            btn1 = types.InlineKeyboardButton(" Да, списать 20₽ в копилку", callback_data="add_20")
            btn2 = types.InlineKeyboardButton("😴 Я уже сплю", callback_data="sleep")
            btn3 = types.InlineKeyboardButton(f"🎟 Использовать пропуск ({passes} ост.)", callback_data="use_pass")
            markup.add(btn1, btn2, btn3)
            
            try:
                bot.send_message(user_id, f"🌙 Эй, ты ещё не спишь? Сейчас {current_hour}:00. Списать 20₽ в копилку отдыха?", reply_markup=markup)
            except:
                pass # Если юзер заблокировал бота

def add_money_callback(call):
    update_balance(call.from_user.id, 20)
    bot.answer_callback_query(call.id, "+20₽ в копилку!", show_alert=True)
    bot.send_message(call.message.chat.id, "Окей, +20₽! Копилка растет. Ложись спать, завтра на кофе накопишь! 🐷")

def sleep_callback(call):
    bot.answer_callback_query(call.id, "Спокойной ночи!", show_alert=True)
    bot.send_message(call.message.chat.id, "Отлично! Сладких снов 🌙✨")

def pass_callback(call):
    user = get_user(call.from_user.id)
    if user[2] > 0:
        use_pass(call.from_user.id)
        bot.answer_callback_query(call.id, "Пропуск использован!", show_alert=True)
        bot.send_message(call.message.chat.id, "Понял, работаешь? Окей, сегодня без списаний. Но не злоупотребляй! 😉")
    else:
        bot.answer_callback_query(call.id, "Пропуски закончились!", show_alert=True)

bot.callback_query_handler(func=lambda call: call.data == 'add_20')(add_money_callback)
bot.callback_query_handler(func=lambda call: call.data == 'sleep')(sleep_callback)
bot.callback_query_handler(func=lambda call: call.data == 'use_pass')(pass_callback)

# --- ЗАПУСК ПЛАНИРОВЩИКА В ФОНЕ ---
def run_scheduler():
    # Бот будет проверять время каждый день в 23:00 и в 23:30
    schedule.every().day.at("23:00").do(night_check)
    schedule.every().day.at("23:30").do(night_check)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    # Запускаем планировщик в отдельном потоке
    threading.Thread(target=run_scheduler, daemon=True).start()
    print("Бот запущен! Жду сообщений...")
    # Запускаем самого бота
    bot.infinity_polling(skip_pending=True)