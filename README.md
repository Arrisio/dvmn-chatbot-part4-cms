### Курс "Чат-боты на Python"
https://dvmn.org/modules/chat-bots/lesson/devman-bot/

## Урок 5
[Продаём рыбу в Telegram](https://dvmn.org/modules/chat-bots/lesson/fish-shop/)  


## Установка

1. Клонировать репозиторий:
```
git clone https://github.com/Arrisio/dvmn-chatbot-part4-cms.git
```

2. Требуется определить следующие переменные окружения:
- `TG_BOT_TOKEN`=`Ваш токен`.
- `TG_BOT_ADMIN_ID`=`UserId админа бота в Telegram. Можно узнать у этого бота @userinfobot`

Учетные данные CMS Molten(elasticpath)
- `MOLTEN_STORE_ID`
- `MOLTEN_CLIENT_ID`
- `MOLTEN_CLIENT_SECRET`

Следующие переменные окружения опциональны:
- `REDIS_HOST` - IP или hostname базы redis. По умолчанию - `localhost`.  
- `REDIS_PORT` - порт базы redis. По умолчанию - `6379`.  
- `REDIS_DB` - Индекс базы redis. По умолчанию None.
- `REDIS_PASSWORD` - Пароль к редису. По умолчанию не требуется  
  
- `LOG_LEVEL` - уровень логирования, варианты значений - см. официальную документацию [Loguru](https://loguru.readthedocs.io/en/stable/api/logger.html). По умолчанию - `INFO`.
- `LOG_USE_JSON` - Выводить ли логи в JSON-формате. По умолчанию - False 

3. Установить зависимости:
```
pip3 install -r requirements.txt
```

## Запуск
```
python3 main.py
```

