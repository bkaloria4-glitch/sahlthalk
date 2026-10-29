from flask import Flask, request, redirect, session, url_for, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg
from psycopg.rows import dict_row
from psycopg.errors import UniqueViolation
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "replace-this-before-online-use")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DEFAULT_CASH_NUMBER = "01279790505"
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")

SUBJECTS = [
    ("arabic", "اللغة العربية", "📘", "شرح ومراجعة وتدريبات اللغة العربية"),
    ("history", "التاريخ", "📙", "شرح ومراجعة أهم دروس التاريخ"),
    ("english", "اللغة الإنجليزية", "📗", "شرح ومراجعة وتدريبات اللغة الإنجليزية"),
]
QUIZZES = {
    "arabic": [("كلمة «الطالب» هي:", ["فعل", "اسم", "حرف"], 1),
               ("جمع كلمة «كتاب» هو:", ["كاتب", "كتابات فقط", "كتب"], 2)],
    "english": [("Choose the plural of 'book'.", ["bookes", "books", "bookies"], 1),
                ("Choose the opposite of 'big'.", ["small", "tall", "long"], 0)],
    "history": [("تقع الأهرامات الشهيرة في محافظة:", ["الجيزة", "أسوان", "مطروح"], 0)],
}
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&display=swap');
*{box-sizing:border-box}body{margin:0;background:#f3f6fb;color:#17243b;font-family:'Cairo',Tahoma,Arial,sans-serif;direction:rtl;font-size:17px;line-height:1.9}
nav{background:#102a43;color:#fff;padding:17px 5%;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
nav a{color:#fff;text-decoration:none;margin:4px 7px}.brand{font-weight:bold;font-size:20px}
.container{max-width:1100px;margin:28px auto;padding:0 16px}.hero{padding:36px;border-radius:20px;color:#fff;background:linear-gradient(120deg,#12365a,#087e8b)}
.hero h1{font-size:clamp(29px,4vw,44px);font-weight:800;line-height:1.45;margin-top:0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:17px;margin:22px 0}
.card,.box{background:#fff;padding:22px;border-radius:15px;box-shadow:0 6px 22px #12243a0b}.card h3{margin:10px 0;font-size:21px;font-weight:700}
.btn{display:inline-block;border:0;border-radius:9px;padding:11px 17px;background:#087e8b;color:#fff;text-decoration:none;cursor:pointer;font-family:inherit;font-weight:700;font-size:16px;margin-top:7px}
.btn.dark{background:#173653}.btn.red{background:#a32b35}
input{font-family:inherit;font-size:16px;width:100%;padding:12px;border:1px solid #cbd5e1;border-radius:8px;margin:8px 0 15px;font:inherit}
.quiz-question{background:#fff;border:1px solid #dfe7f0;border-radius:16px;padding:20px;margin:18px 0;box-shadow:0 5px 18px #12243a08}.quiz-question h3{font-size:20px;margin:0 0 14px}.answer-option{display:flex;align-items:center;gap:10px;border:1px solid #d8e1ec;border-radius:11px;padding:10px 13px;margin:9px 0;cursor:pointer;font-weight:500}.answer-option:has(input:checked){border-color:#087e8b;background:#eaf8f4}.answer-option input{width:auto;margin:0;accent-color:#087e8b}label{font-weight:bold}.notice{padding:13px;border-radius:9px;background:#e2f7eb;margin:12px 0}.error{padding:13px;border-radius:9px;background:#ffe8e8;margin:12px 0}
.price{font-size:22px;font-weight:bold;color:#087e8b}.cash{font-size:27px;font-weight:bold;letter-spacing:1px;direction:ltr;text-align:center;padding:18px;background:#eaf8f4;border:2px dashed #087e8b;border-radius:12px}
table{width:100%;border-collapse:collapse;background:#fff;margin:15px 0}th,td{text-align:right;padding:11px;border-bottom:1px solid #e4e9ef;vertical-align:top}
footer{text-align:center;padding:24px;color:#667085}
"""
def connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing. Add your Neon connection string in Render Environment Variables.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    schema = [
        "CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'student')",
        "CREATE TABLE IF NOT EXISTS courses(id BIGSERIAL PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',price DOUBLE PRECISION NOT NULL DEFAULT 0,visible INTEGER NOT NULL DEFAULT 1)",
        "CREATE TABLE IF NOT EXISTS payments(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,course_id BIGINT NOT NULL,sender_wallet TEXT NOT NULL,reference TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'pending',created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS enrollments(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,course_id BIGINT NOT NULL,UNIQUE(user_id,course_id))",
        "CREATE TABLE IF NOT EXISTS results(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,subject TEXT NOT NULL,score INTEGER NOT NULL,total INTEGER NOT NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS questions(id BIGSERIAL PRIMARY KEY,subject TEXT NOT NULL,question TEXT NOT NULL,opt1 TEXT NOT NULL,opt2 TEXT NOT NULL,opt3 TEXT NOT NULL,opt4 TEXT NOT NULL DEFAULT '',answer INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1)",
        "CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    ]
    with connect() as con:
        for statement in schema:
            con.execute(statement)
        con.execute("INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT (key) DO NOTHING", ("cash_number", DEFAULT_CASH_NUMBER))
        if con.execute("SELECT COUNT(*) AS count FROM questions").fetchone()["count"] == 0:
            for subject_key, quiz_items in QUIZZES.items():
                for question, options, answer in quiz_items:
                    padded = (options + ["", ""])[:4]
                    con.execute("INSERT INTO questions(subject,question,opt1,opt2,opt3,opt4,answer) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                                (subject_key, question, padded[0], padded[1], padded[2], padded[3], answer))
        if con.execute("SELECT COUNT(*) AS count FROM courses").fetchone()["count"] == 0:
            con.executemany("INSERT INTO courses(title,description,price) VALUES(%s,%s,%s)", [
                ("مراجعة اللغة العربية", "شرح ومراجعة وتدريبات اللغة العربية", 150),
                ("مراجعة التاريخ", "شرح ومراجعة أهم دروس التاريخ", 120),
                ("مراجعة اللغة الإنجليزية", "شرح ومراجعة وتدريبات اللغة الإنجليزية", 150)])
        if not con.execute("SELECT id FROM users WHERE username=%s", (ADMIN_USER,)).fetchone():
            con.execute("INSERT INTO users(username,password_hash,role) VALUES(%s,%s,%s)",
                        (ADMIN_USER, generate_password_hash(ADMIN_PASSWORD), "admin"))

def get_setting(key, default=""):
    with connect() as con:
        row = con.execute("SELECT value FROM settings WHERE key=%s", (key,)).fetchone()
    return row["value"] if row else default

def page(title, body, **ctx):
    template = """<!doctype html><html lang="ar"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ title }} | سهلتهالك بكالوريا</title>
    <style>""" + CSS + """</style></head><body><nav><a class="brand" href="/">🎓 سهلتهالك بكالوريا</a><div>
    <a href="/">الرئيسية</a><a href="/courses">الكورسات</a>
    {% if session.get('user_id') %}<a href="/account">حسابي</a><a href="/logout">خروج</a>
    {% else %}<a href="/login">دخول</a><a href="/register">إنشاء حساب</a>{% endif %}
    {% if session.get('role') == 'admin' %}<a href="/admin">لوحة الإدارة</a>{% endif %}
    </div></nav><main class="container"><h2>{{ title }}</h2>""" + body + """</main>
    <footer>سهلتهالك بكالوريا © منصة تعليمية</footer></body></html>"""
    return render_template_string(template, title=title, **ctx)

def login_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if not session.get("user_id"): return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return inner

def admin_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if session.get("role") != "admin": return "غير مسموح. سجّل الدخول بحساب الإدارة.", 403
        return fn(*args, **kwargs)
    return inner

@app.route("/")
def home():
    body = """<section class="hero"><h1>مستقبلك يبدأ من هنا 🚀</h1><p>ذاكر، اختبر نفسك، وتابع تقدمك في منصة واحدة.</p>
    <a class="btn" href="/courses">تصفح الكورسات</a> <a class="btn dark" href="/register">أنشئ حسابك مجانًا</a></section>
    <h2>المواد التعليمية</h2><div class="grid">{% for s in subjects %}<article class="card"><div style="font-size:35px">{{ s[2] }}</div>
    <h3>{{ s[1] }}</h3><p>{{ s[3] }}</p><a class="btn" href="/quiz/{{ s[0] }}">اختبر نفسك</a></article>{% endfor %}</div>"""
    return page("الرئيسية", body, subjects=SUBJECTS)

@app.route("/register", methods=["GET", "POST"])
def register():
    error = ""
    if request.method == "POST":
        username, password = request.form.get("username", "").strip(), request.form.get("password", "")
        if len(username) < 3 or len(password) < 6: error = "اسم المستخدم 3 أحرف على الأقل وكلمة المرور 6 أحرف على الأقل."
        else:
            try:
                with connect() as con:
                    con.execute("INSERT INTO users(username,password_hash) VALUES(%s,%s)", (username, generate_password_hash(password)))
                return redirect(url_for("login"))
            except UniqueViolation: error = "اسم المستخدم مستخدم بالفعل."
    body = """{% if error %}<div class="error">{{ error }}</div>{% endif %}<div class="box"><form method="post">
    <label>اسم المستخدم</label><input name="username" required minlength="3" autocomplete="username">
    <label>كلمة المرور</label><input type="password" name="password" required minlength="6" autocomplete="new-password">
    <button class="btn">إنشاء الحساب</button></form></div>"""
    return page("إنشاء حساب طالب", body, error=error)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        username, password = request.form.get("username", "").strip(), request.form.get("password", "")
        with connect() as con: user = con.execute("SELECT * FROM users WHERE username=%s", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear(); session["user_id"] = user["id"]; session["username"] = user["username"]; session["role"] = user["role"]
            return redirect(url_for("admin" if user["role"] == "admin" else "account"))
        error = "اسم المستخدم أو كلمة المرور غير صحيحة."
    body = """{% if error %}<div class="error">{{ error }}</div>{% endif %}<div class="box"><form method="post">
    <label>اسم المستخدم</label><input name="username" required autocomplete="username">
    <label>كلمة المرور</label><input type="password" name="password" required autocomplete="current-password">
    <button class="btn">تسجيل الدخول</button></form></div>"""
    return page("تسجيل الدخول", body, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/courses")
def courses():
    with connect() as con: items = con.execute("SELECT * FROM courses WHERE visible=1 ORDER BY id").fetchall()
    body = """<div class="grid">{% for c in courses %}<article class="card"><h3>{{ c['title'] }}</h3><p>{{ c['description'] }}</p>
    <p class="price">{{ "%.2f"|format(c['price']) }} جنيه</p><a class="btn" href="/course/{{ c['id'] }}">عرض الكورس والاشتراك</a></article>
    {% else %}<p>لا توجد كورسات متاحة.</p>{% endfor %}</div>"""
    return page("الكورسات المتاحة", body, courses=items)

@app.route("/course/<int:course_id>")
def course_detail(course_id):
    with connect() as con:
        c = con.execute("SELECT * FROM courses WHERE id=%s AND visible=1", (course_id,)).fetchone()
        enrolled = bool(session.get("user_id") and con.execute("SELECT 1 FROM enrollments WHERE user_id=%s AND course_id=%s", (session["user_id"], course_id)).fetchone())
    if not c: return "الكورس غير موجود.", 404
    body = """<div class="box"><h3>{{ c['title'] }}</h3><p>{{ c['description'] }}</p><p class="price">السعر: {{ "%.2f"|format(c['price']) }} جنيه مصري</p>
    {% if enrolled %}<div class="notice">أنت مشترك بالفعل في هذا الكورس.</div>{% elif session.get('user_id') %}
    <a class="btn" href="/pay/{{ c['id'] }}">اشترك الآن</a>{% else %}<a class="btn" href="/login">سجّل الدخول للاشتراك</a>{% endif %}</div>"""
    return page("تفاصيل الكورس", body, c=c, enrolled=enrolled)

@app.route("/pay/<int:course_id>", methods=["GET", "POST"])
@login_required
def pay(course_id):
    with connect() as con:
        c = con.execute("SELECT * FROM courses WHERE id=%s AND visible=1", (course_id,)).fetchone()
        enrolled = con.execute("SELECT 1 FROM enrollments WHERE user_id=%s AND course_id=%s", (session["user_id"], course_id)).fetchone()
        pending = con.execute("SELECT 1 FROM payments WHERE user_id=%s AND course_id=%s AND status='pending'", (session["user_id"], course_id)).fetchone()
    if not c: return "الكورس غير موجود.", 404
    if enrolled: return redirect(url_for("account"))
    error = ""
    if request.method == "POST":
        sender_wallet, reference = request.form.get("sender_wallet", "").strip(), request.form.get("reference", "").strip()
        if len(sender_wallet) < 5 or not reference: error = "اكتب رقم المحفظة المحوّل منها ورقم العملية."
        else:
            with connect() as con:
                con.execute("INSERT INTO payments(user_id,course_id,sender_wallet,reference) VALUES(%s,%s,%s,%s)",
                            (session["user_id"], course_id, sender_wallet, reference))
            return redirect(url_for("account"))
    body = """<div class="box"><h3>{{ c['title'] }}</h3><p class="price">المبلغ المطلوب: {{ "%.2f"|format(c['price']) }} جنيه</p>
    <h3>حوّل عبر فودافون كاش إلى الرقم التالي</h3><div class="cash" dir="ltr">{{ cash_number }}</div>
    <p>بعد التحويل، اكتب رقم المحفظة التي أرسلت منها ورقم العملية. سيُراجع الأدمن الطلب قبل تفعيل الكورس.</p>
    <div class="notice">لا ترسل كلمة مرور المحفظة أو رمز OTP لأي شخص. إدخال رقم العملية لا يؤكد وصول الأموال.</div>
    {% if pending %}<p>لديك طلب دفع معلّق بالفعل؛ تابع حالته من حسابك.</p>{% endif %}
    {% if error %}<div class="error">{{ error }}</div>{% endif %}<form method="post">
    <label>رقم المحفظة المحوّل منها</label><input name="sender_wallet" required minlength="5" placeholder="رقم الموبايل الذي تم التحويل منه">
    <label>رقم العملية / مرجع التحويل</label><input name="reference" required placeholder="اكتب رقم العملية">
    <button class="btn">إرسال طلب الدفع للمراجعة</button></form></div>"""
    return page("الدفع عبر فودافون كاش", body, c=c, cash_number=get_setting("cash_number", DEFAULT_CASH_NUMBER), error=error, pending=pending)

@app.route("/account")
@login_required
def account():
    with connect() as con:
        user = con.execute("SELECT username FROM users WHERE id=%s", (session["user_id"],)).fetchone()
        enrolled = con.execute("SELECT courses.title,courses.description FROM enrollments JOIN courses ON courses.id=enrollments.course_id WHERE enrollments.user_id=%s ORDER BY courses.title", (session["user_id"],)).fetchall()
        payments = con.execute("SELECT payments.*,courses.title FROM payments JOIN courses ON courses.id=payments.course_id WHERE payments.user_id=%s ORDER BY payments.id DESC", (session["user_id"],)).fetchall()
        results = con.execute("SELECT * FROM results WHERE user_id=%s ORDER BY id DESC", (session["user_id"],)).fetchall()
    body = """<div class="box"><h3>أهلًا {{ user['username'] }}</h3><h3>كورساتي</h3>
    {% for c in enrolled %}<p>✅ {{ c['title'] }} — {{ c['description'] }}</p>{% else %}<p>لم يتم تفعيل أي كورس بعد.</p>{% endfor %}
    <h3>طلبات الدفع</h3><table><tr><th>الكورس</th><th>رقم العملية</th><th>الحالة</th></tr>
    {% for p in payments %}<tr><td>{{ p['title'] }}</td><td>{{ p['reference'] }}</td><td>{{ 'قيد المراجعة' if p['status']=='pending' else ('تم القبول' if p['status']=='approved' else 'مرفوض') }}</td></tr>
    {% else %}<tr><td colspan="3">لا توجد طلبات دفع.</td></tr>{% endfor %}</table><h3>نتائج الاختبارات</h3>
    {% for r in results %}<p>{{ r['subject'] }}: {{ r['score'] }} من {{ r['total'] }}</p>{% else %}<p>لم تؤدِ أي اختبار بعد.</p>{% endfor %}</div>"""
    return page("حساب الطالب", body, user=user, enrolled=enrolled, payments=payments, results=results)

@app.route("/quiz/<subject>", methods=["GET", "POST"])
@login_required
def quiz(subject):
    subject_names = {s[0]: s[1] for s in SUBJECTS}
    if subject not in subject_names:
        return "المادة غير موجودة.", 404
    with connect() as con:
        rows = con.execute("SELECT * FROM questions WHERE subject=%s AND active=1 ORDER BY id", (subject,)).fetchall()
    if not rows:
        return page("اختبار " + subject_names[subject],
                    '<div class="box"><p>لا توجد أسئلة مضافة لهذه المادة حتى الآن.</p><a class="btn" href="/">الرئيسية</a></div>')
    questions = []
    for row in rows:
        options = [row["opt1"], row["opt2"], row["opt3"]]
        if row["opt4"].strip():
            options.append(row["opt4"])
        questions.append({"id": row["id"], "q": row["question"], "options": options, "answer": row["answer"]})
    if request.method == "POST":
        score = sum(1 for i, q in enumerate(questions) if request.form.get("q" + str(i)) == str(q["answer"]))
        with connect() as con:
            con.execute("INSERT INTO results(user_id,subject,score,total) VALUES(%s,%s,%s,%s)",
                        (session["user_id"], subject_names[subject], score, len(questions)))
        percent = round(score * 100 / len(questions))
        return page("نتيجة الاختبار", """
        <div class="box" style="text-align:center;padding:30px">
        <p>نتيجتك في {{ subject_name }}</p><div style="font-size:42px;font-weight:800;color:#087e8b">{{ score }} / {{ total }}</div>
        <p>النسبة: {{ percent }}%</p><a class="btn" href="/quiz/{{ subject }}">إعادة الاختبار</a>
        <a class="btn dark" href="/account">حسابي</a></div>""",
        subject_name=subject_names[subject], score=score, total=len(questions), percent=percent, subject=subject)
    body = """<form method="post">
    {% for q in questions %}
      <section class="quiz-question"><h3>{{ loop.index }}. {{ q.q }}</h3>
      {% set qi=loop.index0 %}
      {% for option in q.options %}
        <label class="answer-option"><input type="radio" name="q{{ qi }}" value="{{ loop.index0 }}" required><span>{{ option }}</span></label>
      {% endfor %}</section>
    {% endfor %}
    <button class="btn" style="width:100%;padding:15px">إنهاء الاختبار وحفظ النتيجة</button></form>"""
    return page("اختبار " + subject_names[subject], body, questions=questions)

@app.route("/admin", methods=["GET", "POST"])
@login_required
@admin_required
def admin():
    message = ""
    if request.method == "POST":
        action = request.form.get("action", "")
        with connect() as con:
            if action == "add_question":
                subject = request.form.get("subject", "").strip()
                question = request.form.get("question", "").strip()
                options = [request.form.get("opt1", "").strip(), request.form.get("opt2", "").strip(),
                           request.form.get("opt3", "").strip(), request.form.get("opt4", "").strip()]
                try: answer = int(request.form.get("answer", "0"))
                except ValueError: answer = -1
                valid_subjects = {item[0] for item in SUBJECTS}
                if subject in valid_subjects and question and all(options[i] for i in range(3)) and 0 <= answer < (4 if options[3] else 3):
                    con.execute("INSERT INTO questions(subject,question,opt1,opt2,opt3,opt4,answer) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                                (subject, question, options[0], options[1], options[2], options[3], answer))
                    message = "تمت إضافة السؤال بنجاح."
                else: message = "راجع المادة والسؤال والاختيارات والإجابة الصحيحة."
            elif action == "delete_question":
                qid = request.form.get("question_id", type=int)
                if qid: con.execute("DELETE FROM questions WHERE id=%s", (qid,)); message = "تم حذف السؤال."
            elif action == "add_course":
                title, description = request.form.get("title", "").strip(), request.form.get("description", "").strip()
                try: price = float(request.form.get("price", ""))
                except ValueError: price = -1
                if title and price >= 0:
                    con.execute("INSERT INTO courses(title,description,price) VALUES(%s,%s,%s)", (title, description, price)); message = "تمت إضافة الكورس."
                else: message = "تحقق من اسم الكورس والسعر."
            elif action == "edit_course":
                cid = request.form.get("course_id", type=int)
                title, description = request.form.get("title", "").strip(), request.form.get("description", "").strip()
                try: price = float(request.form.get("price", ""))
                except ValueError: price = -1
                if cid and title and price >= 0:
                    con.execute("UPDATE courses SET title=%s,description=%s,price=%s WHERE id=%s", (title, description, price, cid)); message = "تم تعديل بيانات الكورس."
                else: message = "تحقق من بيانات الكورس والسعر."
            elif action == "toggle_course":
                cid = request.form.get("course_id", type=int)
                if cid: con.execute("UPDATE courses SET visible=1-visible WHERE id=%s", (cid,)); message = "تم تغيير ظهور الكورس."
            elif action == "delete_course":
                cid = request.form.get("course_id", type=int)
                if cid:
                    used = con.execute("SELECT (SELECT COUNT(*) FROM payments WHERE course_id=%s)+(SELECT COUNT(*) FROM enrollments WHERE course_id=%s) AS count", (cid,cid)).fetchone()["count"]
                    if used: message = "لا يمكن حذف كورس له طلبات دفع أو اشتراكات؛ يمكنك إخفاؤه بدلًا من ذلك."
                    else: con.execute("DELETE FROM courses WHERE id=%s", (cid,)); message = "تم حذف الكورس."
            elif action in ("approve", "reject"):
                pid = request.form.get("payment_id", type=int)
                payment = con.execute("SELECT * FROM payments WHERE id=%s", (pid,)).fetchone() if pid else None
                if payment and payment["status"] == "pending":
                    status = "approved" if action == "approve" else "rejected"
                    con.execute("UPDATE payments SET status=%s WHERE id=%s", (status, pid))
                    if action == "approve": con.execute("INSERT INTO enrollments(user_id,course_id) VALUES(%s,%s) ON CONFLICT (user_id,course_id) DO NOTHING", (payment["user_id"], payment["course_id"]))
                    message = "تم تحديث حالة الطلب."
            elif action == "save_settings":
                cash = request.form.get("cash_number", "").strip()
                if len(cash) >= 8:
                    con.execute("INSERT INTO settings(key,value) VALUES('cash_number',%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (cash,))
                    message = "تم حفظ رقم فودافون كاش."
                else: message = "اكتب رقم محفظة صحيحًا."
            elif action == "change_admin_password":
                current = request.form.get("current_password", "")
                new_password = request.form.get("new_password", "")
                admin_user = con.execute("SELECT * FROM users WHERE id=%s AND role='admin'", (session["user_id"],)).fetchone()
                if admin_user and check_password_hash(admin_user["password_hash"], current) and len(new_password) >= 10:
                    con.execute("UPDATE users SET password_hash=%s WHERE id=%s", (generate_password_hash(new_password), session["user_id"]))
                    message = "تم تغيير كلمة مرور الأدمن."
                else: message = "كلمة المرور الحالية غير صحيحة أو الجديدة أقل من 10 أحرف."
            elif action == "remove_enrollment":
                uid = request.form.get("user_id", type=int); cid = request.form.get("course_id", type=int)
                if uid and cid:
                    con.execute("DELETE FROM enrollments WHERE user_id=%s AND course_id=%s", (uid,cid)); message = "تم إلغاء الاشتراك."

    with connect() as con:
        courses = con.execute("SELECT * FROM courses ORDER BY id DESC").fetchall()
        payments = con.execute("SELECT payments.*,users.username,courses.title,courses.price FROM payments JOIN users ON users.id=payments.user_id JOIN courses ON courses.id=payments.course_id ORDER BY payments.id DESC").fetchall()
        students = con.execute("SELECT id,username FROM users WHERE role='student' ORDER BY id DESC").fetchall()
        enrollments = con.execute("SELECT enrollments.user_id,enrollments.course_id,users.username,courses.title FROM enrollments JOIN users ON users.id=enrollments.user_id JOIN courses ON courses.id=enrollments.course_id ORDER BY users.username,courses.title").fetchall()
        user_count = len(students)
        questions = con.execute("SELECT * FROM questions ORDER BY id DESC").fetchall()
        results = con.execute("SELECT results.*,users.username FROM results JOIN users ON users.id=results.user_id ORDER BY results.id DESC LIMIT 100").fetchall()
    body = r'''{% if message %}<div class="notice">{{ message }}</div>{% endif %}
    <div class="grid"><div class="card"><h3>الطلاب</h3><p>{{ user_count }}</p></div><div class="card"><h3>الكورسات</h3><p>{{ courses|length }}</p></div><div class="card"><h3>طلبات الدفع</h3><p>{{ payments|length }}</p></div></div>
    <div class="box"><h3>إعدادات الدفع</h3><form method="post"><input type="hidden" name="action" value="save_settings"><label>رقم فودافون كاش الذي يظهر للطلاب</label><input name="cash_number" value="{{ cash_number }}" required><button class="btn">حفظ رقم الدفع</button></form></div>
    <div class="box"><h3>تغيير كلمة مرور الأدمن</h3><form method="post"><input type="hidden" name="action" value="change_admin_password"><label>كلمة المرور الحالية</label><input type="password" name="current_password" required><label>كلمة المرور الجديدة (10 أحرف على الأقل)</label><input type="password" name="new_password" minlength="10" required><button class="btn dark">تغيير كلمة المرور</button></form></div>
    <div class="box"><h3>إضافة كورس</h3><form method="post"><input type="hidden" name="action" value="add_course"><label>اسم الكورس</label><input name="title" required><label>الوصف</label><input name="description"><label>السعر بالجنيه</label><input type="number" min="0" step="0.01" name="price" required><button class="btn">إضافة الكورس</button></form></div>
    <h3>إدارة الكورسات</h3><div class="grid">{% for c in courses %}<div class="card"><form method="post"><input type="hidden" name="action" value="edit_course"><input type="hidden" name="course_id" value="{{ c['id'] }}"><label>اسم الكورس</label><input name="title" value="{{ c['title'] }}" required><label>الوصف</label><input name="description" value="{{ c['description'] }}"><label>السعر</label><input type="number" min="0" step="0.01" name="price" value="{{ c['price'] }}" required><button class="btn">حفظ التعديل</button></form><p>{{ 'ظاهر للطلاب' if c['visible'] else 'مخفي' }}</p><form method="post"><input type="hidden" name="action" value="toggle_course"><input type="hidden" name="course_id" value="{{ c['id'] }}"><button class="btn dark">{{ 'إخفاء الكورس' if c['visible'] else 'إظهار الكورس' }}</button></form><form method="post" onsubmit="return confirm('حذف الكورس نهائيًا؟')"><input type="hidden" name="action" value="delete_course"><input type="hidden" name="course_id" value="{{ c['id'] }}"><button class="btn red">حذف الكورس إذا لم يكن مرتبطًا بطلبات</button></form></div>{% endfor %}</div>
    <div class="box"><h3>إضافة سؤال جديد</h3><form method="post"><input type="hidden" name="action" value="add_question"><label>المادة</label><select name="subject" required style="width:100%;padding:12px;font:inherit;margin:8px 0 15px">{% for sid,sname,icon,desc in subjects %}<option value="{{ sid }}">{{ sname }}</option>{% endfor %}</select><label>نص السؤال</label><input name="question" required><label>الاختيار الأول</label><input name="opt1" required><label>الاختيار الثاني</label><input name="opt2" required><label>الاختيار الثالث</label><input name="opt3" required><label>الاختيار الرابع (اختياري)</label><input name="opt4"><label>رقم الإجابة الصحيحة</label><select name="answer" required style="width:100%;padding:12px;font:inherit;margin:8px 0 15px"><option value="0">الاختيار الأول</option><option value="1">الاختيار الثاني</option><option value="2">الاختيار الثالث</option><option value="3">الاختيار الرابع</option></select><button class="btn">حفظ السؤال</button></form></div>
    <h3>الأسئلة المضافة</h3><div class="box"><table><tr><th>المادة</th><th>السؤال</th><th>الإجراء</th></tr>{% for q in questions %}<tr><td>{{ q['subject'] }}</td><td>{{ q['question'] }}</td><td><form method="post" onsubmit="return confirm('متأكد من حذف السؤال؟')"><input type="hidden" name="action" value="delete_question"><input type="hidden" name="question_id" value="{{ q['id'] }}"><button class="btn red">حذف</button></form></td></tr>{% else %}<tr><td colspan="3">لا توجد أسئلة.</td></tr>{% endfor %}</table></div>
    <h3>الطلاب والاشتراكات</h3><div class="box"><table><tr><th>اسم الطالب</th><th>الكورسات المفعلة</th></tr>{% for st in students %}<tr><td>{{ st['username'] }}</td><td>{% for e in enrollments if e['user_id']==st['id'] %}<div>{{ e['title'] }} <form method="post" style="display:inline"><input type="hidden" name="action" value="remove_enrollment"><input type="hidden" name="user_id" value="{{ st['id'] }}"><input type="hidden" name="course_id" value="{{ e['course_id'] }}"><button class="btn red">إلغاء الاشتراك</button></form></div>{% else %}لا توجد اشتراكات{% endfor %}</td></tr>{% else %}<tr><td colspan="2">لا يوجد طلاب حتى الآن.</td></tr>{% endfor %}</table></div>
    <h3>مراجعة طلبات فودافون كاش</h3><div class="box"><table><tr><th>الطالب</th><th>الكورس</th><th>المبلغ</th><th>محفظة الطالب</th><th>رقم العملية</th><th>الحالة</th><th>الإجراء</th></tr>{% for p in payments %}<tr><td>{{ p['username'] }}</td><td>{{ p['title'] }}</td><td>{{ "%.2f"|format(p['price']) }} ج.م</td><td>{{ p['sender_wallet'] }}</td><td>{{ p['reference'] }}</td><td>{{ 'قيد المراجعة' if p['status']=='pending' else ('مقبول' if p['status']=='approved' else 'مرفوض') }}</td><td>{% if p['status']=='pending' %}<form method="post"><input type="hidden" name="payment_id" value="{{ p['id'] }}"><button class="btn" name="action" value="approve">قبول وتفعيل</button><button class="btn red" name="action" value="reject">رفض</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="7">لا توجد طلبات دفع حتى الآن.</td></tr>{% endfor %}</table></div>
    <h3>آخر نتائج الاختبارات</h3><div class="box"><table><tr><th>الطالب</th><th>المادة</th><th>النتيجة</th><th>التاريخ</th></tr>{% for r in results %}<tr><td>{{ r['username'] }}</td><td>{{ r['subject'] }}</td><td>{{ r['score'] }} / {{ r['total'] }}</td><td>{{ r['created_at'] }}</td></tr>{% else %}<tr><td colspan="4">لا توجد نتائج بعد.</td></tr>{% endfor %}</table></div>'''
    return page("لوحة الإدارة", body, message=message, courses=courses, payments=payments, students=students, enrollments=enrollments, user_count=user_count, cash_number=get_setting("cash_number", DEFAULT_CASH_NUMBER), questions=questions, subjects=SUBJECTS, results=results)

init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
