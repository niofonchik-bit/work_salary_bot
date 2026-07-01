# Work Salary Bot

Личный Telegram-бот для учёта рабочего времени, перерывов, примерной зарплаты и прогресса к финансовой цели.

Проект рассчитан на обычный запуск Python без Docker. Локально используется SQLite, на Railway — PostgreSQL. Автоматический приход может фиксироваться через геозону Android и MacroDroid без передачи координат на сервер.

## Возможности

- фиксация прихода и ухода;
- автоматический приход по геозоне офиса;
- несколько перерывов внутри смены;
- корректная обработка смен через полночь;
- календарь рабочих дней, выходных, отпуска, больничного и отгула;
- расчёт нормы, баланса, переработки и недоработки;
- прогноз зарплаты и текущая заработанная сумма;
- цель по доходу и план её достижения;
- история, ручное добавление и редактирование смен;
- мягкое удаление и восстановление смены;
- CSV-экспорт и JSON-копия;
- напоминание о приходе, уходе, открытой смене и перерыве;
- недельный отчёт;
- постоянное FSM-состояние в базе;
- Alembic-миграция;
- JSON-журнал и healthcheck для Railway;
- ограничение доступа по Telegram ID.

## Telegram-интерфейс

Бот использует один основной экран сообщения:

- нажатия постоянной клавиатуры удаляются из чата;
- переходы по inline-кнопкам изменяют текущее сообщение вместо создания нового;
- текст, введённый в форму, удаляется после обработки;
- формы изменения настроек, календаря и истории содержат кнопку «Отмена»;
- удаление смены требует отдельного подтверждения;
- напоминание и сообщение геозоны содержат кнопку удаления;
- экспортированный файл остаётся в чате как полезный результат.

Настройки разделены на компактные категории:

```text
💵 Доход и цель
🕘 Рабочий график
📈 Расчёт оплаты
📅 Коэффициенты
🎯 План цели
🔔 Напоминания
📍 Автоматизация
```

## Стек

- Python 3.12;
- aiogram 3;
- SQLAlchemy 2;
- Alembic;
- SQLite;
- PostgreSQL;
- aiohttp;
- pytest;
- Ruff.

## Быстрый запуск на Windows

Создание окружения и установка зависимостей:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

При запрете выполнения PowerShell-скриптов:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Заполните `.env`:

```env
BOT_TOKEN=токен_от_BotFather
ALLOWED_USER_IDS=ваш_telegram_id
ADMIN_USER_ID=ваш_telegram_id
DEFAULT_TIMEZONE=Europe/Istanbul
DATABASE_URL=sqlite+aiosqlite:///data/bot.db
```

Применение миграции:

```powershell
alembic upgrade head
```

Запуск:

```powershell
python main.py
```

Также доступны готовые скрипты:

```powershell
.\setup.ps1
.\run.bat
```

## Получение Telegram ID

При локальном запуске временно оставьте `ALLOWED_USER_IDS` пустым, запустите бота и отправьте:

```text
/myid
```

После получения ID заполните переменную и перезапустите приложение. На Railway пустой `ALLOWED_USER_IDS` блокирует запуск.

## Автоматический приход по геозоне

Геозона определяется приложением MacroDroid на Android. Телефон отправляет один защищённый HTTPS-запрос после подтверждённого входа в офисную зону. Координаты, адрес офиса и история перемещений серверу не передаются.

Переменные:

```env
GEOFENCE_ENABLED=true
GEOFENCE_SECRET=случайный_секрет_не_короче_32_символов
GEOFENCE_USER_ID=ваш_telegram_id
GEOFENCE_ZONE=office
GEOFENCE_ARRIVAL_START=05:00
GEOFENCE_ARRIVAL_END=13:00
```

`GEOFENCE_USER_ID` должен входить в `ALLOWED_USER_IDS`.

Endpoint:

```http
POST /api/geofence/arrival
Authorization: Bearer <GEOFENCE_SECRET>
Content-Type: application/json
```

Тело:

```json
{
  "zone": "office",
  "client": "macrodroid"
}
```

Первый допустимый запрос создаёт открытую смену и отправляет Telegram-подтверждение. Повторный запрос, открытая смена, уже отмеченный приход этого дня или запрос вне заданного времени безопасно игнорируются.

### Рекомендуемый макрос MacroDroid

1. Триггер `Geofence Trigger → Офис → Area Entered`.
2. Радиус около 150 метров.
3. Срабатывание при неизвестном предыдущем положении выключено.
4. Задержка 120 секунд.
5. Повторная проверка нахождения внутри зоны.
6. HTTP POST на Railway endpoint.
7. Повтор при сетевой ошибке через 30 и 60 секунд.
8. Локальное уведомление после последней неудачной попытки.

Для MacroDroid должны быть разрешены точная фоновая геолокация, автозапуск и работа без ограничений энергосбережения.

Полная спецификация находится в `GEOFENCE_INTEGRATION_TECHNICAL_SPECIFICATION.md`.

## Ручная проверка геозоны

```powershell
$headers = @{
    Authorization = 'Bearer ТВОЙ_СЕКРЕТ'
}

$body = @{
    zone = 'office'
    client = 'manual-test'
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri 'https://ТВОЙ-ДОМЕН/api/geofence/arrival' `
    -Headers $headers `
    -ContentType 'application/json' `
    -Body $body
```

Ожидаемые ответы:

```text
первый запрос: created
повтор при открытой смене: active_session_exists
повтор после завершения смены в тот же день: arrival_already_recorded
```

## Railway

На Railway используются:

- отдельный PostgreSQL-сервис;
- одна реплика приложения;
- `alembic upgrade head` как pre-deploy command;
- `python main.py` как start command;
- `/health` как healthcheck;
- публичный HTTPS-домен для геозоны.

Подробная инструкция находится в `RAILWAY_DEPLOY.md`.

## Проверка проекта

```powershell
python -m pip install -r requirements-dev.txt
ruff format --check .
ruff check .
pytest -q
alembic upgrade head
alembic check
```

## Структура

```text
app/
├── database/      таблицы, подключение и FSM-хранилище
├── handlers/      Telegram-обработчики
├── keyboards/     клавиатуры
├── middlewares/   ограничение доступа
├── repositories/  операции с базой
├── services/      UI, расчёты, экспорт и напоминания
├── states/        состояния форм
├── use_cases/     прикладные сценарии
└── utils/         форматирование

alembic/            миграции
tests/              тесты
main.py             точка входа
railway.json        конфигурация Railway
```

## Стиль комментариев

Комментарии оформлены короткими именными конструкциями в именительном падеже и единственном числе:

```python
# расчёт месяца
# профиль пользователя
# обработчик геозоны
```
