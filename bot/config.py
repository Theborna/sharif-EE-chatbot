import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # API Configuration
    API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8020")
    API_USERNAME = os.getenv("API_USERNAME", "admin")
    API_PASSWORD = os.getenv("API_PASSWORD", "admin")
    
    # Bot Configuration
    WELCOME_TEXT = """
🤖 سلام!
من دستیار هوش مصنوعی دانشکده برق شریف هستم و می‌توانم به شما کمک کنم
مستقیماً از تلگرام با من گفتگو کنید!

من با یک مدل زبان بزرگ (LLM) سفارشی پشتیبانی می‌شوم و می‌توانم به سوالات شما به فارسی و انگلیسی پاسخ دهم.

🛠️ دستورات موجود:
/start, /help - نمایش این پیام خوش‌آمدگویی
/ping - بررسی زمان پاسخ‌دهی ربات
/report <پیام> - ارسال گزارش به مدیران
/ask <سوال> - هر چیزی که می‌خواهید از من بپرسید! (فقط در چت‌های گروهی لازم است)
/new_chat - شروع یک گفتگوی جدید (پاک شدن تاریخچه قبلی)
/end_chat - پایان گفتگوی فعلی شما
/enable_memory - فعال کردن حافظه برای این گفتگو
/disable_memory - غیرفعال کردن حافظه برای این گفتگو

💡 نکته: در پیام‌های خصوصی می‌توانید مستقیماً با من صحبت کنید و نیازی به /ask نیست. 
در چت‌های گروهی باید از /ask <سوال> استفاده کنید.

💡 حالت اینلاین: شما می‌توانید من را در هر چت دیگری با تایپ کردن
@sharif_EE_chatbot و سپس سوال خود استفاده کنید!
هنگامی که تایپ کردن را متوقف کنید، یک پنجره "پرسیدن سوال" ظاهر می‌شود.
روی آن کلیک کنید تا سوال ارسال شود و پاسخ همان‌جا نمایش داده شود.

فقط یک پیام برای من بفرستید و من سعی می‌کنم کمک کنم! 🚀
    """

    CURRENT_APIS = ["Custom LLM", "Ping Service", "Report System", "Inline Queries"]
    
    # Directories
    REPORTS_DIR = "./reports"
    
    @classmethod
    def ensure_directories(cls):
        """Create necessary directories if they don't exist"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
