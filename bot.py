import os
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# --- Загрузка переменных окружения ---
BOT_TOKEN = os.environ['BOT_TOKEN']
SPREADSHEET_ID = os.environ['SPREADSHEET_ID']
ADMIN_CHAT_ID = int(os.environ['ADMIN_CHAT_ID'])
SHEET_ORDERS = os.environ.get('SHEET_ORDERS', 'Заказы')
SHEET_EXPENSES = os.environ.get('SHEET_EXPENSES', 'Расходы')

# --- Подключение к Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet_orders = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_ORDERS)
sheet_expenses = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_EXPENSES)

# --- Хранилище диалогов (в памяти) ---
user_data = {}

# --- Обработчики команд ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для учёта заказов.\n\n"
        "📋 Команды:\n"
        "/new_order – добавить заказ\n"
        "/list_orders – список заказов\n"
        "/update_status ID статус – обновить статус\n"
        "/stats – статистика\n"
        "/add_expense сумма описание – добавить расход"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команды: /new_order, /list_orders, /update_status ID статус, /stats, /add_expense сумма описание")

async def new_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data[chat_id] = {'step': 'client'}
    await update.message.reply_text("📝 Введите имя клиента (или ФИО):")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in user_data:
        return
    state = user_data[chat_id]
    step = state['step']
    text = update.message.text

    if step == 'client':
        state['client'] = text
        state['step'] = 'nick'
        await update.message.reply_text("📝 Введите ник (Telegram/Instagram):")
    elif step == 'nick':
        state['nick'] = text
        state['step'] = 'contact'
        await update.message.reply_text("📝 Способ связи (Инст, ТГ, Макс):")
    elif step == 'contact':
        state['contact'] = text
        state['step'] = 'holiday'
        await update.message.reply_text("📝 Дата праздника (в формате ДД.ММ.ГГГГ):")
    elif step == 'holiday':
        state['holiday'] = text
        state['step'] = 'city'
        await update.message.reply_text("📝 Город (Москва, СПб, другой):")
    elif step == 'city':
        state['city'] = text
        state['step'] = 'format'
        await update.message.reply_text("📝 Формат (полный, электронная, самовывоз):")
    elif step == 'format':
        state['format'] = text
        state['step'] = 'status'
        await update.message.reply_text("📝 Статус (переговорка, дизайн, печать, отправлено):")
    elif step == 'status':
        state['status'] = text
        state['step'] = 'paid'
        await update.message.reply_text("📝 Оплачено? (Да / Нет):")
    elif step == 'paid':
        state['paid'] = text
        state['step'] = 'amount'
        await update.message.reply_text("📝 Сумма (1800, 1500 или своя):")
    elif step == 'amount':
        state['amount'] = text
        try:
            amount_value = float(state['amount'].replace(',', '.')) if state['amount'].replace(',', '').replace('.', '').isdigit() else 0
            row = [
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                state.get('client', ''),
                state.get('nick', ''),
                state.get('contact', ''),
                state.get('holiday', ''),
                state.get('city', ''),
                state.get('format', ''),
                state.get('status', ''),
                state.get('paid', ''),
                amount_value
            ]
            sheet_orders.append_row(row)
            await update.message.reply_text("✅ Заказ успешно добавлен!")
            await context.bot.send_message(ADMIN_CHAT_ID, f"🆕 Новый заказ от {state.get('client', 'Неизвестно')} на сумму {state.get('amount', '0')} руб.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка сохранения: {e}")
        del user_data[chat_id]

async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        records = sheet_orders.get_all_values()
        if len(records) <= 1:
            await update.message.reply_text("📭 Заказов пока нет.")
            return
        msg = "📋 Последние 5 заказов:\n"
        start = max(1, len(records)-5)
        for i in range(start, len(records)):
            row = records[i]
            msg += f"ID {i}: {row[1]} – {row[7]} – {row[9]} руб.\n"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def update_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❌ Используйте: /update_status ID статус")
            return
        order_id = int(args[0])
        new_status = ' '.join(args[1:])
        row_num = order_id + 1
        sheet_orders.update_cell(row_num, 8, new_status)
        await update.message.reply_text(f"✅ Статус заказа {order_id} обновлён на '{new_status}'")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        orders = sheet_orders.get_all_values()
        total_revenue = 0
        paid_count = 0
        for row in orders[1:]:
            if len(row) > 8 and row[8].lower() == 'да':
                total_revenue += float(row[9]) if row[9] else 0
                paid_count += 1
        expenses = sheet_expenses.get_all_values()
        total_expenses = 0
        for row in expenses[1:]:
            if len(row) > 2 and row[2]:
                total_expenses += float(row[2]) if row[2] else 0
        profit = total_revenue - total_expenses
        msg = (f"📊 Статистика:\n"
               f"Оплаченных заказов: {paid_count}\n"
               f"Выручка: {total_revenue} руб.\n"
               f"Расходы: {total_expenses} руб.\n"
               f"Прибыль: {profit} руб.")
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❌ Используйте: /add_expense сумма описание")
            return
        amount = float(args[0].replace(',', '.'))
        desc = ' '.join(args[1:])
        row = [datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), desc, amount]
        sheet_expenses.append_row(row)
        await update.message.reply_text(f"✅ Расход {amount} руб. добавлен.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('new_order', new_order))
    app.add_handler(CommandHandler('list_orders', list_orders))
    app.add_handler(CommandHandler('update_status', update_status))
    app.add_handler(CommandHandler('stats', stats))
    app.add_handler(CommandHandler('add_expense', add_expense))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()
