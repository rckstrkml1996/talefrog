
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode
import logging
import sys
from requests.exceptions import RequestException
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_log.txt', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Глобальные переменные
saved_links = []
pending_links = []
waiting_for_filename = False

# Файлы для хранения ID админов и пользователей
ADMINS_FILE = "admins.txt"
USERS_FILE = "users.txt"

def get_date_of_publication(soup: BeautifulSoup) -> str:
    try:
        # Ищем все span элементы с возможными классами
        possible_classes = [
            "x193iq5w xeuugli x13faqbe x1vvkbs xlh3980 xvmahel x1n0sxbx x1lliihq x1s928wv xhkezso x1gmr53x x1cpjm7i x1fgarty x1943h6x x4zkp8e x3x7a5m x6prxxf xvq8zen xo1l8bm xzsf02u x1yc453h",
            "x193iq5w xeuugli x13faqbe x1vvkbs x1xmvt09 x1lliihq x1s928wv xhkezso x1gmr53x x1cpjm7i x1fgarty x1943h6x xudqn12 x3x7a5m x6prxxf xvq8zen xo1l8bm xzsf02u x1yc453h"
        ]
        
        for class_name in possible_classes:
            spans = soup.find_all("span", class_=class_name)
            for span in spans:
                if 'Listed' in span.text:
                    return span.text.strip()
        return "No information"
    except Exception as e:
        return f"Error getting date: {str(e)}"

# Функции для работы с админами и пользователями
def load_ids_from_file(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return set(map(int, f.read().splitlines()))
    return set()

def save_ids_to_file(ids, filename):
    with open(filename, 'w') as f:
        f.write('\n'.join(map(str, ids)))

def is_admin(user_id):
    admins = load_ids_from_file(ADMINS_FILE)
    return user_id in admins

def is_user(user_id):
    users = load_ids_from_file(USERS_FILE)
    return user_id in users

async def start(update: Update, context):
    user_id = update.effective_user.id
    
    if not (is_admin(user_id) or is_user(user_id)):
        await update.message.reply_text("Пошёл нахуй.\nТвой айди: " + str(user_id))
        return
    
    keyboard = [["RESTART"]]
    if is_admin(user_id):
        keyboard[0].append("ADD USER")
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Кидай ссылка на абьяву",
        reply_markup=reply_markup
    )

async def add_user(update: Update, context):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("Пошел нахуй.")
        return
    
    try:
        new_user_id = int(update.message.text.split()[1])
        users = load_ids_from_file(USERS_FILE)
        users.add(new_user_id)
        save_ids_to_file(users, USERS_FILE)
        await update.message.reply_text(f"Пользователь {new_user_id} успешно добавлен.")
    except (IndexError, ValueError):
        await update.message.reply_text("Пожалуйста, укажите корректный ID пользователя.\nФормат: /add_user ID")

async def handle_document(update: Update, context):
    user_id = update.effective_user.id
    
    if not (is_admin(user_id) or is_user(user_id)):
        await update.message.reply_text("У вас нет доступа к боту.")
        return

    global pending_links
    
    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        file_content = await file.download_as_bytearray()
        
        try:
            links = file_content.decode('utf-8').splitlines()
        except UnicodeDecodeError:
            links = file_content.decode('windows-1251').splitlines()
            
        pending_links = [link.strip() for link in links if link.strip()]
        
        await update.message.reply_text(f"Получено {len(pending_links)} ссылок. Начинаю обработку...")
        await process_next_link(update, context)

async def handle_text(update: Update, context):
    user_id = update.effective_user.id
    
    if not (is_admin(user_id) or is_user(user_id)):
        await update.message.reply_text("У вас нет доступа к боту.")
        return

    global waiting_for_filename
    
    if update.message.text == "RESTART":
        await handle_restart(update, context)
        return
    
    if update.message.text == "ADD USER" and is_admin(user_id):
        await update.message.reply_text("/add_user ID")
        return
    
    if not saved_links:
        if update.message.text.startswith('http'):
            pending_links.append(update.message.text)
            await process_next_link(update, context)
        else:
            await update.message.reply_text("Пожалуйста, отправьте файл со ссылками")
    else:
        filename = f"{update.message.text} {len(saved_links)}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('\n'.join(saved_links))
        await update.message.reply_document(
            document=open(filename, 'rb'),
        )
        saved_links.clear()
        waiting_for_filename = False

async def process_next_link(update: Update, context):
    user_id = update.effective_user.id
    
    if not (is_admin(user_id) or is_user(user_id)):
        await update.message.reply_text("У вас нет доступа к боту.")
        return

    if not pending_links:
        if saved_links:
            await update.effective_message.reply_text(
                f"Все ссылки обработаны. Сохранено {len(saved_links)} ссылок.\n"
                "Введите название для файла с результатами:"
            )
            global waiting_for_filename
            waiting_for_filename = True
        else:
            await update.effective_message.reply_text("Вы ничего не сохранили.")
        return

    url = pending_links.pop(0)
    if not url.startswith("http"):
        logger.warning(f"Некорректная ссылка: {url}")
        await update.effective_message.reply_text(f"Некорректная ссылка: {url}")
        await process_next_link(update, context)
        return

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        logger.info(f"Начало обработки URL: {url}")
        
        # Попытка получить страницу
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            logger.info(f"Успешно получен ответ от сервера. Статус: {response.status_code}")
        except RequestException as e:
            logger.error(f"Ошибка при получении страницы {url}: {str(e)}")
            await update.effective_message.reply_text(f"Ошибка при получении страницы: {url}\nОшибка: {str(e)}")
            await process_next_link(update, context)
            return

        # Парсинг страницы
        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            logger.info("Успешно создан объект BeautifulSoup")
        except Exception as e:
            logger.error(f"Ошибка при парсинге HTML: {str(e)}")
            await update.effective_message.reply_text(f"Ошибка при парсинге страницы: {url}\nОшибка: {str(e)}")
            await process_next_link(update, context)
            return

        # Получение метаданных
        try:
            title = soup.select_one('meta[property="og:title"]')
            description = soup.select_one('meta[property="og:description"]')
            image_url = soup.select_one('meta[property="og:image"]')
            publication_date = get_date_of_publication(soup)

            logger.info(f"Найденные метаданные:")
            logger.info(f"Title meta tag: {title}")
            logger.info(f"Description meta tag: {description}")
            logger.info(f"Image URL meta tag: {image_url}")
            logger.info(f"Publication date: {publication_date}")

            title = title.get('content', 'Название не найдено') if title else 'Название не найдено'
            description = description.get('content', 'Описание не найдено') if description else 'Описание не найдено'
            image_url = image_url.get('content', None) if image_url else None

        except Exception as e:
            logger.error(f"Ошибка при извлечении метаданных: {str(e)}")
            title = "Название не найдено"
            description = "Описание не найдено"
            image_url = None
            publication_date = "Дата не найдена"

        # Создание клавиатуры и сообщения
        keyboard = [
            [InlineKeyboardButton("Оставить", callback_data=f"save|{url}"),
             InlineKeyboardButton("Удалить", callback_data="delete")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        caption = (f"<b>Линк:</b>\n{url}\n"
                  f"<b>Тайтл обьявы:</b>\n{title}\n\n"
                  f"<b>Описание обьявы:</b>\n{description}\n\n"
                  f"<b>Дата публикации:</b>\n{publication_date}")

        # Отправка сообщения
        try:
            if image_url:
                logger.info(f"Попытка отправить сообщение с фото: {image_url}")
                try:
                    await update.effective_message.reply_photo(
                        photo=image_url, 
                        caption=caption, 
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML
                    )
                    logger.info("Фото успешно отправлено")
                except Exception as e:
                    logger.error(f"Ошибка при отправке фото: {str(e)}")
                    await update.effective_message.reply_text(
                        caption, 
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML
                    )
            else:
                logger.info("Отправка сообщения без фото")
                await update.effective_message.reply_text(
                    caption, 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {str(e)}")
            await update.effective_message.reply_text(f"Ошибка при отправке сообщения: {str(e)}")

    except Exception as e:
        logger.error(f"Неожиданная ошибка при обработке ссылки {url}: {str(e)}")
        await update.effective_message.reply_text(f"Неожиданная ошибка при обработке ссылки: {url}\nОшибка: {str(e)}")
    
    finally:
        await process_next_link(update, context)


async def button_handler(update: Update, context):
    user_id = update.effective_user.id
    
    if not (is_admin(user_id) or is_user(user_id)):
        await update.callback_query.answer("У вас нет доступа к боту.")
        return

    query = update.callback_query
    await query.answer()

    data = query.data

    if query.message.caption:
        message_text = query.message.caption
    else:
        message_text = query.message.text

    try:
        url = message_text.split('Линк:\n')[1].split('\nТайтл')[0].strip()
        title = message_text.split('Тайтл обьявы:\n')[1].split('\nОписание')[0].strip()
        description = message_text.split('Описание обьявы:\n')[1].split('\nДата')[0].strip()
        publication_date = message_text.split('Дата публикации:\n')[1].strip()
        
        formatted_message = (
            f"<b>Линк:</b>\n"
            f"{url}\n"
            f"<b>Тайтл обьявы:</b>\n"
            f"{title}\n\n"
            f"<b>Описание обьявы:</b>\n"
            f"{description}\n\n"
            f"<b>Дата публикации:</b>\n"
            f"{publication_date}"
        )
    except IndexError:
        formatted_message = message_text

    if data.startswith("save"):
        _, save_url = data.split("|", 1)
        saved_links.append(save_url)
        result_message = f"{formatted_message}\n\n<b>Сохранено! ✅</b>"
    elif data == "delete":
        result_message = f"{formatted_message}\n\n<b>Удалено! ❌</b>"

    if query.message.caption:
        await query.edit_message_caption(
            caption=result_message,
            parse_mode=ParseMode.HTML
        )
    else:
        await query.edit_message_text(
            text=result_message,
            parse_mode=ParseMode.HTML
        )

    await process_next_link(update, context)

async def handle_restart(update: Update, context):
    user_id = update.effective_user.id
    
    if not (is_admin(user_id) or is_user(user_id)):
        await update.message.reply_text("У вас нет доступа к боту.")
        return

    global saved_links, pending_links, waiting_for_filename
    saved_links.clear()
    pending_links.clear()
    waiting_for_filename = False
    await update.message.reply_text("Бот перезапущен.")

if __name__ == "__main__":
    # Проверка версий библиотек
    logger.info("Starting bot...")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"BeautifulSoup version: {bs4.__version__}")
    logger.info(f"Requests version: {requests.__version__}")
    logger.info(f"python-telegram-bot version: {telegram.__version__}")

    # Создаем файлы для админов и пользователей, если их нет
    if not os.path.exists(ADMINS_FILE):
        with open(ADMINS_FILE, 'w') as f:
            f.write("7961435399\n")  # Замените на ваш ID
        logger.info(f"Created {ADMINS_FILE}")

    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w') as f:
            pass
        logger.info(f"Created {USERS_FILE}")

    try:
        app = ApplicationBuilder().token("7721305352:AAGGTi9daJfIJc-NFlz0JVEuZGYTHeI0eLU").build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("add_user", add_user))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(CallbackQueryHandler(button_handler))

        logger.info("Bot handlers configured successfully")
        logger.info("Bot started!")
        app.run_polling()
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
