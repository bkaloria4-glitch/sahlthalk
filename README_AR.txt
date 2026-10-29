منصة سهلتهالك بكالوريا - نسخة Render + Neon

1) ارفع الملفات app.py و requirements.txt إلى جذر مستودع GitHub (بدل النسخة القديمة).
2) في Render Build Command: pip install -r requirements.txt
3) Start Command: gunicorn app:app
4) أضف Environment Variables في Render:
   DATABASE_URL = رابط الاتصال من Neon (Connection string)
   SECRET_KEY = قيمة عشوائية طويلة وفريدة
   ADMIN_USER = اسم مستخدم الإدارة الذي تختاره
   ADMIN_PASSWORD = كلمة مرور قوية وفريدة
5) لا تنشر رابط DATABASE_URL أو كلمات السر في GitHub أو في المحادثات.

ملاحظة: هذه النسخة تنشئ جداول جديدة في Neon تلقائياً. لا تنقل تلقائياً بيانات SQLite القديمة الموجودة على جهازك. احتفظ بقاعدة بياناتك المحلية ولا تحذفها.
