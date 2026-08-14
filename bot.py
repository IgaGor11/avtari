import os
import datetime
import asyncio
import csv
import io
import gspread
import traceback
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

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet_orders = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_ORDERS)
sheet_expenses = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_EXPENSES)

app = ApplicationBuilder().token(BOT_TOKEN).build()
user_data = {}

# ============================================
#  КЛАВИАТУРЫ
# ============================================

main_keyboard = ReplyKeyboardMarkup(
    [
        ["📦 Новый заказ", "📋 Список заказов"],
        ["📊 Статистика", "💰 Добавить расход"],
        ["🔍 Поиск", "❓ Помощь"]
    ],
    resize_keyboard=True
)

dialog_keyboard = ReplyKeyboardMarkup(
    [
        ["🔙 Отмена"]
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
    [InlineKeyboardButton("🔙 Назад", callback_data="cancel_filter")]
])

edit_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📝 Статус", callback_data="edit_status"),
     InlineKeyboardButton("💰 Оплата", callback_data="edit_paid")],
    [InlineKeyboardButton("👤 Клиент", callback_data="edit_client"),
     InlineKeyboardButton("💸 Сумма", callback_data="edit_amount")],
    [InlineKeyboardButton("🎉 Праздник", callback_data="edit_holiday"),
     InlineKeyboardButton("🏙️ Город", callback_data="edit_city")],
    [InlineKeyboardButton("📦 Формат", callback_data="edit_format"),
     InlineKeyboardButton("📞 Контакт", callback_data="edit_contact")],
    [InlineKeyboardButton("🔙 Назад", callback_data="cancel_edit")]
])

status_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("🟢 Переговорка", callback_data="set_status_переговорка")],
    [InlineKeyboardButton("🟡 Дизайн", callback_data="set_status_дизайн")],
    [InlineKeyboardButton("🔵 Печать", callback_data="set_status_печать")],
    [InlineKeyboardButton("✅ Отправлено", callback_data="set_status_отправлено")],
    [InlineKeyboardButton("🔙 Отмена", callback_data="cancel_edit")]
])

paid_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("✅ Да", callback_data="set_paid_да"),
     InlineKeyboardButton("❌ Нет", callback_data="set_paid_нет")],
    [InlineKeyboardButton("🔙 Отмена", callback_data="cancel_edit")]
])

# ============================================
#  ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК
# ============================================

async def error_handler(update, context):
    print(f"[ERROR] {context.error}")
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка. Администратор уведомлён.",
                reply_markup=main_keyboard
            )
    except:
        pass

# ============================================
#  КОМАНДЫ
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для учёта заказов.\n\nВыберите действие из меню ниже 👇",
        reply_markup=main_keyboard
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📌 Доступные действия:\n\n"
        "• /new_order – добавить заказ\n"
        "• /list_orders – список заказов (с фильтрами)\n"
        "• /stats – общая статистика\n"
        "• /stats_date ДД.ММ.ГГГГ-ДД.ММ.ГГГГ – статистика за период\n"
        "• /add_expense сумма описание – добавить расход\n"
        "• /export – экспорт всех заказов в CSV\n"
        "• /search имя – поиск заказов по клиенту\n"
        "• /test – проверить работу бота\n"
        "• /status – диагностика\n\n"
        "Также вы можете использовать кнопки меню."
    )
    await update.message.reply_text(msg, reply_markup=main_keyboard)

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот работает!", reply_markup=main_keyboard)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        orders_count = len(sheet_orders.get_all_values()) - 1
        expenses_count = len(sheet_expenses.get_all_values()) - 1
        webhook_info = await app.bot.get_webhook_info()
        webhook_url = webhook_info.url if webhook_info else "не установлен"
        pending = webhook_info.pending_update_count if webhook_info else 0
        msg = (
            f"🔍 Диагностика:\n"
            f"• Заказов: {orders_count}\n"
            f"• Расходов: {expenses_count}\n"
            f"• Вебхук: {webhook_url}\n"
            f"• Ожидающих обновлений: {pending}"
        )
        await update.message.reply_text(msg, reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)

async def search_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if not args:
            await update.message.reply_text("❌ Введите имя для поиска: /search Иван", reply_markup=main_keyboard)
            return
        query = ' '.join(args).lower()
        records = sheet_orders.get_all_values()
        if len(records) <= 1:
            await update.message.reply_text("📭 Заказов нет.", reply_markup=main_keyboard)
            return
        found = []
        for idx, row in enumerate(records[1:], start=1):
            if len(row) > 1 and query in row[1].lower():
                found.append((idx, row))
        if not found:
            await update.message.reply_text(f"🔍 Ничего не найдено по запросу '{query}'.", reply_markup=main_keyboard)
            return
        msg = f"🔍 Найдено {len(found)} заказов:\n\n"
        for idx, row in found[:10]:
            msg += f"*{idx}.* {row[1]} – {row[7]} – {row[9]} руб.\n"
        if len(found) > 10:
            msg += f"\n... и ещё {len(found)-10} заказов. Используйте список для управления."
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)

# ----- Новый заказ (диалог) -----
async def new_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data[chat_id] = {'step': 'client'}
    await update.message.reply_text("📝 Введите имя клиента:", reply_markup=dialog_keyboard)

# ----- Список заказов (вызов фильтров) -----
async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 Выберите фильтр для списка заказов:",
        reply_markup=filter_keyboard
    )
    context.user_data['filter'] = None
    context.user_data['page'] = 1

# ----- Остальные команды (статистика, расходы, экспорт) -----
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        orders = sheet_orders.get_all_values()
        expenses = sheet_expenses.get_all_values()
        total_revenue = sum(float(r[9]) for r in orders[1:] if len(r)>8 and r[8].lower()=='да' and r[9])
        paid_count = sum(1 for r in orders[1:] if len(r)>8 and r[8].lower()=='да')
        total_expenses = sum(float(r[2]) for r in expenses[1:] if len(r)>2 and r[2])
        profit = total_revenue - total_expenses
        status_counts = {}
        for r in orders[1:]:
            if len(r)>7:
                status = r[7] or "Не указан"
                status_counts[status] = status_counts.get(status, 0) + 1
        status_lines = "\n".join(f"   • {s}: {c}" for s, c in status_counts.items())
        msg = (
            f"📊 СТАТИСТИКА\n\n"
            f"💰 Выручка: {total_revenue} руб.\n"
            f"💸 Расходы: {total_expenses} руб.\n"
            f"📈 Прибыль: {profit} руб.\n\n"
            f"📦 Всего заказов: {len(orders)-1}\n"
            f"✅ Оплачено: {paid_count}\n\n"
            f"📌 Распределение по статусам:\n{status_lines}"
        )
        await update.message.reply_text(msg, reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)

async def stats_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text("❌ Используйте: /stats_date ДД.ММ.ГГГГ-ДД.ММ.ГГГГ", reply_markup=main_keyboard)
            return
        dates = args[0].split('-')
        if len(dates) != 2:
            raise ValueError("Неверный формат")
        start = datetime.datetime.strptime(dates[0], '%d.%m.%Y')
        end = datetime.datetime.strptime(dates[1], '%d.%m.%Y')
        records = sheet_orders.get_all_values()
        count = 0
        paid = 0
        revenue = 0
        for r in records[1:]:
            if len(r) < 10:
                continue
            try:
                order_date = datetime.datetime.strptime(r[0].split()[0], '%Y-%m-%d')
                if start <= order_date <= end:
                    count += 1
                    if r[8].lower() == 'да':
                        paid += 1
                        revenue += float(r[9]) if r[9] else 0
            except:
                continue
        msg = f"📊 Статистика за {dates[0]} – {dates[1]}\n\n📦 Заказов: {count}\n💰 Оплачено: {paid}\n💸 Выручка: {revenue} руб."
        await update.message.reply_text(msg, reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)

async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❌ /add_expense сумма описание", reply_markup=main_keyboard)
            return
        amount = float(args[0].replace(',', '.'))
        desc = ' '.join(args[1:])
        sheet_expenses.append_row([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), desc, amount])
        await update.message.reply_text(f"✅ Расход {amount} руб. добавлен.", reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)

async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        records = sheet_orders.get_all_values()
        if len(records) <= 1:
            await update.message.reply_text("📭 Нет данных.", reply_markup=main_keyboard)
            return
        output = io.StringIO()
        csv.writer(output).writerows(records)
        output.seek(0)
        await update.message.reply_document(
            document=output.getvalue().encode('utf-8'),
            filename=f"заказы_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
            caption="📊 Экспорт всех заказов",
            reply_markup=main_keyboard
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)

# ============================================
#  ОТОБРАЖЕНИЕ СПИСКА ЗАКАЗОВ С КНОПКАМИ
# ============================================

async def show_orders_page(update: Update, context: ContextTypes.DEFAULT_TYPE, edit_mode=False):
    query = update.callback_query
    page = context.user_data.get('page', 1)
    filter_type = context.user_data.get('filter')
    print(f"[LOG] Показ страницы {page}, фильтр {filter_type}")

    try:
        records = sheet_orders.get_all_values()
        if len(records) <= 1:
            await query.edit_message_text("📭 Заказов пока нет.", reply_markup=None)
            return

        data_rows = records[1:]
        filtered = []
        for idx, row in enumerate(data_rows, start=1):
            if filter_type:
                key, value = filter_type
                if key == 'status':
                    if len(row) > 7 and row[7].lower() == value.lower():
                        filtered.append((idx, row))
                elif key == 'paid':
                    if len(row) > 8 and row[8].lower() == value.lower():
                        filtered.append((idx, row))
            else:
                filtered.append((idx, row))

        if not filtered:
            await query.edit_message_text("📭 Нет заказов, соответствующих фильтру.", reply_markup=None)
            return

        total = len(filtered)
        total_pages = (total + 4) // 5
        start = (page - 1) * 5
        end = min(start + 5, total)
        page_items = filtered[start:end]

        # Формируем текст списка
        msg = f"📋 Список заказов (стр. {page}/{total_pages})\n\n"
        for idx, row in page_items:
            status_emoji = {
                "переговорка": "🟢",
                "дизайн": "🟡",
                "печать": "🔵",
                "отправлено": "✅"
            }.get(row[7].lower() if len(row)>7 else "", "⚪")
            paid_emoji = "💰" if len(row)>8 and row[8].lower() == "да" else "❌"
            msg += f"{status_emoji} *{idx}.* {row[1]} ({row[2]})\n"
            msg += f"   Статус: {row[7]} | Оплата: {row[8]} | Сумма: {row[9]} руб.\n\n"

        # Строим клавиатуру с кнопками для каждого заказа + пагинация
        keyboard_buttons = []
        # Для каждого заказа добавляем строку с кнопками "Редактировать" и "Удалить"
        for idx, row in page_items:
            row_buttons = [
                InlineKeyboardButton(f"✏️ #{idx}", callback_data=f"edit_order_{idx}"),
                InlineKeyboardButton(f"🗑️ #{idx}", callback_data=f"delete_order_{idx}")
            ]
            keyboard_buttons.append(row_buttons)

        # Кнопки пагинации
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("◀️", callback_data=f"page_{page-1}"))
        nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("▶️", callback_data=f"page_{page+1}"))
        if nav_row:
            keyboard_buttons.append(nav_row)

        # Кнопка "Назад" для выхода из списка
        keyboard_buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="cancel_filter")])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=keyboard)

    except Exception as e:
        print(f"[ERROR] show_orders_page: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=None)

# ============================================
#  ОБРАБОТЧИКИ CALLBACK
# ============================================

async def filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel_filter":
        await query.edit_message_text("❌ Фильтр отменён.", reply_markup=None)
        await query.message.reply_text("Главное меню:", reply_markup=main_keyboard)
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

async def edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel_edit":
        await query.edit_message_text("❌ Редактирование отменено.", reply_markup=None)
        # Возвращаемся в список заказов
        await show_orders_page(update, context)
        return

    if data.startswith("edit_order_"):
        order_id = int(data.split("_")[2])
        context.user_data['editing_id'] = order_id
        # Сохраняем текущий фильтр и страницу для возврата
        context.user_data['return_filter'] = context.user_data.get('filter')
        context.user_data['return_page'] = context.user_data.get('page', 1)
        await query.edit_message_text(
            f"✏️ Редактирование заказа #{order_id}\n\nВыберите поле для изменения:",
            reply_markup=edit_keyboard
        )
        return

    if data.startswith("edit_"):
        field = data.split("_")[1]
        context.user_data['edit_field'] = field
        if field == "status":
            await query.edit_message_text("Выберите новый статус:", reply_markup=status_keyboard)
        elif field == "paid":
            await query.edit_message_text("Выберите статус оплаты:", reply_markup=paid_keyboard)
        else:
            # Для остальных полей просим ввести текст
            await query.edit_message_text(
                f"📝 Введите новое значение для поля '{field}':",
                reply_markup=None
            )
            context.user_data['waiting_for_edit_input'] = True
        return

    if data.startswith("set_status_"):
        new_status = data.split("_", 2)[2]
        order_id = context.user_data.get('editing_id')
        if order_id:
            try:
                sheet_orders.update_cell(order_id + 1, 8, new_status)
                await query.edit_message_text(f"✅ Статус заказа #{order_id} обновлён.")
            except Exception as e:
                await query.edit_message_text(f"❌ Ошибка: {e}")
        else:
            await query.edit_message_text("❌ Ошибка: не найден ID.")
        context.user_data.pop('editing_id', None)
        context.user_data.pop('edit_field', None)
        # Возврат в список
        await show_orders_page(update, context)
        return

    if data.startswith("set_paid_"):
        new_paid = data.split("_", 2)[2]
        order_id = context.user_data.get('editing_id')
        if order_id:
            try:
                sheet_orders.update_cell(order_id + 1, 9, new_paid)
                await query.edit_message_text(f"✅ Оплата заказа #{order_id} обновлена.")
            except Exception as e:
                await query.edit_message_text(f"❌ Ошибка: {e}")
        else:
            await query.edit_message_text("❌ Ошибка: не найден ID.")
        context.user_data.pop('editing_id', None)
        context.user_data.pop('edit_field', None)
        await show_orders_page(update, context)
        return

    if data.startswith("delete_order_"):
        order_id = int(data.split("_")[2])
        context.user_data['delete_id'] = order_id
        context.user_data['delete_row'] = order_id + 1
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, удалить", callback_data="confirm_delete"),
             InlineKeyboardButton("❌ Отмена", callback_data="cancel_delete")]
        ])
        await query.edit_message_text(
            f"⚠️ Вы уверены, что хотите удалить заказ #{order_id}?",
            reply_markup=keyboard
        )
        return

async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "confirm_delete":
        order_id = context.user_data.get('delete_id')
        row_num = context.user_data.get('delete_row')
        if order_id and row_num:
            try:
                sheet_orders.delete_rows(row_num, row_num)
                await query.edit_message_text(f"✅ Заказ #{order_id} удалён.")
            except Exception as e:
                await query.edit_message_text(f"❌ Ошибка: {e}")
        else:
            await query.edit_message_text("❌ Нет данных.")
        context.user_data.pop('delete_id', None)
        context.user_data.pop('delete_row', None)
    elif data == "cancel_delete":
        await query.edit_message_text("❌ Удаление отменено.")
        context.user_data.pop('delete_id', None)
        context.user_data.pop('delete_row', None)

    # Возврат в список
    await show_orders_page(update, context)

# ============================================
#  ОБРАБОТЧИК ВВОДА ДЛЯ РЕДАКТИРОВАНИЯ (текстовые поля)
# ============================================

async def handle_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_edit_input'):
        return
    text = update.message.text
    field = context.user_data.get('edit_field')
    order_id = context.user_data.get('editing_id')
    if not field or not order_id:
        await update.message.reply_text("❌ Ошибка.", reply_markup=main_keyboard)
        context.user_data.pop('waiting_for_edit_input', None)
        return
    try:
        col_map = {
            'client': 2,
            'amount': 10,
            'holiday': 5,
            'city': 6,
            'format': 7,
            'contact': 4,
        }
        col = col_map.get(field)
        if not col:
            await update.message.reply_text("❌ Неизвестное поле.", reply_markup=main_keyboard)
            context.user_data.pop('waiting_for_edit_input', None)
            return
        row_num = order_id + 1
        if field == 'amount':
            try:
                new_value = float(text.replace(',', '.'))
                sheet_orders.update_cell(row_num, col, new_value)
            except:
                await update.message.reply_text("❌ Сумма должна быть числом.", reply_markup=main_keyboard)
                context.user_data.pop('waiting_for_edit_input', None)
                return
        else:
            sheet_orders.update_cell(row_num, col, text)
        await update.message.reply_text(f"✅ Поле '{field}' обновлено.", reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)
    context.user_data.pop('waiting_for_edit_input', None)
    context.user_data.pop('edit_field', None)
    context.user_data.pop('editing_id', None)
    # Возврат в список заказов (на ту же страницу) – но так как мы в текстовом сообщении, мы не можем редактировать то же сообщение,
    # поэтому просто возвращаем главное меню и предлагаем заново открыть список.
    await update.message.reply_text("Вернуться в список заказов можно через меню.", reply_markup=main_keyboard)

# ============================================
#  ОСНОВНОЙ ОБРАБОТЧИК ТЕКСТА
# ============================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith('/'):
        return

    chat_id = update.effective_chat.id
    text = update.message.text

    # Редактирование — ожидание ввода
    if context.user_data.get('waiting_for_edit_input'):
        await handle_edit_input(update, context)
        return

    # Отмена
    if text == "🔙 Отмена":
        if chat_id in user_data:
            del user_data[chat_id]
        await update.message.reply_text("❌ Отменено.", reply_markup=main_keyboard)
        return

    # Диалог создания заказа
    if chat_id in user_data:
        state = user_data[chat_id]
        step = state['step']
        if step == 'client':
            state['client'] = text
            state['step'] = 'nick'
            await update.message.reply_text("📝 Введите ник:", reply_markup=dialog_keyboard)
        elif step == 'nick':
            state['nick'] = text
            state['step'] = 'contact'
            await update.message.reply_text("📝 Способ связи (Инст, ТГ, Макс):", reply_markup=dialog_keyboard)
        elif step == 'contact':
            state['contact'] = text
            state['step'] = 'holiday'
            await update.message.reply_text("📝 Дата праздника (ДД.ММ.ГГГГ):", reply_markup=dialog_keyboard)
        elif step == 'holiday':
            state['holiday'] = text
            state['step'] = 'city'
            await update.message.reply_text("📝 Город (Москва, СПб, другой):", reply_markup=dialog_keyboard)
        elif step == 'city':
            state['city'] = text
            state['step'] = 'format'
            await update.message.reply_text("📝 Формат (полный, электронная, самовывоз):", reply_markup=dialog_keyboard)
        elif step == 'format':
            state['format'] = text
            state['step'] = 'status'
            await update.message.reply_text("📝 Статус (переговорка, дизайн, печать, отправлено):", reply_markup=dialog_keyboard)
        elif step == 'status':
            state['status'] = text
            state['step'] = 'paid'
            await update.message.reply_text("📝 Оплачено? (Да / Нет):", reply_markup=dialog_keyboard)
        elif step == 'paid':
            state['paid'] = text
            state['step'] = 'amount'
            await update.message.reply_text("📝 Сумма (число):", reply_markup=dialog_keyboard)
        elif step == 'amount':
            state['amount'] = text
            try:
                amount_value = float(state['amount'].replace(',', '.')) if state['amount'].replace(',', '').replace('.', '').isdigit() else 0
                row = [
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    state['client'], state['nick'], state['contact'],
                    state['holiday'], state['city'], state['format'],
                    state['status'], state['paid'], amount_value
                ]
                sheet_orders.append_row(row)
                await update.message.reply_text("✅ Заказ добавлен!", reply_markup=main_keyboard)
                await context.bot.send_message(ADMIN_CHAT_ID, f"🆕 Новый заказ от {state['client']} на сумму {amount_value} руб.")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)
            del user_data[chat_id]
        return

    # Кнопки главного меню
    if text == "📦 Новый заказ":
        await new_order(update, context)
    elif text == "📋 Список заказов":
        await list_orders(update, context)
    elif text == "📊 Статистика":
        await stats(update, context)
    elif text == "💰 Добавить расход":
        await update.message.reply_text("Используйте: /add_expense сумма описание", reply_markup=main_keyboard)
    elif text == "🔍 Поиск":
        await update.message.reply_text("Введите: /search Имя", reply_markup=main_keyboard)
    elif text == "❓ Помощь":
        await help_command(update, context)
    else:
        await update.message.reply_text("Не понял. Используйте меню.", reply_markup=main_keyboard)

# ============================================
#  РЕГИСТРАЦИЯ
# ============================================

app.add_handler(CommandHandler('start', start))
app.add_handler(CommandHandler('help', help_command))
app.add_handler(CommandHandler('test', test_command))
app.add_handler(CommandHandler('status', status_command))
app.add_handler(CommandHandler('new_order', new_order))
app.add_handler(CommandHandler('list_orders', list_orders))
app.add_handler(CommandHandler('stats', stats))
app.add_handler(CommandHandler('stats_date', stats_date))
app.add_handler(CommandHandler('add_expense', add_expense))
app.add_handler(CommandHandler('export', export_csv))
app.add_handler(CommandHandler('search', search_orders))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(filter_callback, pattern='^(filter_|page_|status_|paid_|cancel_filter)'))
app.add_handler(CallbackQueryHandler(edit_callback, pattern='^(edit_|set_|delete_order_|cancel_edit)'))
app.add_handler(CallbackQueryHandler(delete_callback, pattern='^(confirm_delete|cancel_delete)'))
app.add_error_handler(error_handler)

# ============================================
#  ВЕБХУК
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
        print(f"[ERROR] Webhook: {e}")
        traceback.print_exc()
        return web.Response(status=500, text='Internal Error')

web_app = web.Application()
web_app.router.add_post('/webhook', handle_webhook)
web_app.router.add_get('/', lambda request: web.Response(text='Bot is running!'))

async def setup_and_run():
    await app.initialize()
    app._initialized = True
    webhook_url = 'https://avtari.onrender.com/webhook'
    await app.bot.set_webhook(url=webhook_url)
    print(f"Webhook установлен на {webhook_url}")

    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.environ.get('PORT', 10000))
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()
    print(f"Сервер запущен на порту {port}")
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(setup_and_run())
