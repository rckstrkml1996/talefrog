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

saved_links = []
pending_links = []
waiting_for_filename = False

async def start(update: Update, context):
    keyboard = [["RESTART"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Отправьте файл со ссылками или введите название для сохранения результатов", reply_markup=reply_markup)

async def handle_document(update: Update, context):
    global pending_links
    
    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        file_content = await file.download_as_bytearray()
        
        # Декодируем содержимое файла и разбиваем на строки
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
        # Сохраняем результаты в файл
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
        # Добавляем заголовки для имитации браузера
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

        # Добавляем таймаут и заголовки
        response = requests.get(url, headers=headers, timeout=30, verify=False)
        response.raise_for_status()  # Проверяем статус ответа
        
        soup = BeautifulSoup(response.content, 'html.parser')

        # Расширенный поиск метаданных
        title = None
        description = None
        image_url = None

        # Пробуем разные варианты поиска title
        title_candidates = [
            soup.select_one('meta[property="og:title"]'),
            soup.select_one('meta[name="title"]'),
            soup.title,
            soup.select_one('h1')
        ]
        
        for candidate in title_candidates:
            if candidate:
                title = candidate.get('content', candidate.text) if hasattr(candidate, 'get') else candidate.text
                break

        # Пробуем разные варианты поиска description
        desc_candidates = [
            soup.select_one('meta[property="og:description"]'),
            soup.select_one('meta[name="description"]'),
            soup.select_one('meta[name="Description"]')
        ]
        
        for candidate in desc_candidates:
            if candidate:
                description = candidate.get('content')
                break

        # Пробуем разные варианты поиска image
        img_candidates = [
            soup.select_one('meta[property="og:image"]'),
            soup.select_one('meta[property="og:image:url"]'),
            soup.select_one('link[rel="image_src"]'),
            soup.select_one('img.primary-image'),
            soup.select_one('img[class*="main"]'),
            soup.select_one('img')
        ]
        
        for candidate in img_candidates:
            if candidate:
                image_url = candidate.get('content') or candidate.get('href') or candidate.get('src')
                if image_url:
                    # Если URL относительный, делаем его абсолютным
                    if image_url.startswith('/'):
                        from urllib.parse import urljoin
                        image_url = urljoin(url, image_url)
                    break

        title = title or 'Название не найдено'
        description = description or 'Описание не найдено'

        # Логируем найденные данные
        print(f"Found data for {url}:")
        print(f"Title: {title}")
        print(f"Description: {description}")
        print(f"Image URL: {image_url}")

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
            except Exception as img_error:
                print(f"Error sending image: {img_error}")
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
        error_message = f"Ошибка при обработке ссылки: {url}\nОшибка: {str(e)}"
        print(error_message)  # Добавляем вывод ошибки в консоль
        await update.effective_message.reply_text(error_message)
        await process_next_link(update, context)
        
async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()

    data = query.data

    # Получаем оригинальное сообщение с HTML-форматированием
    if query.message.caption:
        message_text = query.message.caption
    else:
        message_text = query.message.text

    # Извлекаем URL, заголовок и описание из оригинального сообщения
    try:
        # Разбиваем сообщение на части по маркерам
        url = message_text.split('Линк:\n')[1].split('\nТайтл')[0].strip()
        title = message_text.split('Тайтл обьявы:\n')[1].split('\nОписание')[0].strip()
        description = message_text.split('Описание обьявы:\n')[1].strip()
        
        # Формируем новое сообщение с правильным форматированием
        formatted_message = (
            f"<b>Линк:</b>\n"
            f"{url}\n"
            f"<b>Тайтл обьявы:</b>\n"
            f"{title}\n\n"
            f"<b>Описание обьявы:</b>\n"
            f"{description}"
        )
    except IndexError:
        formatted_message = message_text  # Если что-то пошло не так, используем оригинальное сообщение

    if data.startswith("save"):
        _, save_url = data.split("|", 1)
        saved_links.append(save_url)
        result_message = f"{formatted_message}\n\n<b>Сохранено! ✅</b>"
    elif data == "delete":
        result_message = f"{formatted_message}\n\n<b>Удалено! ❌</b>"

    # Редактируем сообщение с сохранением HTML-форматирования
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

    # Продолжаем обработку следующей ссылки
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
    # Изменен фильтр для документов
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Бот запущен!")
    app.run_polling()
