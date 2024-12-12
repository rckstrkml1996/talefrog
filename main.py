import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получение токена из переменной окружения
TOKEN = os.getenv('7809877984:AAGz2HSxHev8HTBPtdIZpd7dQKAD1KOe6Pc')
if not TOKEN:
    raise ValueError("No token provided!")

class LinkProcessor:
    def __init__(self):
        self.saved_links = []
        self.pending_links = []
        self.waiting_for_filename = False

    async def start(self, update: Update, context):
        try:
            keyboard = [["RESTART"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(
                "Отправьте файл со ссылками или введите название для сохранения результатов",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error in start handler: {e}")
            await self.handle_error(update, "Произошла ошибка при запуске бота")

    async def handle_document(self, update: Update, context):
        try:
            if update.message.document:
                file = await context.bot.get_file(update.message.document.file_id)
                file_content = await file.download_as_bytearray()
                
                try:
                    links = file_content.decode('utf-8').splitlines()
                except UnicodeDecodeError:
                    links = file_content.decode('windows-1251').splitlines()
                
                self.pending_links = [link.strip() for link in links if link.strip()]
                
                await update.message.reply_text(f"Получено {len(self.pending_links)} ссылок. Начинаю обработку...")
                await self.process_next_link(update, context)
        except Exception as e:
            logger.error(f"Error in document handler: {e}")
            await self.handle_error(update, "Ошибка при обработке файла")

    async def handle_text(self, update: Update, context):
        try:
            if update.message.text == "RESTART":
                await self.handle_restart(update, context)
                return
            
            if not self.saved_links:
                if update.message.text.startswith('http'):
                    self.pending_links.append(update.message.text)
                    await self.process_next_link(update, context)
                else:
                    await update.message.reply_text("Пожалуйста, отправьте файл со ссылками")
            else:
                await self.save_results(update, update.message.text)
        except Exception as e:
            logger.error(f"Error in text handler: {e}")
            await self.handle_error(update, "Ошибка при обработке текста")

    async def save_results(self, update, filename):
        try:
            safe_filename = f"{filename}_{len(self.saved_links)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(safe_filename, 'w', encoding='utf-8') as f:
                f.write('\n'.join(self.saved_links))
            
            await update.message.reply_document(document=open(safe_filename, 'rb'))
            os.remove(safe_filename)  # Удаляем файл после отправки
            
            self.saved_links.clear()
            self.waiting_for_filename = False
        except Exception as e:
            logger.error(f"Error saving results: {e}")
            await self.handle_error(update, "Ошибка при сохранении результатов")

    async def process_next_link(self, update: Update, context):
        try:
            if not self.pending_links:
                if self.saved_links:
                    await update.effective_message.reply_text(
                        f"Все ссылки обработаны. Сохранено {len(self.saved_links)} ссылок.\n"
                        "Введите название для файла с результатами:"
                    )
                    self.waiting_for_filename = True
                else:
                    await update.effective_message.reply_text("Вы ничего не сохранили.")
                return

            url = self.pending_links.pop(0)
            await self.process_single_link(update, context, url)
        except Exception as e:
            logger.error(f"Error processing link: {e}")
            await self.handle_error(update, "Ошибка при обработке ссылки")

    async def process_single_link(self, update, context, url):
        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')

            metadata = self.extract_metadata(soup)
            await self.send_link_preview(update, url, metadata)
        except Exception as e:
            logger.error(f"Error processing single link {url}: {e}")
            await update.effective_message.reply_text(f"Ошибка при обработке ссылки: {url}")
            await self.process_next_link(update, context)

    def extract_metadata(self, soup):
        title = soup.select_one('meta[property="og:title"]')
        description = soup.select_one('meta[property="og:description"]')
        image_url = soup.select_one('meta[property="og:image"]')

        return {
            'title': title.get('content', 'Название не найдено') if title else 'Название не найдено',
            'description': description.get('content', 'Описание не найдено') if description else 'Описание не найдено',
            'image_url': image_url.get('content', None) if image_url else None
        }

    async def send_link_preview(self, update, url, metadata):
        keyboard = [
            [InlineKeyboardButton("Оставить", callback_data=f"save|{url}"),
             InlineKeyboardButton("Удалить", callback_data="delete")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        caption = (
            f"<b>Линк:</b>\n{url}\n"
            f"<b>Тайтл обьявы:</b>\n{metadata['title']}\n\n"
            f"<b>Описание обьявы:</b>\n{metadata['description']}"
        )

        if metadata['image_url']:
            await update.effective_message.reply_photo(
                photo=metadata['image_url'],
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        else:
            await update.effective_message.reply_text(
                caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )

    async def handle_error(self, update, message):
        await update.effective_message.reply_text(f"❌ {message}")

    async def handle_restart(self, update: Update, context):
        self.saved_links.clear()
        self.pending_links.clear()
        self.waiting_for_filename = False
        await update.message.reply_text("Бот перезапущен.")

def main():
    try:
        processor = LinkProcessor()
        application = Application.builder().token(TOKEN).build()

        application.add_handler(CommandHandler("start", processor.start))
        application.add_handler(MessageHandler(filters.Document.ALL, processor.handle_document))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processor.handle_text))
        application.add_handler(CallbackQueryHandler(processor.button_handler))

        logger.info("Bot started!")
        application.run_polling()
    except Exception as e:
        logger.error(f"Critical error: {e}")

if __name__ == "__main__":
    main()
