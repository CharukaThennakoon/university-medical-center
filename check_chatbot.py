"""
check_chatbot.py - Run from the project root:  python check_chatbot.py

Checks the AI assistant setup step by step and tells you what to fix:
  1. configuration (.env)      2. google-genai installed
  3. knowledge base            4. one tiny live call to Gemini
"""
import sys

from config import Config
from modules.chatbot import service
from modules.chatbot.knowledge_base import get_kb


def line(ok, text):
    print(("[ok]   " if ok else "[FIX]  ") + text)
    return ok


def main():
    good = True
    print(f"Model: {Config.GEMINI_MODEL}\n")

    good &= line(bool(Config.GEMINI_API_KEY),
                 "GEMINI_API_KEY is set" if Config.GEMINI_API_KEY else
                 "GEMINI_API_KEY is empty -> create a free key at https://aistudio.google.com/apikey "
                 "and add GEMINI_API_KEY=... to .env")

    try:
        import google.genai  # noqa: F401
        line(True, "google-genai is installed")
    except ImportError:
        good &= line(False, "google-genai is missing -> run: pip install -U google-genai")

    kb = get_kb()
    good &= line(len(kb.entries) > 0, f"knowledge base loaded ({len(kb.entries)} entries)")
    missing = kb.unfilled_placeholders()
    if missing:
        print(f"[todo] {len(missing)} detail(s) in modules/chatbot/knowledge/center_kb.json "
              f"still say <<FILL IN ...>>:")
        for entry_id, text in missing:
            print(f"         - {entry_id}: {text}")
    else:
        line(True, "no <<FILL IN>> placeholders left")

    print("\nRetrieval test:")
    for q in ("What are your opening hours?", "How do I get a token?", "first aid for a burn"):
        titles = ", ".join(e.title for e in kb.retrieve(q))
        print(f"   {q!r} -> {titles}")

    print("\nLive test (one tiny request to Gemini)...")
    ok, detail = service.ping()
    good &= line(ok, detail)

    print("\nAll good - start the app with: python app.py" if good
          else "\nFix the [FIX] items above, then run this check again.")
    sys.exit(0 if good else 1)


if __name__ == "__main__":
    main()
