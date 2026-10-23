"""
check_setup.py - Run from the project root:  python check_setup.py

Reads each project file as plain text (no imports), so it works even when
app.py cannot start. Reports files that are missing, empty, or that do not
contain the code they should.
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

# file -> text fragments that MUST appear inside it
EXPECTED = {
    "app.py": ["def create_app", "csrf_protect", "chatbot_bp"],
    "config.py": ["class Config", "DB_NAME", "CHATBOT_ENABLED", "GEMINI_API_KEY", "GEMINI_MODEL"],
    "database/db_connection.py": ["def db_cursor", "def test_connection"],
    "modules/auth/routes.py": ["auth_bp = Blueprint", "def login", "def logout"],
    "modules/auth/decorators.py": ["def login_required", "def role_required"],
    "modules/patients/services.py": ["def validate_patient_form", "def register_patient", "def issue_token"],
    "modules/patients/routes.py": ["patients_bp = Blueprint", "def register", "def dashboard", "def issue_my_token", "def history"],
    "modules/doctor/routes.py": ["doctor_bp = Blueprint", "def consult", "def prescribe", "def find"],
    "modules/doctor/services.py": ["def create_prescription", "def list_medicines", "def parse_prescription_form"],
    "modules/chatbot/service.py": ["def answer", "SYSTEM_PROMPT", "SELF_HARM_RE", "classify_error"],
    "modules/chatbot/knowledge_base.py": ["class KnowledgeBase", "def retrieve", "def load_knowledge_base"],
    "modules/chatbot/routes.py": ["chatbot_bp = Blueprint", "def message"],
    "modules/chatbot/knowledge/center_kb.json": ['"emergency"', '"token_rules"', '"fa_burn"'],
    "check_chatbot.py": ["def main", "service.ping"],
    "static/js/chatbot.js": ["function parseRich", "X-CSRFToken", "sessionStorage"],
    "static/css/chatbot.css": [".umc-chat__panel", ".umc-chat__bubble--user"],
    "templates/_chatbot_widget.html": ["umcChatPanel", "umcChatForm", "umcChatInput"],
    "modules/patients/history.py": ["def get_patient_history", "def get_prescription_for_token"],
    "modules/pharmacy/routes.py": ["pharmacy_bp = Blueprint", "def dispense", "def stock", "def prescription"],
    "modules/pharmacy/services.py": ["def dispense_prescription", "def get_pending_queue", "def get_stock"],
    "modules/counter/routes.py": ["counter_bp = Blueprint", "def dashboard", "def register", "def token"],
    "templates/base.html": ["block content", "csrf_token", "_chatbot_widget.html", "chatbot.js"],
    "templates/login.html": ["csrf_token", "patients.register"],
    "templates/error.html": ["block content"],
    "templates/_macros.html": ["status_badge"],
    "templates/_patient_fields.html": ["macro field", "confirm_password"],
    "templates/register_student.html": ["_patient_fields.html", "csrf_token"],
    "templates/counter_register.html": ["_patient_fields.html", "csrf_token"],
    "templates/counter_token.html": ["id_verified", "csrf_token"],
    "templates/dashboard_student.html": ["issue_my_token", "Doctor availability", "patients.history"],
    "templates/dashboard_doctor.html": ["Find patient", "doctor.start"],
    "templates/doctor_consult.html": ["rxForm", "add-med", "stock_indicator"],
    "templates/doctor_patient.html": ["_history.html"],
    "templates/_history.html": ["rx.medicines"],
    "templates/dashboard_pharmacy.html": ["Pending prescriptions", "pharmacy.find"],
    "templates/pharmacy_dispense.html": ["pack-check", "dispenseBtn"],
    "templates/pharmacy_stock.html": ["stock_indicator", "summary"],
    "templates/patient_history.html": ["My Medical History", "r.medicines"],
    "templates/dashboard_counter.html": ["Today's tokens", "counter.token"],
    "modules/admin/routes.py": ["admin_bp = Blueprint", "def dashboard", "def medicines", "def users"],
    "modules/admin/services.py": ["def adjust_stock", "def set_user_active", "def create_doctor"],
    "templates/dashboard_admin.html": ["admin.medicines"],
    "templates/admin_users.html": ["csrf_token"],
    "templates/admin_medicines.html": ["csrf_token"],
    "static/css/style.css": ["body"],
}


def main():
    problems = 0
    for rel, fragments in EXPECTED.items():
        path = os.path.join(BASE, *rel.split("/"))
        if not os.path.isfile(path):
            print(f"[MISSING]    {rel}")
            problems += 1
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        if not text.strip():
            print(f"[EMPTY]      {rel}   <- paste the full code into this file")
            problems += 1
            continue
        absent = [x for x in fragments if x not in text]
        if absent:
            print(f"[INCOMPLETE] {rel}   missing: {', '.join(absent)}")
            problems += 1
        else:
            print(f"[ok]         {rel}")

    print()
    if problems:
        print(f"{problems} file(s) need attention (listed above).")
        sys.exit(1)
    print("All files look complete. You can run app.py.")


if __name__ == "__main__":
    main()
