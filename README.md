# Бот для учёта заказов

Этот бот автоматизирует учёт заказов наклеек через Telegram.

## Развертывание на Render.com

1. Зарегистрируйтесь на [Render.com](https://render.com).
2. Создайте новый Web Service, подключив этот репозиторий (`IgaGor11/avtari`).
3. В настройках укажите:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
4. Добавьте переменные окружения:
   - `BOT_TOKEN` = ваш токен бота
   - `SPREADSHEET_ID` = ID вашей Google таблицы
   - `ADMIN_CHAT_ID` = ваш Telegram ID
   - `SHEET_ORDERS` = имя листа с заказами (по умолчанию "Заказы")
   - `SHEET_EXPENSES` = имя листа с расходами (по умолчанию "Расходы")
5. Загрузите файл `credentials.json` (ключ доступа к Google Sheets) через панель Render (раздел "Files" или "Secret Files").
6. Нажмите "Deploy".

## Использование

- `/start` – приветствие
- `/new_order` – начать добавление заказа
- `/list_orders` – показать последние 5 заказов
- `/update_status ID статус` – обновить статус заказа
- `/stats` – статистика
- `/add_expense сумма описание` – добавить расход
