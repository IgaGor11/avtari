import os
import datetime
import asyncio
import csv
import io
import re
import gspread
import traceback
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.font_manager import FontProperties
from PIL import Image
import tempfile
from oauth2client.service_account import ServiceAccountCredentials
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler, ConversationHandler

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
#  КЛАВИАТУРЫ
# ============================================

main_keyboard = ReplyKeyboardMarkup(
    [
        ["📦 Пошаговый заказ", "⚡ Быстрый заказ"],
        ["📋 Список заказов", "📊 Статистика"],
        ["💰 Добавить расход", "🔍 Поиск"],
        ["📸 Скриншот", "📋 Таблица"],
        ["❓ Помощь"]
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
    [InlineKeyboardButton("✅ Оплачено", callback_data="set_paid_оплачено")],
    [InlineKeyboardButton("❌ Не оплачено", callback_data="set_paid_не оплачено")],
    [InlineKeyboardButton("🔙 Отмена", callback_data="cancel_edit")]
])

screenshot_choice_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📋 Заказы", callback_data="screenshot_orders"),
     InlineKeyboardButton("💰 Расходы", callback_data="screenshot_expenses")],
    [InlineKeyboardButton("🔙 Отмена", callback_data="cancel_screenshot")]
])

# ============================================
#  ФУНКЦИЯ НОРМАЛИЗАЦИИ ДАТЫ
# ============================================

def normalize_date(date_str):
    date_str = date_str.strip()
    if not date_str:
        return date_str

    months_ru = {
        'января': 1, 'янв': 1, 'январь': 1,
        'февраля': 2, 'фев': 2, 'февраль': 2,
        'марта': 3, 'мар': 3, 'март': 3,
        'апреля': 4, 'апр': 4, 'апрель': 4,
        'мая': 5, 'май': 5,
        'июня': 6, 'июн': 6, 'июнь': 6,
        'июля': 7, 'июл': 7, 'июль': 7,
        'августа': 8, 'авг': 8, 'август': 8,
        'сентября': 9, 'сен': 9, 'сентябрь': 9,
        'октября': 10, 'окт': 10, 'октябрь': 10,
        'ноября': 11, 'ноя': 11, 'ноябрь': 11,
        'декабря': 12, 'дек': 12, 'декабрь': 12
    }
    months_en = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
        'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'october': 10, 'oct': 10,
        'november': 11, 'nov': 11, 'december': 12, 'dec': 12
    }
    months = {**months_ru, **months_en}

    now = datetime.datetime.now()
    if date_str.lower() in ['сегодня', 'today']:
        return now.strftime('%d.%m.%Y')
    if date_str.lower() in ['завтра', 'tomorrow']:
        return (now + datetime.timedelta(days=1)).strftime('%d.%m.%Y')

    separators = ['.', '/', '-']
    for sep in separators:
        if sep in date_str:
            parts = date_str.split(sep)
            if len(parts) == 3:
                try:
                    day = int(parts[0])
                    month = int(parts[1])
                    year = int(parts[2])
                    if year < 100:
                        year += 2000 if year < 30 else 1900
                    if 1 <= day <= 31 and 1 <= month <= 12:
                        return f"{day:02d}.{month:02d}.{year}"
                except:
                    pass

    words = re.split(r'[,\s]+', date_str)
    month_num = None
    day = None
    year = None
    for i, w in enumerate(words):
        w_lower = w.lower()
        if w_lower in months:
            month_num = months[w_lower]
            if i > 0 and words[i-1].isdigit():
                day = int(words[i-1])
            elif i < len(words)-1 and words[i+1].isdigit():
                day = int(words[i+1])
            for w2 in words:
                if w2.isdigit() and len(w2) == 4:
                    year = int(w2)
                elif w2.isdigit() and len(w2) == 2:
                    year = 2000 + int(w2) if int(w2) < 30 else 1900 + int(w2)
            if year is None:
                year = now.year
            if day is not None and month_num is not None:
                try:
                    dt = datetime.datetime(year, month_num, day)
                    return dt.strftime('%d.%m.%Y')
                except:
                    pass
    return date_str

# ============================================
#  ПАРСИНГ БЫСТРОГО ЗАКАЗА (5 строк, регистр приводится к нижнему)
# ============================================

def parse_quick_order(text):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if len(lines) < 5:
        raise ValueError("Недостаточно строк. Нужно минимум 5 строк: имя+связь, город+дата, формат, статус, сумма.")

    try:
        parts1 = lines[0].split()
        if len(parts1) < 2:
            raise ValueError("В первой строке должны быть: имя и способ связи (минимум 2 слова).")
        if len(parts1) == 2:
            client = parts1[0]
            nick = ''
            contact = parts1[1]
        else:
            client = parts1[0]
            contact = parts1[-1]
            nick = ' '.join(parts1[1:-1]) if len(parts1) > 2 else ''

        city_date = lines[1].split()
        if len(city_date) < 2:
            raise ValueError("Во второй строке должны быть город и дата (минимум 2 слова).")
        if len(city_date) == 2:
            city = city_date[0].lower()
            raw_date = city_date[1]
        else:
            city = ' '.join(city_date[:-1]).lower()
            raw_date = city_date[-1]
        holiday = normalize_date(raw_date)

        format_type = lines[2].lower()
        status = lines[3].lower()
        amount_str = lines[4].replace(',', '.').strip()
        amount = float(amount_str) if amount_str else 0.0

        if city.lower() in ['неважно', 'n/a', '-']:
            city = 'неважно'

        return {
            'client': client,
            'nick': nick,
            'contact': contact,
            'city': city,
            'holiday': holiday,
            'format': format_type,
            'status': status,
            'paid': 'Оплачено',  # всегда оплачено
            'amount': amount
        }
    except IndexError:
        raise ValueError("Не хватает данных. Проверьте, что вы заполнили все 5 строк.")
    except Exception as e:
        raise ValueError(f"Ошибка парсинга: {e}")

# ============================================
#  ФУНКЦИЯ ГЕНЕРАЦИИ СКРИНШОТА (универсальная)
# ============================================

def generate_screenshot(sheet_type='orders'):
    """Генерирует изображение с последними 10 записями из таблицы Заказы или Расходы."""
    try:
        if sheet_type == 'orders':
            sheet = sheet_orders
            title = "Заказы"
        else:
            sheet = sheet_expenses
            title = "Расходы"

        records = sheet.get_all_values()
        if len(records) <= 1:
            return None

        headers = records[0]
        data = records[1:11]  # последние 10 записей

        # Определяем ширину колонок
        if sheet_type == 'orders':
            col_widths = [0.08, 0.12, 0.1, 0.1, 0.12, 0.08, 0.1, 0.12, 0.08, 0.08]
        else:
            col_widths = [0.2, 0.5, 0.3]  # Дата, Описание, Сумма

        fig_width = 12 if sheet_type == 'orders' else 10
        fig, ax = plt.subplots(figsize=(fig_width, 0.5 + 0.5 * len(data)))
        ax.axis('tight')
        ax.axis('off')
        ax.set_title(f"📊 {title} (последние 10)", fontsize=14, weight='bold')

        # Формируем таблицу
        table_data = []
        table_data.append(headers[:10 if sheet_type == 'orders' else 3])
        for row in data:
            table_data.append(row[:10 if sheet_type == 'orders' else 3])

        table = ax.table(cellText=table_data, loc='center', cellLoc='left',
                         colWidths=col_widths[:len(table_data[0])])
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.2, 1.5)

        for (i, j), cell in table.get_cell_dict().items():
            if i == 0:
                cell.set_facecolor('#4CAF50')
                cell.set_text_props(weight='bold', color='white')
            else:
                cell.set_facecolor('#f9f9f9' if i % 2 == 0 else '#e8f5e9')
            cell.set_edgecolor('#cccccc')

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            plt.savefig(tmp.name, bbox_inches='tight', dpi=150, facecolor='white')
            return tmp.name
    except Exception as e:
        print(f"[ERROR] generate_screenshot: {e}")
        return None

# ============================================
#  ОБРАБОТЧИКИ КОМАНД
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для учёта заказов.\n\n"
        "Выберите действие из меню 👇",
        reply_markup=main_keyboard
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📌 *Доступные действия:*\n\n"
        "• /new_order – пошаговое создание заказа\n"
        "• /quick – быстрый заказ одним сообщением (см. шаблон)\n"
        "• /list_orders – список заказов (с фильтрами)\n"
        "• /stats – общая статистика\n"
        "• /stats_date ДД.ММ.ГГГГ-ДД.ММ.ГГГГ – статистика за период\n"
        "• /add_expense – добавить расход (диалог)\n"
        "• /export – экспорт всех заказов в CSV\n"
        "• /search – поиск по имени (интерактивный)\n"
        "• /screenshot – скриншот таблицы (выбор таблицы)\n"
        "• /table – получить ссылку на таблицу\n"
        "• /test – проверить работу бота\n"
        "• /status – диагностика\n\n"
        "Используйте кнопки меню для быстрого доступа."
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard)

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
            "🔍 *Диагностика:*\n"
            f"• Заказов: {orders_count}\n"
            f"• Расходов: {expenses_count}\n"
            f"• Вебхук: {webhook_url}\n"
            f"• Ожидающих обновлений: {pending}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)

# ---------- Пошаговый заказ ----------
async def new_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data[chat_id] = {'step': 'client'}
    await update.message.reply_text("📝 Введите имя клиента:", reply_markup=dialog_keyboard)

# ---------- Быстрый заказ (шаблон) ----------
async def quick_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    template = (
        "📝 *Отправьте одним сообщением данные заказа в 5 строках:*\n\n"
        "1) имя, ник (опционально), способ связи\n"
        "2) город, дата (можно без запятой)\n"
        "3) формат (печать / электронная)\n"
        "4) статус (дизайн / печать / отправлено)\n"
        "5) сумма (число)\n\n"
        "*Примеры:*\n"
        "Елена @cikovskay тг\n"
        "Москва 21 августа\n"
        "Печать\n"
        "Дизайн\n"
        "1800\n\n"
        "Или без ника:\n"
        "Анна инст\n"
        "неважно 25.12\n"
        "электронная\n"
        "отправлено\n"
        "1500"
    )
    await update.message.reply_text(template, parse_mode="Markdown", reply_markup=main_keyboard)

# ---------- Список заказов ----------
async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 Выберите фильтр для списка заказов:",
        reply_markup=filter_keyboard
    )
    context.user_data['filter'] = None
    context.user_data['page'] = 1

# ---------- Статистика ----------
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        orders = sheet_orders.get_all_values()
        expenses = sheet_expenses.get_all_values()
        total_revenue = 0
        paid_count = 0
        for r in orders[1:]:
            if len(r) > 8 and 'оплачено' in r[8].lower():
                total_revenue += float(r[9]) if r[9] else 0
                paid_count += 1
        total_expenses = sum(float(r[2]) for r in expenses[1:] if len(r)>2 and r[2])
        profit = total_revenue - total_expenses
        status_counts = {}
        for r in orders[1:]:
            if len(r)>7:
                status = r[7] or "Не указан"
                status_counts[status] = status_counts.get(status, 0) + 1
        status_lines = "\n".join(f"   • {s}: {c}" for s, c in status_counts.items())
        msg = (
            "📊 *СТАТИСТИКА*\n\n"
            f"💰 Выручка: {total_revenue} руб.\n"
            f"💸 Расходы: {total_expenses} руб.\n"
            f"📈 Прибыль: {profit} руб.\n\n"
            f"📦 Всего заказов: {len(orders)-1}\n"
            f"✅ Оплачено: {paid_count}\n\n"
            f"📌 Распределение по статусам:\n{status_lines}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)

# ---------- Статистика за период ----------
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
                    if 'оплачено' in r[8].lower():
                        paid += 1
                        revenue += float(r[9]) if r[9] else 0
            except:
                continue
        msg = f"📊 *Статистика за {dates[0]} – {dates[1]}*\n\n📦 Заказов: {count}\n💰 Оплачено: {paid}\n💸 Выручка: {revenue} руб."
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)

# ---------- Экспорт CSV ----------
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

# ---------- Скриншот (выбор таблицы) ----------
async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Выберите таблицу для скриншота:",
        reply_markup=screenshot_choice_keyboard
    )

async def screenshot_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel_screenshot":
        await query.edit_message_text("❌ Скриншот отменён.", reply_markup=None)
        await query.message.reply_text("Главное меню:", reply_markup=main_keyboard)
        return

    sheet_type = "orders" if data == "screenshot_orders" else "expenses"
    await query.edit_message_text(f"⏳ Генерирую скриншот таблицы '{'Заказы' if sheet_type == 'orders' else 'Расходы'}'...")
    img_path = generate_screenshot(sheet_type)
    if img_path:
        try:
            with open(img_path, 'rb') as img_file:
                caption = "📸 *Последние 10 записей в таблице Заказы*" if sheet_type == 'orders' else "📸 *Последние 10 записей в таблице Расходы*"
                await query.message.reply_photo(
                    photo=img_file,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=main_keyboard
                )
            os.unlink(img_path)
        except Exception as e:
            await query.message.reply_text(f"❌ Ошибка при отправке скриншота: {e}", reply_markup=main_keyboard)
    else:
        await query.message.reply_text("📭 Нет данных для отображения.", reply_markup=main_keyboard)
    await query.delete_message()

# ---------- Ссылка на таблицу ----------
async def table_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = "https://docs.google.com/spreadsheets/d/1biglRVO95f4sVINiL8j9-CRYKs_IQTOWiSHLblXR0_U/edit?usp=sharing"
    await update.message.reply_text(
        f"📋 *Ссылка на таблицу заказов:*\n{link}",
        parse_mode="Markdown",
        reply_markup=main_keyboard
    )

# ============================================
#  ДИАЛОГ ДОБАВЛЕНИЯ РАСХОДА
# ============================================

EXPENSE_AMOUNT, EXPENSE_DESC = 2, 3

async def expense_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Введите сумму расхода (число):", reply_markup=dialog_keyboard)
    return EXPENSE_AMOUNT

async def expense_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.replace(',', '.'))
        context.user_data['expense_amount'] = amount
        await update.message.reply_text("📝 Введите описание расхода:", reply_markup=dialog_keyboard)
        return EXPENSE_DESC
    except:
        await update.message.reply_text("❌ Введите число. Попробуйте снова:", reply_markup=dialog_keyboard)
        return EXPENSE_AMOUNT

async def expense_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text
    amount = context.user_data.get('expense_amount')
    if amount:
        sheet_expenses.append_row([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), desc, amount])
        await update.message.reply_text(f"✅ Расход {amount} руб. добавлен.", reply_markup=main_keyboard)
    else:
        await update.message.reply_text("❌ Ошибка. Попробуйте заново.", reply_markup=main_keyboard)
    context.user_data.pop('expense_amount', None)
    return ConversationHandler.END

async def cancel_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Добавление расхода отменено.", reply_markup=main_keyboard)
    return ConversationHandler.END

# ============================================
#  ПОИСК (диалог)
# ============================================

SEARCH_NAME = 1

async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Введите имя клиента для поиска:", reply_markup=dialog_keyboard)
    return SEARCH_NAME

async def search_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if not query:
        await update.message.reply_text("❌ Имя не может быть пустым.", reply_markup=main_keyboard)
        return ConversationHandler.END

    try:
        records = sheet_orders.get_all_values()
        if len(records) <= 1:
            await update.message.reply_text("📭 Заказов пока нет.", reply_markup=main_keyboard)
            return ConversationHandler.END

        found = []
        for idx, row in enumerate(records[1:], start=1):
            if len(row) > 1 and query.lower() in row[1].lower():
                found.append((idx, row))

        if not found:
            await update.message.reply_text(f"🔍 Ничего не найдено по запросу '{query}'.", reply_markup=main_keyboard)
            return ConversationHandler.END

        msg = f"🔍 Найдено {len(found)} заказов:\n\n"
        for idx, row in found[:10]:
            status_emoji = {
                "переговорка": "🟢",
                "дизайн": "🟡",
                "печать": "🔵",
                "отправлено": "✅"
            }.get(row[7].lower() if len(row)>7 else "", "⚪")
            paid_emoji = "💰" if 'оплачено' in row[8].lower() else "❌"
            msg += f"{status_emoji} *{idx}.* {row[1]} ({row[2]})\n"
            msg += f"   Статус: {row[7]} | Оплата: {row[8]} | Сумма: {row[9]} руб.\n"
        if len(found) > 10:
            msg += f"\n... и ещё {len(found)-10} заказов. Используйте список для просмотра."

        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)
    return ConversationHandler.END

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Поиск отменён.", reply_markup=main_keyboard)
    return ConversationHandler.END

# ============================================
#  ОТОБРАЖЕНИЕ СПИСКА ЗАКАЗОВ С КНОПКАМИ
# ============================================

async def show_orders_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                    # Проверяем оплату: если value == "да" – ищем "оплачено", иначе "не оплачено"
                    if value == "да":
                        if len(row) > 8 and 'оплачено' in row[8].lower():
                            filtered.append((idx, row))
                    else:  # "нет"
                        if len(row) > 8 and 'оплачено' not in row[8].lower():
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

        msg = f"📋 *Список заказов* (стр. {page}/{total_pages})\n\n"
        for idx, row in page_items:
            status_emoji = {
                "переговорка": "🟢",
                "дизайн": "🟡",
                "печать": "🔵",
                "отправлено": "✅"
            }.get(row[7].lower() if len(row)>7 else "", "⚪")
            paid_emoji = "💰" if 'оплачено' in row[8].lower() else "❌"
            msg += f"{status_emoji} *{idx}.* {row[1]} ({row[2]})\n"
            msg += f"   Статус: {row[7]} | Оплата: {row[8]} | Сумма: {row[9]} руб.\n\n"

        keyboard_buttons = []
        for idx, row in page_items:
            row_buttons = [
                InlineKeyboardButton(f"✏️ #{idx}", callback_data=f"edit_order_{idx}"),
                InlineKeyboardButton(f"🗑️ #{idx}", callback_data=f"delete_order_{idx}")
            ]
            keyboard_buttons.append(row_buttons)

        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("◀️", callback_data=f"page_{page-1}"))
        nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("▶️", callback_data=f"page_{page+1}"))
        if nav_row:
            keyboard_buttons.append(nav_row)

        keyboard_buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="cancel_filter")])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=keyboard)

    except Exception as e:
        print(f"[ERROR] show_orders_page: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=None)

# ============================================
#  ОБРАБОТЧИКИ CALLBACK (фильтры, редактирование, удаление, скриншот)
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
        await show_orders_page(update, context)
        return

    if data.startswith("edit_order_"):
        order_id = int(data.split("_")[2])
        context.user_data['editing_id'] = order_id
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
        await show_orders_page(update, context)
        return

    if data.startswith("set_paid_"):
        new_paid = data.split("_", 2)[2]  # "оплачено" или "не оплачено"
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
    await update.message.reply_text("Главное меню:", reply_markup=main_keyboard)

# ============================================
#  ОСНОВНОЙ ОБРАБОТЧИК ТЕКСТА
# ============================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith('/'):
        return

    chat_id = update.effective_chat.id
    text = update.message.text

    if context.user_data.get('waiting_for_edit_input'):
        await handle_edit_input(update, context)
        return

    if text == "🔙 Отмена":
        if chat_id in user_data:
            del user_data[chat_id]
        await update.message.reply_text("❌ Отменено.", reply_markup=main_keyboard)
        return

    # Диалог пошагового заказа
    if chat_id in user_data:
        state = user_data[chat_id]
        step = state['step']
        if step == 'client':
            state['client'] = text
            state['step'] = 'nick'
            await update.message.reply_text("📝 Введите ник (можно пропустить):", reply_markup=dialog_keyboard)
        elif step == 'nick':
            state['nick'] = text if text != '-' else ''
            state['step'] = 'contact'
            await update.message.reply_text("📝 Способ связи (Инст, ТГ, Макс):", reply_markup=dialog_keyboard)
        elif step == 'contact':
            state['contact'] = text
            state['step'] = 'holiday'
            await update.message.reply_text("📝 Дата праздника (ДД.ММ.ГГГГ или текст):", reply_markup=dialog_keyboard)
        elif step == 'holiday':
            state['holiday'] = text
            state['step'] = 'city'
            await update.message.reply_text("📝 Город (Москва, СПб, другой или 'неважно'):", reply_markup=dialog_keyboard)
        elif step == 'city':
            state['city'] = text
            state['step'] = 'format'
            await update.message.reply_text("📝 Формат (печать / электронная):", reply_markup=dialog_keyboard)
        elif step == 'format':
            state['format'] = text
            state['step'] = 'status'
            await update.message.reply_text("📝 Статус (дизайн / печать / отправлено):", reply_markup=dialog_keyboard)
        elif step == 'status':
            state['status'] = text
            state['step'] = 'amount'
            await update.message.reply_text("📝 Сумма (число):", reply_markup=dialog_keyboard)
        elif step == 'amount':
            state['amount'] = text
            try:
                amount_value = float(state['amount'].replace(',', '.')) if state['amount'].replace(',', '').replace('.', '').isdigit() else 0
                row = [
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    state['client'], state.get('nick', ''), state['contact'],
                    state['holiday'], state['city'], state['format'],
                    state['status'], 'Оплачено', amount_value
                ]
                sheet_orders.append_row(row)
                await update.message.reply_text("✅ Заказ добавлен!", reply_markup=main_keyboard)
                await context.bot.send_message(ADMIN_CHAT_ID, f"🆕 Новый заказ от {state['client']} на сумму {amount_value} руб.")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=main_keyboard)
            del user_data[chat_id]
        return

    # ---------- БЫСТРЫЙ ЗАКАЗ (новый формат 5 строк) ----------
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if len(lines) >= 5:
        try:
            parsed = parse_quick_order(text)
            if parsed['client'] and parsed['amount'] is not None:
                row = [
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    parsed['client'],
                    parsed['nick'],
                    parsed['contact'],
                    parsed['holiday'],
                    parsed['city'],
                    parsed['format'],
                    parsed['status'],
                    parsed['paid'],
                    parsed['amount']
                ]
                sheet_orders.append_row(row)
                await update.message.reply_text(
                    f"✅ Заказ от {parsed['client']} успешно добавлен!\n"
                    f"Сумма: {parsed['amount']} руб.",
                    reply_markup=main_keyboard
                )
                await context.bot.send_message(ADMIN_CHAT_ID,
                    f"🆕 Быстрый заказ от {parsed['client']} на сумму {parsed['amount']} руб.")
                return
        except Exception as e:
            await update.message.reply_text(
                f"❌ Не удалось распознать заказ: {e}\n\n"
                "Пожалуйста, проверьте формат и попробуйте снова.\n"
                "Используйте кнопку '⚡ Быстрый заказ' для просмотра шаблона.",
                reply_markup=main_keyboard
            )
            return

    # Кнопки главного меню
    if text == "📦 Пошаговый заказ":
        await new_order(update, context)
    elif text == "⚡ Быстрый заказ":
        await quick_order(update, context)
    elif text == "📋 Список заказов":
        await list_orders(update, context)
    elif text == "📊 Статистика":
        await stats(update, context)
    elif text == "💰 Добавить расход":
        await expense_start(update, context)
    elif text == "🔍 Поиск":
        await search_start(update, context)
    elif text == "📸 Скриншот":
        await screenshot_command(update, context)
    elif text == "📋 Таблица":
        await table_command(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    else:
        await update.message.reply_text(
            "Я не понял. Используйте кнопки меню или введите /help.\n"
            "Для быстрого заказа отправьте данные в 5 строк по шаблону.",
            reply_markup=main_keyboard
        )

# ============================================
#  РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ
# ============================================

conv_search = ConversationHandler(
    entry_points=[CommandHandler('search', search_start)],
    states={SEARCH_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_name)]},
    fallbacks=[CommandHandler('cancel', cancel_search)]
)

conv_expense = ConversationHandler(
    entry_points=[CommandHandler('add_expense', expense_start)],
    states={
        EXPENSE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_amount)],
        EXPENSE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_desc)]
    },
    fallbacks=[CommandHandler('cancel', cancel_expense)]
)

app.add_handler(CommandHandler('start', start))
app.add_handler(CommandHandler('help', help_command))
app.add_handler(CommandHandler('test', test_command))
app.add_handler(CommandHandler('status', status_command))
app.add_handler(CommandHandler('new_order', new_order))
app.add_handler(CommandHandler('quick', quick_order))
app.add_handler(CommandHandler('list_orders', list_orders))
app.add_handler(CommandHandler('stats', stats))
app.add_handler(CommandHandler('stats_date', stats_date))
app.add_handler(CommandHandler('export', export_csv))
app.add_handler(CommandHandler('screenshot', screenshot_command))
app.add_handler(CommandHandler('table', table_command))
app.add_handler(conv_search)
app.add_handler(conv_expense)
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(filter_callback, pattern='^(filter_|page_|status_|paid_|cancel_filter)'))
app.add_handler(CallbackQueryHandler(edit_callback, pattern='^(edit_|set_|delete_order_|cancel_edit)'))
app.add_handler(CallbackQueryHandler(delete_callback, pattern='^(confirm_delete|cancel_delete)'))
app.add_handler(CallbackQueryHandler(screenshot_choice_callback, pattern='^screenshot_'))
app.add_error_handler(error_handler)

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
        print(f"[ERROR] Webhook: {e}")
        traceback.print_exc()
        return web.Response(status=500, text='Internal Error')

web_app = web.Application()
web_app.router.add_post('/webhook', handle_webhook)
web_app.router.add_get('/', lambda request: web.Response(text='Bot is running!'))

# ============================================
#  ЗАПУСК
# ============================================

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
