# GLDRUBF Trading Strategy

Автоматизированная торговая стратегия для фьючерса GLDRUBF (золото) с интеграцией Telegram.

## Структура проекта

```
/workspace/
├── src/                      # Исходный код стратегии
│   ├── main.py              # Точка входа
│   ├── instruments.py       # Поиск инструмента GLDRUBF
│   ├── market_data.py       # Загрузка свечей и цен
│   ├── indicators.py        # Индикаторы (ATR, Donchian, SAR)
│   ├── positions.py         # Поиск и управление позициями
│   ├── strategy.py          # Логика сигналов (вход/выход)
│   └── telegram_bot.py      # Отправка сообщений в Telegram
├── config/                   # Конфигурация
│   ├── __init__.py
│   └── settings.py          # Параметры стратегии
├── bot.py                    # Telegram-бот для ручного запуска расчёта
├── .github/workflows/        # GitHub Actions workflows
│   ├── gold_strategy.yml    # Запуск стратегии по расписанию
│   └── telegram_bot.yml     # Workflow для бота
├── .gitignore
└── README.md
```

## Установка зависимостей

```bash
pip install t-tech-investments --index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple
pip install pandas numpy requests
```

## Настройка секретов

Необходимо настроить следующие GitHub Secrets:

- `T_SANDBOX` - токен T-Invest API (sandbox)
- `BOT_TOKEN` - токен Telegram бота (для уведомлений и для bot.py)
- `TELEGRAM_CHAT_ID` - ID чата для уведомлений от стратегии
- `GH_TRIGGER_TOKEN` - токен GitHub с правами на запуск workflows (для bot.py)
- `GITHUB_OWNER` - владелец репозитория (для bot.py)
- `GITHUB_REPO` - имя репозитория (для bot.py)

## Запуск

### Локальный запуск стратегии

```bash
export T_SANDBOX="your_token"
export BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"

python -m src.main
```

### Автоматический запуск стратегии

Стратегия запускается автоматически каждые 4 часа через GitHub Actions:
- 03:01 МСК
- 07:01 МСК
- 11:01 МСК
- 15:01 МСК
- 19:01 МСК
- 23:01 МСК

### Запуск Telegram-бота (bot.py)

Бот позволяет вручную запустить расчёт сигнала по команде `/signal`:

```bash
export BOT_TOKEN="your_bot_token"
export GH_TRIGGER_TOKEN="your_github_token"
export GITHUB_OWNER="your_github_username"
export GITHUB_REPO="your_repo_name"

python bot.py
```

**Команды бота:**
- `/signal` - запускает workflow расчёта сигнала стратегии

После получения команды бот:
1. Отправляет сообщение «⏳ Запускаю расчёт сигнала...»
2. Вызывает GitHub workflow `gold_strategy.yml`
3. Сообщает об успешном запуске или ошибке

## Параметры стратегии

| Параметр | Значение | Описание |
|----------|----------|----------|
| TIMEFRAME | 4H | Таймфрейм свечей |
| DONCHIAN_LEN | 20 | Период канала Дончиана |
| ATR_LEN | 14 | Период ATR |
| SL_ATR | 3.0 | Stop Loss в единицах ATR |
| TP_PCT | 0.07 | Take Profit (7%) |
| BE_PCT | 0.02 | Безубыток (2%) |
| SAR_START | 0.03 | Начальный AF Parabolic SAR |
| SAR_INC | 0.02 | Шаг AF |
| SAR_MAX | 0.20 | Максимальный AF |

## Логика работы

1. **Загрузка данных** - получаем последние 200 свечей 4H
2. **Расчет индикаторов** - ATR, Donchian Channel, Parabolic SAR
3. **Поиск позиции** - проверяем все счета на наличие позиции GLDRUBF
4. **Принятие решения**:
   - Если нет позиции → проверяем сигнал на вход (пробой Donchian)
   - Если есть позиция → проверяем условия выхода (SL, TP, SAR, BE)
5. **Отправка отчета** в Telegram

## Формат сообщения Telegram

```
🟢 GLDRUBF SENTRY

💰 Рынок
Цена:        7850.50
Закрытие 4H: 7845.00
Свеча:       16.08.2025 15:00 MSK

📈 Позиция
⚪ Нет позиции

🎯 Сигнал
⚪ Нет сигнала

📐 SAR
7820.00 · 🟢 LONG

➡️ Действие
WAIT

⏱ 15:00:00 MSK
```
