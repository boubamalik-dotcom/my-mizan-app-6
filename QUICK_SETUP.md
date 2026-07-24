# ⚡ تثبيت سريع - خطوات بسيطة جداً

## 📋 ما تحتاجه قبل البدء

```
✅ Node.js (https://nodejs.org/)
✅ Git (https://git-scm.com/)
✅ حساب GitHub (https://github.com)
✅ حساب Vercel (https://vercel.com)
```

---

## 🚀 الخطوات (5 دقائق فقط!)

### **الخطوة 1: فتح Terminal/Command Prompt**

**Windows:**
- اضغط: `Win + R`
- اكتب: `cmd`
- اضغط: Enter

**Mac:**
- اضغط: `Cmd + Space`
- اكتب: `Terminal`
- اضغط: Enter

**Linux:**
- اضغط: `Ctrl + Alt + T`

---

### **الخطوة 2: إنشاء المشروع**

اكتب هذه الأوامر واحداً تلو الآخر:

```bash
cd Desktop
mkdir mizan-app
cd mizan-app
```

---

### **الخطوة 3: نسخ الملفات**

انسخ هذه الملفات من الـ outputs folder إلى مجلد `mizan-app`:

```
✅ package.json
✅ .gitignore
✅ vercel.json
✅ .env.example
✅ README.md

ثم أنشئ مجلدات وانسخ الملفات:

public/
  └─ index.html

src/
  ├─ App.jsx
  ├─ index.js
  └─ index.css
```

---

### **الخطوة 4: تثبيت المتطلبات**

```bash
npm install
```

**انتظر 2-3 دقائق...**

---

### **الخطوة 5: اختبار محلياً**

```bash
npm start
```

**يفتح تطبيقك على:** `http://localhost:3000`

👉 **اضغط على "صوّر إجابتك الآن" لاختبار التطبيق**

---

## 🌐 النشر على Vercel

### **الخطوة 1: رفع على GitHub**

```bash
git init
git add .
git commit -m "Al-Mizan App"
git branch -M main
```

ثم انسخ هذا الأمر من صفحة GitHub الجديدة:
```bash
git remote add origin https://github.com/YOUR_USERNAME/mizan-app.git
git push -u origin main
```

---

### **الخطوة 2: النشر على Vercel**

**الطريقة الأسهل:**

1. افتح: https://vercel.com/new
2. اختر: "Import from GitHub"
3. ابحث عن: mizan-app
4. اضغط: "Import"
5. اضغط: "Deploy"
6. انتظر 2 دقيقة...
7. ✅ رابطك جاهز!

---

## ✅ الرابط الحي

بعد النشر ستحصل على رابط مثل:
```
https://mizan-app.vercel.app
```

**شاركه مع الجميع! 🎉**

---

## 🐛 حل المشاكل البسيطة

| المشكلة | الحل |
|---------|------|
| خطأ npm | `npm install --legacy-peer-deps` |
| Port 3000 مشغول | أغلق البرنامج الآخر أو غيّر الـ port |
| لم تظهر التغييرات | اضغط: `Ctrl+Shift+R` |
| Build Failed | احذف `node_modules` وأعد `npm install` |

---

## 🎯 خلاصة

```
1️⃣ npm install
      ↓
2️⃣ npm start
      ↓
3️⃣ git push
      ↓
4️⃣ Deploy on Vercel
      ↓
✅ موقعك حي!
```

---

**تمّ بسهولة! 🚀**

**اي استفسار؟ انظر إلى `VERCEL_DEPLOYMENT_GUIDE.md` للتفاصيل الكاملة**
