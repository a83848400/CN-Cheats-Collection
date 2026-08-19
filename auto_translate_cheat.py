import os
import json

# 读取词典环境变量，yml传入 DICT_PATH
DICT_PATH = os.environ.get("DICT_PATH", "custom_dict.json")

# 加载翻译词典
with open(DICT_PATH, "r", encoding="utf-8") as f:
    translate_dict = json.load(f)

miss_log_path = "translate_miss.log"
miss_set = set()


def translate_text(text: str):
    if not text:
        return text
    src = text.strip()
    if src in translate_dict:
        return translate_dict[src]
    # 子串替换
    for eng, chn in translate_dict.items():
        if eng in text:
            text = text.replace(eng, chn)
    return text


def process_json_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[SKIP BAD JSON] {filepath} | error: {e}")
        return

    modified = False

    def walk(obj):
        nonlocal modified
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    original = v
                    newv = translate_text(v)
                    if newv != original:
                        obj[k] = newv
                        modified = True
                    else:
                        val_strip = v.strip()
                        if val_strip and val_strip not in translate_dict.values():
                            miss_set.add(val_strip)
                elif isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)

    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def scan_all_files(root_dir):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # 排除conf目录，不会读取词典json
        if "conf" in dirnames:
            dirnames.remove("conf")

        for fname in filenames:
            fullpath = os.path.join(dirpath, fname)
            if fname.lower().endswith(".json"):
                print(f"Processing JSON: {fullpath}")
                try:
                    process_json_file(fullpath)
                except Exception as e:
                    print(f"[FILE EXCEPTION] {fullpath} : {str(e)}")
            elif fname.lower().endswith(".shn"):
                print(f"Processing SHN: {fullpath}")


def main():
    ROOT_DIR = os.getcwd()
    scan_all_files(ROOT_DIR)

    # 输出未匹配词条
    with open(miss_log_path, "w", encoding="utf-8") as f:
        for word in sorted(miss_set):
            f.write(word + "\n")
    print(f"\nMiss words saved -> {miss_log_path}, total miss:{len(miss_set)}")


if __name__ == "__main__":
    main()
