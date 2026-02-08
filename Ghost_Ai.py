import tkinter as tk
from tkinter import scrolledtext, messagebox
import requests
import json
import threading
import os
from datetime import datetime
from tkinter import filedialog
import docx
import PyPDF2
import random
import re

# clear code
def clean_markdown(text):

    # إزالة **
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)

    # إزالة __
    text = re.sub(r"__(.*?)__", r"\1", text)

    # إزالة ##
    text = re.sub(r"#+\s*", "", text)

    # تنظيف الجداول
    text = re.sub(r"\|", " | ", text)

    # إزالة ---
    text = re.sub(r"-{3,}", "", text)

    return text.strip()


KNOWLEDGE_FOLDER = "knowledge"
os.makedirs(KNOWLEDGE_FOLDER, exist_ok=True)

def load_knowledge_files():

    data = {}

    for file in os.listdir(KNOWLEDGE_FOLDER):

        if file.endswith(".txt"):

            path = os.path.join(KNOWLEDGE_FOLDER, file)

            with open(path, "r", encoding="utf-8") as f:
                data[file] = f.read()

    return data

def search_knowledge_snippet(question, snippet_length=300):
    """
    تبحث في ملفات المعرفة وتُرجع جزء صغير من الملف يحتوي على أكثر الكلمات تطابقًا مع السؤال
    """
    files_data = load_knowledge_files()
    keywords = re.findall(r"\w+", question.lower())
    
    best_file = None
    best_score = 0
    best_snippet = ""
    
    for file, content in files_data.items():
        text_lower = content.lower()
        score = 0
        # احسب التطابق
        for word in keywords:
            score += text_lower.count(word)
        
        if score > best_score:
            best_score = score
            best_file = file
            # أبحث عن أول ظهور للكلمة الأكثر تطابقاً
            first_index = len(content)
            for word in keywords:
                idx = text_lower.find(word)
                if idx != -1 and idx < first_index:
                    first_index = idx
            # قص جزء مناسب قبل وبعد الكلمة (snippet)
            start = max(0, first_index - snippet_length//2)
            end = min(len(content), first_index + snippet_length//2)
            best_snippet = content[start:end].strip()
    
    if best_score > 0:
        return best_file, best_snippet
    return None, None

def build_knowledge_prompt(question):
    file, snippet = search_knowledge_snippet(question)
    
    if not file:
        return None

    prompt = f"""
أنت مساعد ذكي.

المعلومات التالية مقتطفة من ملف محلي اسمه: {file}

{snippet}

سؤال المستخدم:
{question}

استخدم هذه المعلومات فقط للإجابة.
 صغ الإجابة باللغة العربية وبشكل واضح ومهني
"""
    return prompt

DATA_FOLDER = "data"
os.makedirs(DATA_FOLDER, exist_ok=True)


def load_text_data(filename):
    path = os.path.join(DATA_FOLDER, filename)

    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]
def get_from_files(user_msg):

    msg = user_msg.lower()

    if "نكت" in msg or "نكتة" in msg or "ضحكني" in msg:
        data = load_text_data("jokes.txt")

    elif "فزورة" in msg or "لغز" in msg:
        data = load_text_data("riddles.txt")

    elif "معلومة" in msg or "هل تعلم" in msg:
        data = load_text_data("facts.txt")

    else:
        return None

    if data:
        return random.choice(data)

    return None


# إعدادات Ollama
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gpt-oss:20b"

# مجلدات الحفظ
SAVE_FOLDER = "chats"
HISTORY_FILE = "chat_history.json"

os.makedirs(SAVE_FOLDER, exist_ok=True)

# ملف المحادثة الحالي
CHAT_FILE = os.path.join(
    SAVE_FOLDER,
    f"chat_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
)

# ألوان
BG_COLOR = "#0f172a"
CHAT_BG = "#020617"
USER_COLOR = "#38bdf8"
AI_COLOR = "#a7f3d0"
THINKING_COLOR = "#fbbf24"
TEXT_COLOR = "#ffffff"
BTN_COLOR = "#1e293b"

class ChatMemory:
    def __init__(self):
        self.conversation_history = []
        self.max_history = 30
        self.load_history()
    
    def add_message(self, role, content):
        self.conversation_history.append({"role": role, "content": content})
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]
        self.save_history()
    
    def get_context(self):
        return self.conversation_history
    
    def clear(self):
        self.conversation_history = []
        self.save_history()
    
    def save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.conversation_history, f, ensure_ascii=False, indent=2)
        except: pass
    
    def load_history(self):
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    self.conversation_history = json.load(f)
        except: self.conversation_history = []

chat_memory = ChatMemory()

# معلومات أساسية ثابتة
BASE_MEMORY = [
    {
        "role": "system",
        "content": "اسم المستخدم محمد. اسم المساعد جوست."
    }
]

CURRENT_FILE_CONTENT = None
CURRENT_FILE_NAME = None


# لو الملف فاضي، ضيف الذاكرة الأساسية
if not chat_memory.conversation_history:
    chat_memory.conversation_history = BASE_MEMORY.copy()
    chat_memory.save_history()


def save_to_file(text):
    with open(CHAT_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")

def show_user(msg):

    chat.config(state="normal")

    chat.insert(tk.END, "\n")

    chat.insert(tk.END, "أنت:\n", "user_label")
    chat.insert(tk.END, msg + "\n\n", "user")

    chat.config(state="disabled")
    chat.see(tk.END)

    chat_memory.add_message("user", msg)

def show_thinking():
    chat.config(state="normal")
    thinking_msg = "   أفكر..."
    chat.insert(tk.END, thinking_msg, "thinking")
    chat.mark_set("thinking_start", "end-1c linestart")
    chat.mark_gravity("thinking_start", "left")
    chat.config(state="disabled")
    chat.see(tk.END)
    return "thinking_start"

def hide_thinking_and_show_ai(thinking_mark, msg):

    chat.config(state="normal")

    thinking_start = chat.index(thinking_mark)
    chat.delete(thinking_start, "end-1c")

    # تنظيف الرد من Markdown
    msg = clean_markdown(msg)

    chat.insert(tk.END, "جوست:\n", "ai_label")
    chat.insert(tk.END, msg + "\n\n", "ai")

    chat.config(state="disabled")
    chat.see(tk.END)

    chat_memory.add_message("assistant", msg)
    save_to_file(f"AI: {msg}\n")


def show_ai(msg):

    chat.config(state="normal")

    # تنظيف الرد من Markdown
    msg = clean_markdown(msg)

    chat.insert(tk.END, "جوست:\n", "ai_label")
    chat.insert(tk.END, msg + "\n\n", "ai")

    chat.config(state="normal") # this line is important to allow copying the AI response
    chat.see(tk.END)

    chat_memory.add_message("assistant", msg)


def build_context_prompt(prompt):
    context = chat_memory.get_context()

    system_info = ""
    for msg in context:
        if msg["role"] == "system":
            system_info += msg["content"] + "\n"

    if context:
        history_text = system_info + "\nسياق المحادثة السابقة:\n"

        for msg in context[-10:]:
            if msg["role"] != "system":
                role = "المستخدم" if msg["role"] == "user" else "المساعد"
                history_text += f"{role}: {msg['content']}\n"

        return f"{history_text}\nاستنادًا لما سبق، أجب على: {prompt}\nالإجابة:"

def read_file_content(path):
    ext = os.path.splitext(path)[1].lower()

    try:
        # TXT
        if ext == ".txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

        # DOCX
        elif ext == ".docx":
            doc = docx.Document(path)
            return "\n".join(p.text for p in doc.paragraphs)

        # PDF
        elif ext == ".pdf":
            text = ""
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() or ""
            return text

        else:
            return None

    except Exception as e:
        return None


def upload_file():
    global CURRENT_FILE_CONTENT, CURRENT_FILE_NAME

    file_path = filedialog.askopenfilename(
        title="اختر ملف",
        filetypes=[
            ("All Files", "*.*"),
            ("Text Files", "*.txt"),
            ("Word Files", "*.docx"),
            ("PDF Files", "*.pdf")
        ]
    )

    if not file_path:
        return

    content = read_file_content(file_path)

    if not content:
        messagebox.showerror("خطأ", "لا يمكن قراءة هذا الملف")
        return

    CURRENT_FILE_CONTENT = content
    CURRENT_FILE_NAME = os.path.basename(file_path)

    show_ai(f"📎 تم تحميل الملف: {CURRENT_FILE_NAME}\nاكتب ماذا تريد مني أن أفعل به (مثل: لخصه، اشرحه، استخرج النقاط المهمة).")


def send_message():

    global CURRENT_FILE_CONTENT, CURRENT_FILE_NAME

    msg = entry.get().strip()
    if not msg:
        return

    # عرض رسالة المستخدم
    show_user(msg)
    save_to_file(f"أنت: {msg}")
    entry.delete(0, tk.END)

    # لو فيه ملف مرفوع
    if CURRENT_FILE_CONTENT:

        prompt = f"""
لدي ملف اسمه: {CURRENT_FILE_NAME}

محتواه:

{CURRENT_FILE_CONTENT}

طلب المستخدم:
{msg}

نفذ الطلب بدقة.
"""

        CURRENT_FILE_CONTENT = None
        CURRENT_FILE_NAME = None

        threading.Thread(
            target=get_ai_reply,
            args=(prompt, msg)
        ).start()

        return

    # ابحث في ملفات المعرفة أولاً
    knowledge_prompt = build_knowledge_prompt(msg)

    if knowledge_prompt:

        threading.Thread(
            target=get_ai_reply,
            args=(knowledge_prompt, msg)
        ).start()

    else:

        context_prompt = build_context_prompt(msg)

        threading.Thread(
            target=get_ai_reply,
            args=(context_prompt, msg)
        ).start()


def get_ai_reply(prompt, user_msg=None):

    thinking_mark = show_thinking()
    root.update_idletasks()

    data = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1000}
    }

    try:
        r = requests.post(OLLAMA_URL, json=data, timeout=300)
        answer = r.json()["response"]

        # لو AI مش عارف
        unsure_words = [
            "لا أعرف",
            "لا اعلم",
            "غير متأكد",
            "ليس لدي",
            "لا أملك",
            "عذراً",
            "عذرًا"
        ]

        is_unsure = any(word in answer for word in unsure_words)

        # لو مش عارف → دور في الملفات
        if is_unsure and user_msg:

            local_answer = get_from_files(user_msg)

            if local_answer:
                answer = "📂 من ملفاتي:\n" + local_answer

        root.after(0, hide_thinking_and_show_ai, thinking_mark, answer)

    except Exception as e:
        root.after(0, hide_thinking_and_show_ai,
                   thinking_mark,
                   f"خطأ: {str(e)}")

def clear_memory():
    if messagebox.askyesno("تأكيد", "هل تريد مسح ذاكرة الجلسة الحالية؟"):

        # احتفظ فقط بالـ system (الذاكرة الأساسية)
        chat_memory.conversation_history = [
            msg for msg in chat_memory.conversation_history
            if msg["role"] == "system"
        ]

        chat_memory.save_history()

        chat.config(state="normal")
        chat.delete("1.0", tk.END)
        chat.config(state="disabled")

        show_ai("تم مسح الذاكرة مع الاحتفاظ بالمعلومات الأساسية.")

# نافذة السجل المحدثة
def open_history():
    win = tk.Toplevel(root)
    win.title("سجل المحادثات")
    win.geometry("600x500")
    win.configure(bg=BG_COLOR)

    def refresh_list():
        listbox.delete(0, tk.END)
        if os.path.exists(SAVE_FOLDER):
            for f in sorted(os.listdir(SAVE_FOLDER), reverse=True):
                listbox.insert(tk.END, f)

    def delete_all():
        if messagebox.askyesno("تأكيد حذف الكل", "سيتم حذف جميع المحادثات المسجلة نهائياً. هل أنت متأكد؟"):
            for f in os.listdir(SAVE_FOLDER):
                os.remove(os.path.join(SAVE_FOLDER, f))
            refresh_list()

    def delete_selected():
        sel = listbox.curselection()
        if not sel: return
        if messagebox.askyesno("حذف", "حذف هذه المحادثة؟"):
            os.remove(os.path.join(SAVE_FOLDER, listbox.get(sel[0])))
            refresh_list()

    def open_selected():
        sel = listbox.curselection()
        if not sel: return
        path = os.path.join(SAVE_FOLDER, listbox.get(sel[0]))
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        chat.config(state="normal")
        chat.delete("1.0", tk.END)
        chat.insert(tk.END, content)
        chat.config(state="disabled")
        win.destroy()

    listbox = tk.Listbox(win, bg=CHAT_BG, fg="white", font=("Segoe UI", 11))
    listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    btn_frame = tk.Frame(win, bg=BG_COLOR)
    btn_frame.pack(pady=10)

    tk.Button(btn_frame, text="📂 فتح", bg=BTN_COLOR, fg="white", width=10, command=open_selected).pack(side=tk.LEFT, padx=5)
    tk.Button(btn_frame, text="🗑️ حذف", bg="#991b1b", fg="white", width=10, command=delete_selected).pack(side=tk.LEFT, padx=5)
    tk.Button(btn_frame, text="🔥 مسح الكل", bg="#ef4444", fg="white", width=10, command=delete_all).pack(side=tk.LEFT, padx=5)

    refresh_list()

# الواجهة الرئيسية
root = tk.Tk()
root.title("Ghost AI")
root.geometry("900x650")
root.configure(bg=BG_COLOR)

header = tk.Frame(root, bg=BG_COLOR)
header.pack(fill=tk.X)

tk.Label(header, text="Ghost AI", bg=BG_COLOR, fg="white", font=("Segoe UI", 18, "bold")).pack(side=tk.LEFT, padx=15, pady=10)

ctrls = tk.Frame(header, bg=BG_COLOR)
ctrls.pack(side=tk.RIGHT, padx=15)

tk.Button(ctrls, text="🗑️ مسح الذاكرة", bg="#7f1d1d", fg="white", command=clear_memory).pack(side=tk.RIGHT, padx=5)  #لو عاوز اظهر الزر
tk.Button(ctrls, text="📂 السجل", bg=BTN_COLOR, fg="white", command=open_history).pack(side=tk.RIGHT, padx=5)

chat = scrolledtext.ScrolledText(root, bg=CHAT_BG, fg=TEXT_COLOR, font=("Segoe UI", 12), state="disabled", wrap=tk.WORD)
chat.pack(padx=15, pady=10, fill=tk.BOTH, expand=True)









# copy & paste
# def on_copy(event=None):
#     try:
#         selected_text = chat.get(tk.SEL_FIRST, tk.SEL_LAST)
#         root.clipboard_clear()
#         root.clipboard_append(selected_text)
#     except tk.TclError:
#         pass


def on_copy(event=None):
    chat.event_generate("<<Copy>>")
    return "break"

chat.bind("<Control-c>", on_copy)



# chat.bind("<Control-c>", on_copy)
chat.bind("<Control-v>", lambda e: chat.event_generate("<<Paste>>"))










chat.tag_config(
    "user",
    foreground=USER_COLOR,
    font=("Segoe UI", 12),
    justify="right",
    lmargin1=120,
    lmargin2=120,
    rmargin=10
)

chat.tag_config(
    "ai",
    foreground=AI_COLOR,
    font=("Segoe UI", 12),
    justify="left",
    lmargin1=10,
    lmargin2=10,
    rmargin=120
)

chat.tag_config(
    "user_label",
    foreground="#60a5fa",
    font=("Segoe UI", 10, "bold"),
    justify="right",
    lmargin1=120,
    lmargin2=120,
    rmargin=10
)

chat.tag_config(
    "ai_label",
    foreground="#34d399",
    font=("Segoe UI", 10, "bold"),
    justify="left",
    lmargin1=10,
    lmargin2=10,
    rmargin=120
)


footer = tk.Frame(root, bg=BG_COLOR)
footer.pack(fill=tk.X, padx=10, pady=10)

entry = tk.Entry(footer, font=("Segoe UI", 12), bg=CHAT_BG, fg="white", insertbackground="white")
entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=6)
entry.bind("<Return>", lambda e: send_message())

tk.Button(
    footer,
    text="📎 ملف",
    bg="#334155",
    fg="white",
    font=("Segoe UI", 11, "bold"),
    command=upload_file,
    padx=10
).pack(side=tk.RIGHT, padx=5)

tk.Button(
    footer,
    text="إرسال",
    bg=BTN_COLOR,
    fg="white",
    font=("Segoe UI", 11, "bold"),
    command=send_message,
    padx=15
).pack(side=tk.RIGHT)


show_ai("مرحباً! كيف يمكنني مساعدتك اليوم؟")
root.mainloop()