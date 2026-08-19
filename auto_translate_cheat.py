import os
import re
import json

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_DICT_PATH = os.path.join(ROOT_DIR, "custom_dict.json")
MISS_LOG_PATH = os.path.join(ROOT_DIR, "translate_miss.log")
SEPARATOR = "｜"

custom_dict_lower = {}
if os.path.exists(CUSTOM_DICT_PATH):
    with open(CUSTOM_DICT_PATH, "r", encoding="utf-8") as f:
        raw_dict = json.load(f)
    for orig_text, trans_text in raw_dict.items():
        custom_dict_lower[orig_text.lower()] = trans_text

miss_set = set()

def offline_translate(text: str) -> str:
    raw = text.strip()
    if not raw:
        return raw
    raw_low = raw.lower()
    if raw_low in custom_dict_lower:
        return f"{raw}{SEPARATOR}{custom_dict_lower[raw_low]}"
    miss_set.add(raw)
    return raw

pattern_shn = re.compile(r'(Cheat Text=")(.*?)(")', re.MULTILINE | re.DOTALL)

def process_shn_file(filepath):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    def replace_func(match):
        prefix = match.group(1)
        origin_txt = match.group(2)
        suffix = match.group(3)
        return prefix + offline_translate(origin_txt) + suffix
    new_content = pattern_shn.sub(replace_func, content)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

def walk_json_node(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "name" and isinstance(v, str):
                obj[k] = offline_translate(v)
            else:
                walk_json_node(v)
    elif isinstance(obj, list):
        for item in obj:
            walk_json_node(item)

def process_json_file(filepath):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)
    walk_json_node(data)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def scan_all_files(root_path):
    for dirpath, _, filenames in os.walk(root_path):
        for fname in filenames:
            fullpath = os.path.join(dirpath, fname)
            fname_low = fname.lower()
            if fname_low.endswith(".shn"):
                print(f"Processing SHN: {fullpath}")
                process_shn_file(fullpath)
            elif fname_low.endswith(".json"):
                print(f"Processing JSON: {fullpath}")
                process_json_file(fullpath)

def write_miss_log():
    with open(MISS_LOG_PATH, "w", encoding="utf-8") as fp:
        for entry in sorted(miss_set):
            fp.write(f"{entry}\n")
    print(f"Miss log saved, total untranslated items: {len(miss_set)}")

if __name__ == "__main__":
    scan_all_files(ROOT_DIR)
    write_miss_log()
    print("✅ Translation work complete")
