import os
import re
import json
from pyglossary import Glossary

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DICT_FOLDER = os.path.join(ROOT_DIR, "dict")
DICT_IFO = os.path.join(DICT_FOLDER, "stardict‑ec‑2.4.2/stardict‑ec‑2.4.2.ifo")
CUSTOM_DICT_PATH = os.path.join(ROOT_DIR, "custom_dict.json")
SEPARATOR = "｜"

custom_dict = {}
if os.path.exists(CUSTOM_DICT_PATH):
    with open(CUSTOM_DICT_PATH, "r", encoding="utf‑8") as f:
        custom_dict = json.load(f)

stardict_cache = {}
if os.path.exists(DICT_IFO):
    glos = Glossary()
    glos.read(DICT_IFO, format="Stardict")
    for entry in glos:
        word = entry.word.strip().lower()
        defi = entry.defi.strip()
        stardict_cache[word] = defi

def offline_translate(text: str) -> str:
    raw = text.strip()
    if not raw:
        return raw
    if raw in custom_dict:
        return f"{raw}{SEPARATOR}{custom_dict[raw]}"
    low_text = raw.lower()
    if low_text in stardict_cache:
        return f"{raw}{SEPARATOR}{stardict_cache[low_text]}"
    return raw

pattern_shn = re.compile(r'(Cheat Text=")(.*?)(")', re.MULTILINE | re.DOTALL)

def process_shn(filepath):
    with open(filepath, "r", encoding="utf‑8", errors="ignore") as f:
        content = f.read()
    def replace_cb(match):
        pre = match.group(1)
        txt = match.group(2)
        suf = match.group(3)
        return pre + offline_translate(txt) + suf
    new_content = pattern_shn.sub(replace_cb, content)
    with open(filepath, "w", encoding="utf‑8") as f:
        f.write(new_content)

def walk_json(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "name" and isinstance(v, str):
                obj[k] = offline_translate(v)
            else:
                walk_json(v)
    elif isinstance(obj, list):
        for item in obj:
            walk_json(item)

def process_json(filepath):
    with open(filepath, "r", encoding="utf‑8", errors="ignore") as f:
        data = json.load(f)
    walk_json(data)
    with open(filepath, "w", encoding="utf‑8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def scan_all(root):
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            fl = fname.lower()
            if fl.endswith(".shn"):
                print(f"Processing SHN: {full_path}")
                process_shn(full_path)
            elif fl.endswith(".json"):
                print(f"Processing JSON: {full_path}")
                process_json(full_path)

if __name__ == "__main__":
    scan_all(ROOT_DIR)
    print("✅ Translation finished")
