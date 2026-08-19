import os
import re
import json
from pyglossary import Glossary

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DICT_FOLDER = os.path.join(ROOT_DIR, "dict")
DICT_IFO = os.path.join(DICT_FOLDER, "stardict‑ec‑2.4.2/stardict‑ec‑2.4.2.ifo")
CUSTOM_DICT_PATH = os.path.join(ROOT_DIR, "custom_dict.json")
MISS_LOG_PATH = os.path.join(ROOT_DIR, "translate_miss.log")
SEPARATOR = "｜"

# 加载自定义词典，构建小写key用于忽略大小写匹配
custom_dict_raw = {}
custom_dict_lower = {}
if os.path.exists(CUSTOM_DICT_PATH):
    with open(CUSTOM_DICT_PATH, "r", encoding="utf-8") as f:
        custom_dict_raw = json.load(f)
    # 构建小写映射: key(小写) -> 译文
    for orig, trans in custom_dict_raw.items():
        custom_dict_lower[orig.lower()] = trans

# 加载Stardict离线词典
stardict_cache = {}
if os.path.exists(DICT_IFO):
    glos = Glossary()
    glos.read(DICT_IFO, format="Stardict")
    for entry in glos:
        word = entry.word.strip().lower()
        defi = entry.defi.strip()
        stardict_cache[word] = defi

miss_set = set()

def offline_translate(text: str) -> str:
    raw = text.strip()
    if not raw:
        return raw

    raw_low = raw.lower()
    # 1.优先自定义词典（忽略大小写）
    if raw_low in custom_dict_lower:
        return f"{raw}{SEPARATOR}{custom_dict_lower[raw_low]}"
    # 2.离线stardict词典
    if raw_low in stardict_cache:
        return f"{raw}{SEPARATOR}{stardict_cache[raw_low]}"
    # 3.全部未命中，记入日志，返回原文
    miss_set.add(raw)
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

def write_miss_log():
    """输出未命中词条日志，方便补充custom_dict.json"""
    with open(MISS_LOG_PATH, "w", encoding="utf‑8") as f:
        for item in sorted(miss_set):
            f.write(f"{item}\n")
    print(f"✅ Miss log wrote: {MISS_LOG_PATH}, total miss: {len(miss_set)}")

if __name__ == "__main__":
    scan_all(ROOT_DIR)
    write_miss_log()
    print("✅ Translation finished")
