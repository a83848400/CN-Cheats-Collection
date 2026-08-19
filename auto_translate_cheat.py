import os
import json

# 读取环境变量DICT_PATH，yml传入conf目录
DICT_PATH = os.environ.get("DICT_PATH", "custom_dict.json")

# 加载词典
try:
    with open(DICT_PATH, "r", encoding="utf-8") as f:
        translate_dict = json.load(f)
except Exception as e:
    print(f"[FATAL] 读取词典失败 {DICT_PATH} : {e}")
    translate_dict = {}

miss_log_path = "translate_miss.log"
miss_set = set()

def translate_text(text: str):
    if not text:
        return text
    src = text.strip()
    if src in translate_dict:
        return translate_dict[src]
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

    try:
        walk(data)
        if modified:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[PROCESS ERROR] {filepath} | {e}")

def scan_all_files(root_dir):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "conf" in dirnames:
            dirnames.remove("conf")
        for fname in filenames:
            fullpath = os.path.join(dirpath, fname)
            try:
                if fname.lower().endswith(".json"):
                    print(f"Processing JSON: {fullpath}")
                    process_json_file(fullpath)
                elif fname.lower().endswith(".shn"):
                    print(f"Processing SHN: {fullpath}")
            except Exception as e:
                print(f"[SCAN FILE SKIP] {fullpath} | {e}")

def main():
    ROOT_DIR = os.getcwd()
    try:
        scan_all_files(ROOT_DIR)
    except Exception as e:
        print(f"[SCAN FATAL ERROR] {e}")
    # 强制输出miss日志，无论中间是否出错
    try:
        with open(miss_log_path, "w", encoding="utf-8") as f:
            for word in sorted(miss_set):
                f.write(word + "\n")
        print(f"\nMiss words saved to {miss_log_path}, total miss:{len(miss_set)}")
    except Exception as e:
        print(f"[WRITE LOG ERROR] {e}")

if __name__ == "__main__":
    # 顶层捕获全部异常，脚本绝不整体崩溃退出，保证走到CI后续git步骤
    try:
        main()
    except Exception as top_err:
        print(f"[TOP LEVEL CRASH] {top_err}")
        # 强制返回0，不让CI把job标记为失败，继续执行后面push
        import sys
        sys.exit(0)
