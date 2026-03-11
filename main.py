import os
import re
import json
import tkinter as tk
import requests
import docx
import PyPDF2
import eel
import cv2
import subprocess
import numpy as np
from datetime import datetime
from tkinter import filedialog
from sentence_transformers import SentenceTransformer
# import random
# import shutil
# import webbrowser
# import urllib.parse
# from xml.parsers.expat import model


# المودل المسؤال عن تحويل النصوص إلى متجهات (Embeddings) للبحث في قاعدة المعرفة
model_path = r"M:\VScode\Ghost_AI_Agent\models\all-MiniLM-L6-v2"
# الكود ده هيتأكد لو الفولدر مش موجود أو فاضي، هيحمل الموديل من النت
if not os.path.exists(model_path):
    os.makedirs(model_path, exist_ok=True)
    print("جاري تحميل الموديل لأول مرة... (لازم يكون فيه إنترنت)")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    model.save(model_path)
    print("تم تحميل وحفظ الموديل بنجاح! تقدر تفصل النت دلوقتي.")


# ----------------- إعدادات النظام والمجلدات -----------------
# إعدادات Ollama
OLLAMA_URL = "http://localhost:11434/api/generate"
# MODEL_NAME = "gpt-oss:20b"
# MODEL_NAME = "gpt-oss:120b-cloud"
# MODEL_NAME = "qwen3.5:397b-cloud"
MODEL_NAME = "qwen3:8b-cloud"

# المتغيرات العامة
KNOWLEDGE_FOLDER = "knowledge"
SAVE_FOLDER = "chats"
HISTORY_FILE = "chat_history.json"
# متغيرات للملف المرفوع مؤقتاً
CURRENT_FILE_CONTENT = None
CURRENT_FILE_NAME = None
SESSION_FILE = None
# وضع الإجابة من المعرفة فقط
KNOWLEDGE_ONLY_MODE = False
embedding_model = SentenceTransformer(model_path, local_files_only=True)

MAX_TITLE_LENGTH = 50  # الحد الأقصى لطول اسم الملف

def generate_chat_title(text):
    """استخراج أول 4 كلمات من رسالة المستخدم ليكون اسم المحادثة"""
    # أخذ أول 4 كلمات فقط
    words = text.split()[:4]
    title = " ".join(words)
    
    # تنظيف النص من أي رموز تمنع الويندوز من إنشاء الملف (مثل / \ : * ? " < > |)
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
    
    # تقليل الطول إذا كان كبير جداً
    if len(safe_title) > MAX_TITLE_LENGTH:
        safe_title = safe_title[:MAX_TITLE_LENGTH].rstrip()
    
    return safe_title if safe_title else "محادثة_بدون_عنوان"

def create_new_session(first_message):
    """إنشاء ملف الجلسة بناءً على محتوى أول رسالة"""
    global SESSION_FILE
    
    title = generate_chat_title(first_message)
    
    # إضافة وقت قصير جداً في النهاية لتجنب تداخل الملفات إذا بدأت محادثتين بنفس الكلمة
    short_time = datetime.now().strftime('%H%M%S')
    filename = f"{title}_{short_time}.txt"
    
    SESSION_FILE = os.path.join(SAVE_FOLDER, filename)
    
    # إنشاء الملف وكتابة الترويسة
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== موضوع المحادثة: {title} ===\n")
        f.write(f"تاريخ الإنشاء: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("-" * 40 + "\n")
for folder in [KNOWLEDGE_FOLDER, SAVE_FOLDER]:
    os.makedirs(folder, exist_ok=True)


# ----------------- دوال المعالجة والتنظيف -----------------
def clean_markdown(text):
    """تنظيف النصوص من علامات المارك داون لتبدو واضحة في الواجهة"""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"#+\s*", "", text)
    # text = re.sub(r"\|", " | ", text)
    text = re.sub(r"-{3,}", "", text)
    return text.strip()

def read_file_content(path):
    """قراءة محتوى الملفات باختلاف أنواعها"""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f: return f.read()
        elif ext == ".docx":
            doc = docx.Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
        elif ext == ".pdf":
            text = ""
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages: text += page.extract_text() or ""
            return text
    except Exception as e:
        print(f"Error reading file: {e}")
        return None


# ----------------- نظام المعرفة المحلي (RAG مبسط) ----------------
os.makedirs(KNOWLEDGE_FOLDER, exist_ok=True)
knowledge_index = []

def build_knowledge_index():
    
    global knowledge_index
    knowledge_index = []

    for file in os.listdir(KNOWLEDGE_FOLDER):

        if not file.endswith(".json"):
            continue

        path = os.path.join(KNOWLEDGE_FOLDER, file)

        try:
            with open(path,"r",encoding="utf-8") as f:

                data = json.load(f)

                for item in data:

                    text = f"{item.get('question','')} {item.get('answer','')}"

                    vector = embedding_model.encode(text)

                    knowledge_index.append({
                        "text": text,
                        "question": item.get("question"),
                        "answer": item.get("answer"),
                        "image": item.get("image"),
                        "link": item.get("link"),
                        "vector": vector,
                        "source": file
                    })

        except Exception as e:
            print("RAG error:",e)

# بحث بسيط في قاعدة المعرفة باستخدام التشابه الكوني (Cosine Similarity)
def search_knowledge(query, limit=100):

    if not knowledge_index:
        return ""

    query_vector = embedding_model.encode(query)

    results = []

    for item in knowledge_index:

        score = np.dot(query_vector, item["vector"]) / (
            np.linalg.norm(query_vector) * np.linalg.norm(item["vector"])
        )

        if score > 0.3:
            results.append((score, item))

    results.sort(reverse=True, key=lambda x: x[0])

    context = "معلومات من قاعدة المعرفة:\n"

    for score, item in results[:limit]:

        context += f"\nالسؤال: {item['question']}\n"
        context += f"المعلومة: {item['answer']}\n"

        if item.get("image"):
            context += f"[IMG:{item['image']}]\n"

        if item.get("link"):
            context += f"[LINK:{item['link']}]\n"

    return context

build_knowledge_index()


# ----------------- إدارة الذاكرة -----------------
class ChatMemory:
    def __init__(self):
        self.conversation_history = []
        self.load_history()
        if not self.conversation_history:
            self.conversation_history = [{"role": "system", "content": "اسم المستخدم محمد , طالب في كلية الهندسة قسم عمارة جامعة الدلتا من مصر. اسم المساعد جوست. أجب باللغة العربية دائماً."}]

    def add_message(self, role, content):
        self.conversation_history.append({"role": role, "content": content})
        if len(self.conversation_history) > 1: # حفظ آخر 1 رسالة فقط للسياق
            self.conversation_history = [self.conversation_history[0]] + self.conversation_history[-19:]
        self.save_history()
        
    def get_context(self): return self.conversation_history

    def clear(self):
        self.conversation_history = [self.conversation_history[0]]
        self.save_history()
        
    def save_history(self):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.conversation_history, f, ensure_ascii=False, indent=2)
        
    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                self.conversation_history = json.load(f)
chat_memory = ChatMemory()

def call_ollama(prompt):
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=300)
    result = response.json()

    return result.get("response", "عذراً، لم أستطع توليد رد.")



# ----------------- نظام الكاميرا الذكية ----------------
class SmartCamera:


    IMAGE_FOLDER = os.path.join("Gui", "images")  # المجلد الثابت لحفظ الصور
    os.makedirs(IMAGE_FOLDER, exist_ok=True)      # لو المجلد مش موجود، اعمله
    
    def take_photo(self):
        cap = cv2.VideoCapture(0)

        # قائمة دقات شائعة من الأعلى إلى الأقل
        resolutions = [
            (3840, 2160),  # 4K
            (2560, 1440),  # 2K
            (1920, 1080),  # Full HD
            (1280, 720),   # HD
            (640, 480)     # SD
        ]

        ret, frame = False, None
        for width, height in resolutions:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            print(f"محاولة الدقة: {width}x{height}")
            ret, frame = cap.read()
            if ret:
                actual_height, actual_width = frame.shape[:2]
                if actual_width == width and actual_height == height:
                    print(f"تم استخدام الدقة: {width}x{height}")
                    break

        if not ret:
            cap.release()
            return "فشل فتح الكاميرا"

        # حفظ الصورة في المجلد الثابت
        filename = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        full_path = os.path.join(self.IMAGE_FOLDER, filename)
        cv2.imwrite(full_path, frame)
        cap.release()

        # نرجع بس اسم الصورة، JS هيتعامل مع المسار
        return filename

def parse_camera_command(text):
    text = text.lower()
    if any(word in text for word in ["صورني", "التقط صورة", "take photo"]):
        return "photo"
    return None

cam = SmartCamera()

# ----------------- نظام فتح التطبيقات ----------------
class ToolExecutor:
    def __init__(self):
        # قاموس التطبيقات المحلية 
        self.local_apps = {
            "notepad": ["النوتة", "النوته", "نوتة", "المفكرة", "مفكرة", "notepad"],
            "calc": ["الحاسبة", "حاسبة", "الالة الحاسبة", "calculator", "calc"],
            "mspaint": ["الرسام", "رسام", "paint", "mspaint"],
            "cmd": ["الدوس", "الشاشة السوداء", "cmd", "terminal", "موجه الاوامر"],
            "chrome": ["كروم", "المتصفح", "chrome", "google chrome"],
            r"C:\Program Files (x86)\Steam\steam.exe": ["ستيم", "steam", "العاب", "ألعاب"],
            r"C:\Program Files\Autodesk\Revit 2020\Revit.exe": ["ريفيت", "revit", "الريفت"],
            r"M:\Photoshop\App\Adobe Photoshop 2021\Photoshop.exe": ["فوتوشوب", "photoshop", "الفوتوشوب"],
        }

    def execute_open_app(self, target):
        target_lower = target.lower()
        
        # البحث في التطبيقات المحلية فقط
        for cmd, synonyms in self.local_apps.items():
            if any(syn in target_lower for syn in synonyms):
                try:
                    subprocess.Popen(cmd, shell=True)
                    return f"💻 تم تشغيل تطبيق: {target}"
                except:
                    return f"❌ فشل تشغيل التطبيق {target}"
                    
        # إذا لم يجد التطبيق في القاموس
        return f"❌ لم أتمكن من العثور على تطبيق مسجل باسم '{target}'."

executor = ToolExecutor()


# ----------------- دوال Eel (الربط مع HTML) -----------------
eel.init('Gui')



@eel.expose
def chat_with_ai(user_msg):

    global CURRENT_FILE_CONTENT, CURRENT_FILE_NAME
    global SESSION_FILE, KNOWLEDGE_ONLY_MODE

    user_msg = user_msg.strip()

    if not user_msg:
        return "الرسالة فارغة."

    if SESSION_FILE is None:
        create_new_session(user_msg)
    # حفظ رسالة المستخدم
    chat_memory.add_message("user", user_msg)

    # ---------------- System Instruction ----------------

    system_instruction = """
أنت 'جوست' (Ghost)، مساعد شخصي ذكي متصل بنظام كمبيوتر.
لديك القدرة على اتخاذ قرارات ذكية واستخدام أدوات النظام عند الحاجة.


القواعد:

[الأدوات المتاحة وطريقة استخدامها]
إذا كان طلب المستخدم يتطلب استخدام أداة، **يجب** أن ترد بكود JSON فقط بالصيغة التالية (بدون أي نص قبله أو بعده):
1. لفتح برنامج أو تطبيق محلي: {"action": "open_app", "target": "اسم البرنامج"}
2. لالتقاط صورة بالكاميرا: {"action": "take_photo"}

[القواعد الأساسية]
إذا طلب المستخدم تعديل كود أو إنشاء كود، أرسل الكود كاملًا مباشرة بدون JSON أو أي تعليمات أخرى.
- إذا كان الطلب يتطلب أداة -> أرسل JSON فقط.
- إذا كان الطلب سؤالاً عادياً، أو دردشة، أو سؤال عن ملف مرفق -> أجب كنص عربي طبيعي، احترافي ومفيد.
- لا يمكنك تصفح الإنترنت أو البحث فيه. أنت تتحكم في برامج الكمبيوتر والملفات المرفقة فقط.

[قاعدة الميديا]
- إذا وجدت معلومة في السياق مرتبطة بصورة [IMG:...] أو رابط [LINK:...] وهي تدعم إجابتك، يجب أن تضع التاج كما هو في نهاية ردك.
- لا تحاول وصف الصورة، فقط ضع التاج.
- إذا لم تجد صورة متعلقة مباشرة، لا تضع أي تاجات.

- اذا طلب المستخدم صورة عن موضوع معين ابحث في قاعدة المعرفة عن أقرب معلومة لها، وإذا وجدت صورة مرتبطة بها استخدمها في إجابتك مع التاج [IMG:...].
- اذا طلب المستخدم عرض جميع الصور عن موضوع معين، ابحث في قاعدة المعرفة عن كل المعلومات المتعلقة بالموضوع، وجمع كل الصور المرتبطة بها في إجابتك مع تاج [IMG:...] لكل صورة.
"""
    # ---------------- بناء السياق ----------------

    context_block = ""

    # -------- ملف مرفوع --------

    if CURRENT_FILE_CONTENT:

        context_block += f"""
محتوى الملف ({CURRENT_FILE_NAME}):

{CURRENT_FILE_CONTENT[:9000]}
"""

    # -------- البحث في المعرفة --------

    json_data = search_knowledge(user_msg)
    if json_data.strip():
        context_block += f"\n[قاعدة بيانات المعرفة]:\n{json_data}\n"

    # -------- تاريخ المحادثة --------

    # -------- سياق الرسائل السابقة --------
    context = chat_memory.get_context()
    history_text = "\n".join([f"{m['role']}: {m['content']}" for m in context[-8:]])

    # ---------------- بناء البرومبت ----------------

    prompt = f"""
{system_instruction}

{context_block}

تاريخ المحادثة:

{history_text}

طلب المستخدم:
{user_msg}

رد المساعد:
"""

    # ---------------- طباعة البرومبت ----------------

    print("==== Prompt المرسل للـ AI ====")
    print(prompt)
    print("================================")

    # ---------------- استدعاء AI ----------------
    

# ---------------- استدعاء AI ----------------
    try:
        raw_answer = call_ollama(prompt)
        
        # متغيرات افتراضية للرد
        final_text = raw_answer
        image_name = None
        link_url = None

        # 1. فحص إذا كان الرد يحتوي على JSON (أوامر تشغيل أدوات)
        if "{" in raw_answer and "}" in raw_answer:
            try:
                start = raw_answer.find("{")
                end = raw_answer.rfind("}") + 1
                decision = json.loads(raw_answer[start:end])

                action = decision.get("action")
                target = decision.get("target", "")

                if action == "open_app":
                    final_text = executor.execute_open_app(target)
                elif action == "take_photo":
                    photo_file = cam.take_photo()
                    final_text = f"📷 تم التقاط الصورة: {photo_file}"
                    image_name = photo_file # عشان تظهر في الشات فوراً لو حبيت
            
            except Exception as json_error:
                print(f"JSON Parsing Error: {json_error}")
                final_text = raw_answer # ارجع للنص الأصلي لو فشل التحليل

        else:
            # 2. إذا كان رد طبيعي (RAG)، استخرج الصور والروابط ونظف النص
            image_match = re.search(r"\[IMG:(.*?)\]", raw_answer)
            link_match = re.search(r"\[LINK:(.*?)\]", raw_answer)
            
            # تنظيف اسم الصورة من أي مسارات فرعية قديمة (مثل assets/) 
            # لضمان توافقها مع فولدر Gui/images
            if image_match:
                image_name = os.path.basename(image_match.group(1))
            else:
                image_name = None
                
            link_url = link_match.group(1) if link_match else None
            
            # تنظيف النص من التاجات تماماً ليرسل للواجهة نظيفاً
            final_text = re.sub(r"\[IMG:.*?\]", "", raw_answer)
            final_text = re.sub(r"\[LINK:.*?\]", "", final_text).strip()

        # ---------------- حفظ الرد وإدارة الجلسة ----------------
        
        # حفظ في الذاكرة (Memory)
        chat_memory.add_message("assistant", final_text)

        # حفظ في ملف الجلسة (Session File)
        if SESSION_FILE:
            try:
                with open(SESSION_FILE, "a", encoding="utf-8") as f:
                    f.write(f"المستخدم: {user_msg}\n")
                    f.write(f"جوست: {final_text}\n")
                    if image_name: f.write(f"[صورة: {image_name}]\n")
                    f.write("-" * 40 + "\n")
            except Exception as file_err:
                print(f"Session Save Error: {file_err}")

        # تصفير الملفات المرفوعة بعد الإجابة عليها
        CURRENT_FILE_CONTENT = None
        CURRENT_FILE_NAME = None

        # ---------------- العودة للواجهة ----------------
        return {
            "status": "success",
            "text": final_text,
            "image": image_name,
            "link": link_url
        }

    except Exception as e:
        print(f"General Error in chat_with_ai: {e}")
        return {
            "status": "error", 
            "message": f"⚠️ حدث خطأ: {str(e)}"
            }
@eel.expose
def trigger_file_dialog():
    global CURRENT_FILE_CONTENT, CURRENT_FILE_NAME
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askopenfilename(filetypes=[("Documents", "*.txt *.pdf *.docx")])
    root.destroy()
    
    if path:
        content = read_file_content(path)
        if content:
            CURRENT_FILE_CONTENT = content
            CURRENT_FILE_NAME = os.path.basename(path)
            return {"status": "success", "message": f"📎 تم تحميل {CURRENT_FILE_NAME}. اسألني أي شيء عنه!"}
    return {"status": "error", "message": "فشل تحميل الملف."}

@eel.expose
def clear_memory_py():
    chat_memory.clear()
    # delete_all_chats()
    return "تم مسح الذاكرة المؤقتة."

# --- دوال إدارة السجل ---
@eel.expose
def get_chat_history_list():
    """جلب قائمة الملفات من مجلد chats لعرضها في السجل"""
    if not os.path.exists(SAVE_FOLDER): 
        return []
    
    # التعديل هنا: سحب أي ملف .txt بدلاً من التي تبدأ بـ chat_ فقط
    files = [f for f in os.listdir(SAVE_FOLDER) if f.endswith(".txt")]
    
    # ترتيب الملفات حسب وقت التعديل (الأحدث يظهر في الأعلى)
    files.sort(key=lambda x: os.path.getmtime(os.path.join(SAVE_FOLDER, x)), reverse=True)
    return files

@eel.expose
def load_specific_chat(filename):
    """قراءة ذكية للمحادثة تدعم الرسائل متعددة الأسطر"""
    try:
        path = os.path.join(SAVE_FOLDER, filename)
        if not os.path.exists(path):
            return []

        messages = []
        current_role = None
        current_content = []

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                raw_line = line.strip()
                
                # التحقق مما إذا كان السطر يبدأ برسالة مستخدم
                if "المستخدم:" in line:
                    # حفظ الرسالة السابقة قبل الانتقال للجديدة
                    if current_role:
                        messages.append({"role": current_role, "content": "\n".join(current_content).strip()})
                    
                    current_role = "user"
                    current_content = [line.split("المستخدم:", 1)[1].strip()]
                
                # التحقق مما إذا كان السطر يبدأ برد الجوست
                elif "جوست:" in line:
                    if current_role:
                        messages.append({"role": current_role, "content": "\n".join(current_content).strip()})
                    
                    current_role = "assistant"
                    current_content = [line.split("جوست:", 1)[1].strip()]
                
                # إذا كان السطر تكملة لرسالة سابقة (أسطر إضافية)
                elif current_role and raw_line and not raw_line.startswith("---") and not raw_line.startswith("==="):
                    current_content.append(raw_line)

            # إضافة آخر رسالة في الملف
            if current_role and current_content:
                messages.append({"role": current_role, "content": "\n".join(current_content).strip()})

        return messages
    except Exception as e:
        print(f"Error loading chat: {e}")
        return []
@eel.expose
def delete_chat_file(filename):
    """حذف ملف سجل واحد"""
    try:
        os.remove(os.path.join(SAVE_FOLDER, filename))
        return True
    except: return False

@eel.expose
def delete_all_chats():
    """حذف كافة السجلات في مجلد chats"""
    try:
        for f in os.listdir(SAVE_FOLDER):
            os.remove(os.path.join(SAVE_FOLDER, f))
        return True
    except: return False

@eel.expose
def start_new_chat():
    global chat_memory, SESSION_FILE

    if len(chat_memory.get_context()) <= 1:
        return "لا توجد محادثات حالية لتسجيلها."

    # مسح الذاكرة
    chat_memory.clear()

    # نجعل ملف الجلسة None لكي يتم إنشاؤه وتسميته مع أول رسالة قادمة
    SESSION_FILE = None

    return "تم بدء محادثة جديدة."  
# ----------------- تشغيل البرنامج -----------------
if __name__ == '__main__':
    print("Ghost AI يعمل الآن...")
    eel.start('index.html', size=(950, 750))
