import requests
import json

# Вставьте ваш токен бота
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

def get_chat_id_force(bot_token):
    """
    Принудительно получает chat_id:
    1. Сначала сбрасывает все старые обновления
    2. Ждет нового сообщения от пользователя
    3. Извлекает chat_id
    """
    base_url = f"https://api.telegram.org/bot{bot_token}"
    
    # Шаг 1: Проверяем токен и получаем имя бота
    print("🔍 Проверка токена бота...")
    resp = requests.get(f"{base_url}/getMe")
    data = resp.json()
    
    if not data.get("ok"):
        raise RuntimeError(f"❌ Неверный токен бота: {data}")
    
    bot_name = data["result"]["first_name"]
    print(f"✅ Бот найден: @{bot_name}")
    
    # Шаг 2: Сбрасываем все старые обновления
    print("🗑️ Сброс старых обновлений...")
    requests.get(f"{base_url}/getUpdates?offset=-1")
    
    # Шаг 3: Инструкция для пользователя
    print("\n" + "="*50)
    print("📱 ТЕПЕРЬ ОТПРАВЬТЕ БОТУ ЛЮБОЕ СООБЩЕНИЕ:")
    print(f"   1. Откройте Telegram")
    print(f"   2. Найдите бота @{bot_name}")
    print(f"   3. Отправьте ему сообщение (например, '/start')")
    print("="*50)
    
    # Шаг 4: Ждем новое сообщение с таймаутом
    print("\n⏳ Ожидание сообщения (30 секунд)...")
    
    import time
    start_time = time.time()
    timeout = 30
    
    while time.time() - start_time < timeout:
        resp = requests.get(f"{base_url}/getUpdates?timeout=5")
        data = resp.json()
        updates = data.get("result", [])
        
        if updates:
            print(f"✅ Получено {len(updates)} сообщений!")
            
            # Ищем сообщение с chat_id
            for update in updates:
                message = update.get("message")
                if message:
                    chat_id = message.get("chat", {}).get("id")
                    username = message.get("chat", {}).get("username", "без username")
                    first_name = message.get("chat", {}).get("first_name", "")
                    
                    if chat_id:
                        print(f"\n{'='*50}")
                        print(f"✅ CHAT_ID НАЙДЕН: {chat_id}")
                        print(f"👤 Пользователь: {first_name} (@{username})")
                        print(f"{'='*50}\n")
                        print(f"Добавьте эту строку в ваш код:")
                        print(f"TELEGRAM_CHAT_ID = {chat_id}")
                        return chat_id
            
            raise RuntimeError("❌ Сообщения получены, но chat_id не найден")
    
    raise RuntimeError(f"❌ Таймаут: нет новых сообщений за {timeout} сек. Отправьте боту сообщение и запустите снова.")


if __name__ == "__main__":
    # Замените на ваш токен
    BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
    
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Пожалуйста, вставьте ваш BOT_TOKEN в переменную BOT_TOKEN")
        exit(1)
    
    try:
        chat_id = get_chat_id_force(BOT_TOKEN)
        print(f"\n✅ Готово! Используйте TELEGRAM_CHAT_ID = {chat_id}")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
