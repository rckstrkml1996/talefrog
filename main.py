try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
    from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
    from telegram.constants import ParseMode
except ModuleNotFoundError:
    print("Error: 'python-telegram-bot' library is not installed. Please install it using 'pip install python-telegram-bot'.")
    exit()

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from requests.sessions import Session
import warnings
from urllib3.exceptions import InsecureRequestWarning

# Suppress SSL warnings
warnings.filterwarnings('ignore', category=InsecureRequestWarning)

saved_links = []
pending_links = []
waiting_for_filename = False

def create_session():
    session = Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    session.headers.update(headers)
    return session

async def start(update: Update, context):
    keyboard = [["RESTART"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Отправьте файл со ссылками или введите название для сохранения результатов", reply_markup=reply_markup)

async def handle_document(update: Update, context):
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
    global waiting_for_filename
    
    if update.message.text == "RESTART":
        await handle_restart(update, context)
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
        await update.effective_message.reply_text(f"Некорректная ссылка: {url}")
        await process_next_link(update, context)
        return

    try:
        session = create_session()
        response = session.get(url, verify=False, timeout=10)
        
        if 'facebook.com' in url:
            title = "Facebook Marketplace Item"
            description = "Facebook content cannot be directly scraped. Please save the link if needed."
            image_url = None
        else:
            soup = BeautifulSoup(response.content, 'html.parser')
            title = soup.select_one('meta[property="og:title"]')
            description = soup.select_one('meta[property="og:description"]')
            image_url = soup.select_one('meta[property="og:image"]')

            title = title.get('content', 'Название не найдено') if title else 'Название не найдено'
            description = description.get('content', 'Описание не найдено') if description else 'Описание не найдено'
            image_url = image_url.get('content', None) if image_url else None

        keyboard = [
            [InlineKeyboardButton("Оставить", callback_data=f"save|{url}"),
             InlineKeyboardButton("Удалить", callback_data="delete")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        caption = f"<b>Линк:</b>\n{url}\n<b>Тайтл обьявы:</b>\n{title}\n\n<b>Описание обьявы:</b>\n{description}"
        
        if image_url:
            try:
                await update.effective_message.reply_photo(
                    photo=image_url, 
                    caption=caption, 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                # If photo sending fails, send as text
                await update.effective_message.reply_text(
                    caption, 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
        else:
            await update.effective_message.reply_text(
                caption, 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        await update.effective_message.reply_text(f"Ошибка при обработке ссылки: {url}\nОшибка: {str(e)}")
        await process_next_link(update, context)

async def button_handler(update: Update, context):
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
        description = message_text.split('Описание обьявы:\n')[1].strip()
        
        formatted_message = (
            f"<b>Линк:</b>\n"
            f"{url}\n"
            f"<b>Тайтл обьявы:</b>\n"
            f"{title}\n\n"
            f"<b>Описание обьявы:</b>\n"
            f"{description}"
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
    global saved_links, pending_links, waiting_for_filename
    saved_links.clear()
    pending_links.clear()
    waiting_for_filename = False
    await update.message.reply_text("Бот перезапущен.")

if __name__ == "__main__":
    app = ApplicationBuilder().token("7809877984:AAGz2HSxHev8HTBPtdIZpd7dQKAD1KOe6Pc").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Бот запущен!")
    app.run_polling()
