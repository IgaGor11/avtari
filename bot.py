import os
import datetime
import asyncio
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# ============================================
#  КОНФИГУРАЦИЯ
# ============================================

BOT_TOKEN = os.environ['BOT_TOKEN']
SPREADSHEET_ID = os.environ['SPREADSHEET_ID']
ADMIN_CHAT_ID = int(os.environ['ADMIN_CHAT_ID'])
SHEET_ORDERS = os.environ.get('SHEET_ORDERS', 'Заказы')
SHEET_EXPENSES = os.environ.get('SHEET_EXPENSES', 'Расходы')

# Подключение к Google Sheets (один раз)
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet_orders = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_ORDERS)
sheet_expenses = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_EXPENSES)

# ============================================
#  БОТ
# ============================================

app = ApplicationBuilder().token(BOT_TOKEN).build()

user_data = {}

# Клавиатуры
main_keyboard = ReplyKeyboardMarkup(
    [
        ["📦 Новый заказ", "📋 Список заказов"],
        ["📊 Статистика", "💰 Добавить расход"],
        ["❓ Помощь"]
    ],
    resize_keyboard=True
)

filter_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📌 Все", callback_data="filter_all")],
    [InlineKeyboardButton("🟢 Переговорка", callback_data="status_переговорка"),
     InlineKeyboardButton("🟡 Дизайн", callback_data="status_дизайн")],
    [InlineKeyboardButton("🔵 Печать", callback_data="status_печать"),
     InlineKeyboardButton("✅ Отправлено", callback_data="status_отправлено")],
    [InlineKeyboardButton("💰 Оплачено", callback_data="paid_да"),
     InlineKeyboardButton("❌ Не оплачено", callback_data="paid_нет")],
    [InlineKeyboardButton("🔙 Отмена", callback_data="cancel_filter")]
])

def pagination_keyboard(page, total_pages):
    buttons = []
    if total_pages > 1:
        row = []
        if page > 1:
            row.append(InlineKeyboardButton("◀️", callback_data=f"page_{page-1}"))
        row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            row.append(InlineKeyboardButton("▶️", callback_data=f"page_{page+1}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="cancel_filter")])
    return InlineKeyboardMarkup(buttons)

# ============================================
#  ОБРАБОТЧИКИ
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для учёта заказов.\n\n"
        "Выберите действие из меню ниже 👇",
        reply_markup=main_keyboard
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 *Доступные действия:*\n"
        "• /new_order – добавить заказ\n"
        "• /list_orders – список заказов (с фильтрами)\n"
        "• /stats – статистика\n"
        "• /add_expense сумма описание – добавить расход\n\n"
        "Также вы можете использовать кнопки меню.",
        parse_mode="Markdown"
    )

async def new_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data[chat_id] = {'step': 'client'}
    await update.message.reply_text("📝 Введите *имя клиента* (или ФИО):", parse_mode="Markdown")

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
        await update.message.reply_text("📝 Введите *ник* (Telegram/Instagram):", parse_mode="Markdown")
    elif step == 'nick':
        state['nick'] = text
        state['step'] = 'contact'
        await update.message.reply_text("📝 *Способ связи* (Инст, ТГ, Макс):", parse_mode="Markdown")
    elif step == 'contact':
        state['contact'] = text
        state['step'] = 'holiday'
        await update.message.reply_text("📝 *Дата праздника* (в формате ДД.ММ.ГГГГ):", parse_mode="Markdown")
    elif step == 'holiday':
        state['holiday'] = text
        state['step'] = 'city'
        await update.message.reply_text("📝 *Город* (Москва, СПб, другой):", parse_mode="Markdown")
    elif step == 'city':
        state['city'] = text
        state['step'] = 'format'
        await update.message.reply_text("📝 *Формат* (полный, электронная, самовывоз):", parse_mode="Markdown")
    elif step == 'format':
        state['format'] = text
        state['step'] = 'status'
        await update.message.reply_text("📝 *Статус* (переговорка, дизайн, печать, отправлено):", parse_mode="Markdown")
    elif step == 'status':
        state['status'] = text
        state['step'] = 'paid'
        await update.message.reply_text("📝 *Оплачено?* (Да / Нет):", parse_mode="Markdown")
    elif step == 'paid':
        state['paid'] = text
        state['step'] = 'amount'
        await update.message.reply_text("📝 *Сумма* (1800, 1500 или своя):", parse_mode="Markdown")
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
            await update.message.reply_text("✅ *Заказ успешно добавлен!*", parse_mode="Markdown")
            await context.bot.send_message(ADMIN_CHAT_ID, f"🆕 *Новый заказ* от {state.get('client', 'Неизвестно')} на сумму {state.get('amount', '0')} руб.")
        except Exception as e:
            await update.message.reply_text(f"❌ *Ошибка сохранения:* {e}", parse_mode="Markdown")
        del user_data[chat_id]
        await update.message.reply_text("Главное меню:", reply_markup=main_keyboard)

async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 *Выберите фильтр для списка заказов:*",
        reply_markup=filter_keyboard,
        parse_mode="Markdown"
    )
    context.user_data['filter'] = None
    context.user_data['page'] = 1

async def filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel_filter":
        await query.edit_message_text("❌ Фильтр отменён.", reply_markup=None)
        return

    if data.startswith("status_"):
        status = data.split("_", 1)[1]
        context.user_data['filter'] = ('status', status)
    elif data.startswith("paid_"):
        paid = data.split("_", 1)[1]
        context.user_data['filter'] = ('paid', paid)
    elif data == "filter_all":
        context.user_data['filter'] = None
    elif data.startswith("page_"):
        page = int(data.split("_")[1])
        context.user_data['page'] = page
        await show_orders_page(update, context)
        return
    else:
        return

    context.user_data['page'] = 1
    await show_orders_page(update, context)

async def show_orders_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    page = context.user_data.get('page', 1)
    filter_type = context.user_data.get('filter')

    try:
        records = sheet_orders.get_all_values()
        if len(records) <= 1:
            await query.edit_message_text("📭 *Заказов пока нет.*", parse_mode="Markdown")
            return

        data_rows = records[1:]
        filtered = []
        for row in data_rows:
            if filter_type:
                key, value = filter_type
                if key == 'status':
                    if len(row) > 7 and row[7].lower() == value.lower():
                        filtered.append(row)
                elif key == 'paid':
                    if len(row) > 8 and row[8].lower() == value.lower():
                        filtered.append(row)
            else:
                filtered.append(row)

        if not filtered:
            await query.edit_message_text("📭 *Нет заказов, соответствующих фильтру.*", parse_mode="Markdown")
            return

        total = len(filtered)
        total_pages = (total + 4) // 5
        start = (page - 1) * 5
        end = min(start + 5, total)
        page_rows = filtered[start:end]

        msg = f"📋 *Список заказов* (стр. {page}/{total_pages})\n\n"
        for idx, row in enumerate(page_rows, start=start+1):
            status_emoji = {
                "переговорка": "🟢",
                "дизайн": "🟡",
                "печать": "🔵",
                "отправлено": "✅"
            }.get(row[7].lower() if len(row)>7 else "", "⚪")
            paid_emoji = "💰" if len(row)>8 and row[8].lower() == "да" else "❌"
            msg += f"*{idx}.* {row[1]} ({row[2]})\n"
            msg += f"   {status_emoji} Статус: {row[7]}\n"
            msg += f"   {paid_emoji} Оплата: {row[8]}\n"
            msg += f"   💸 Сумма: {row[9]} руб.\n"
            msg += f"   📅 Праздник: {row[4]}\n\n"

        keyboard = pagination_keyboard(page, total_pages)
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=keyboard)

    except Exception as e:
        await query.edit_message_text(f"❌ *Ошибка:* {e}", parse_mode="Markdown")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        orders = sheet_orders.get_all_values()
        expenses = sheet_expenses.get_all_values()
        total_revenue = 0
        paid_count = 0
        status_counts = {}
        for row in orders[1:]:
            if len(row) > 8 and row[8].lower() == 'да':
                total_revenue += float(row[9]) if row[9] else 0
                paid_count += 1
            if len(row) > 7:
                status = row[7] if row[7] else "Не указан"
                status_counts[status] = status_counts.get(status, 0) + 1

        total_expenses = 0
        for row in expenses[1:]:
            if len(row) > 2 and row[2]:
                total_expenses += float(row[2]) if row[2] else 0

        profit = total_revenue - total_expenses
        status_lines = "\n".join([f"   • {s}: {c}" for s, c in status_counts.items()])
        msg = (
            f"📊 *СТАТИСТИКА*\n\n"
            f"💰 *Выручка:* {total_revenue} руб.\n"
            f"💸 *Расходы:* {total_expenses} руб.\n"
            f"📈 *Прибыль:* {profit} руб.\n\n"
            f"📦 *Всего заказов:* {len(orders)-1}\n"
            f"✅ *Оплачено:* {paid_count}\n\n"
            f"📌 *Распределение по статусам:*\n{status_lines}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"❌ *Ошибка:* {e}", parse_mode="Markdown")

async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "❌ *Используйте:* /add_expense сумма описание\n"
                "Например: /add_expense 500 Краска",
                parse_mode="Markdown"
            )
            return
        amount = float(args[0].replace(',', '.'))
        desc = ' '.join(args[1:])
        row = [datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), desc, amount]
        sheet_expenses.append_row(row)
        await update.message.reply_text(f"✅ *Расход {amount} руб. добавлен.*", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ *Ошибка:* {e}", parse_mode="Markdown")

async def update_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "❌ *Используйте:* /update_status ID статус\n"
                "Например: /update_status 5 отправлено",
                parse_mode="Markdown"
            )
            return
        order_id = int(args[0])
        new_status = ' '.join(args[1:])
        row_num = order_id + 1
        sheet_orders.update_cell(row_num, 8, new_status)
        await update.message.reply_text(f"✅ *Статус заказа {order_id} обновлён на '{new_status}'*", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ *Ошибка:* {e}", parse_mode="Markdown")

# ============================================
#  РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ
# ============================================

app.add_handler(CommandHandler('start', start))
app.add_handler(CommandHandler('help', help_command))
app.add_handler(CommandHandler('new_order', new_order))
app.add_handler(CommandHandler('list_orders', list_orders))
app.add_handler(CommandHandler('update_status', update_status))
app.add_handler(CommandHandler('stats', stats))
app.add_handler(CommandHandler('add_expense', add_expense))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(filter_callback))

# ============================================
#  ВЕБХУК НА AIOHTTP
# ============================================

async def handle_webhook(request):
    try:
        data = await request.json()
        if not data:
            return web.Response(status=400, text='Invalid JSON')
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        return web.Response(status=200, text='ok')
    except Exception as e:
        print(f"Webhook error: {e}")
        import traceback
        traceback.print_exc()
        return web.Response(status=500, text='Internal Error')

# Создаём aiohttp приложение
web_app = web.Application()
web_app.router.add_post('/webhook', handle_webhook)
web_app.router.add_get('/', lambda request: web.Response(text='Bot is running!'))

# ============================================
#  ЗАПУСК
# ============================================

async def setup_and_run():
    # Инициализация бота
    await app.initialize()
    app._initialized = True

    # Установка вебхука
    webhook_url = 'https://avtari.onrender.com/webhook'
    await app.bot.set_webhook(url=webhook_url)
    print(f"Webhook установлен на {webhook_url}")

    # Запуск aiohttp сервера
    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.environ.get('PORT', 10000))
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()
    print(f"Сервер запущен на порту {port}")
    await asyncio.Event().wait()  # Бесконечное ожидание

if __name__ == '__main__':
    asyncio.run(setup_and_run())
