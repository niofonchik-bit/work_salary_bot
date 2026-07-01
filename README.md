# Work Salary Bot

Личный Telegram-бот для учёта рабочего времени, перерывов, примерной зарплаты и прогресса к финансовой цели.

Проект рассчитан на обычный запуск Python без Docker. Локально используется SQLite, на Railway — PostgreSQL. События входа и выхода из офисной геозоны поступают от MacroDroid и формируют смены, которые пользователь подтверждает вручную.

## Возможности

- фиксация прихода и ухода;
- предложения смен по событиям входа и выхода из офисной геозоны;
- подтверждение полной смены сразу или массово раз в неделю;
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
- сообщения геозоны сохраняются до подтверждения или отклонения;
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

## Подтверждение смен по геозоне

MacroDroid отправляет события входа и выхода из зоны офиса. Endpoint сохраняет событие и обновляет одну карточку смены в Telegram, но не создаёт `work_sessions` автоматически.

Логика:

```text
вход в зону → предполагаемый приход
выход из зоны → предполагаемый уход
приход + уход → готовая смена
подтверждение пользователя → запись WorkSession
```

Если утреннее событие не пришло, вечерний запрос создаёт карточку с найденным уходом и кнопкой добавления времени прихода. Если утреннее сообщение уже существует, оно обновляется, а новое сообщение не создаётся.

Переменные:

```env
GEOFENCE_ENABLED=true
GEOFENCE_SECRET=случайный_секрет_не_короче_32_символов
GEOFENCE_USER_ID=ваш_telegram_id
GEOFENCE_ZONE=office
GEOFENCE_ARRIVAL_START=05:00
GEOFENCE_ARRIVAL_END=13:00
GEOFENCE_DEPARTURE_START=12:00
GEOFENCE_DEPARTURE_END=23:59
GEOFENCE_EVENT_DEDUP_MINUTES=15
```

Поддерживаются три endpoint:

```text
POST /api/geofence/event
POST /api/geofence/arrival
POST /api/geofence/departure
```

Универсальное тело:

```json
{
  "zone": "office",
  "event": "arrival",
  "client": "macrodroid"
}
```

Для `/arrival` и `/departure` поле `event` не требуется.

После получения события API возвращает `accepted` или `duplicate`. Это означает только сохранение предложения. Реальная смена появляется после нажатия `Подтвердить смену` или `Подтвердить все полные` в разделе `📥 Подтверждения`.

### Макрос прихода

```text
Вход в зону
→ задержка 2 минуты
→ проверка нахождения внутри
→ POST /api/geofence/arrival
```

### Макрос ухода

```text
Выход из зоны
→ задержка 10 минут
→ проверка нахождения вне зоны
→ POST /api/geofence/departure
```

Оба запроса используют:

```text
Authorization: Bearer <GEOFENCE_SECRET>
Content-Type: application/json
```

Координаты, адрес офиса и история перемещений серверу не передаются.

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

Ожидаемый первый ответ:

```json
{
  "status": "accepted",
  "eventType": "arrival",
  "pendingShiftId": 1,
  "messageUpdated": true
}
```

Миграция `0002_geofence_queue` создаёт таблицы `geofence_events` и `pending_shifts`.

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
