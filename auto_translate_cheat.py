import os
import json
import re

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

# 捕获整行 Cheat Text="内容"，允许前面空格/tab
PAT_CHEAT_TEXT = re.compile(r'Cheat Text="(.*?)"', re.IGNORECASE)


def translate_text(text: str):
    """翻译函数：优先完全匹配，再子串替换，支持局部翻译"""
    if not text:
        return text
    src_strip = text.strip()
    # 1.完整完全匹配优先
    if src_strip in translate_dict:
        return translate_dict[src_strip]
    result = text
    # 2.子串循环替换，做局部翻译
    for eng, chn in translate_dict.items():
        if eng in result:
            result = result.replace(eng, chn)
    return result


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


def process_shn_file(filepath):
    """处理shn，兼容行前空格、tab；完整匹配+局部子串替换"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[SKIP BAD SHN READ] {filepath} | {e}")
        return

    changed = False
    out_lines = []
    for line in lines:
        match = PAT_CHEAT_TEXT.search(line)
        if match:
            raw_inner = match.group(1)
            # 执行翻译（完整匹配+局部子串替换）
            translated_inner = translate_text(raw_inner)
            # 收集未命中文本到miss日志
            strip_raw = raw_inner.strip()
            if strip_raw and strip_raw not in translate_dict.values():
                miss_set.add(strip_raw)

            if raw_inner != translated_inner:
                # 发生翻译：格式 Cheat Text="原文｜译文"
                new_text_in_quotes = f"{raw_inner}｜{translated_inner}"
                # 替换引号内内容，保留行前面的空格/Tab等原始格式
                new_line = line[:match.start(1)] + new_text_in_quotes + line[match.end(1):]
                out_lines.append(new_line)
                changed = True
            else:
                # 完全没有翻译改动，原样保留该行
                out_lines.append(line)
        else:
            out_lines.append(line)

    if changed:
        try:
            with open(filepath, "w", encoding="utf-8") as fw:
                fw.writelines(out_lines)
            print(f"[SHN MODIFIED] {filepath}")
        except Exception as e:
            print(f"[SHN WRITE ERROR] {filepath} | {e}")


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
                    process_shn_file(fullpath)
            except Exception as e:
                print(f"[SCAN FILE SKIP] {fullpath} | {e}")


def main():
    ROOT_DIR = os.getcwd()
    try:
        scan_all_files(ROOT_DIR)
    except Exception as e:
        print(f"[SCAN FATAL ERROR] {e}")
    # 输出miss日志
    try:
        with open(miss_log_path, "w", encoding="utf-8") as f:
            for word in sorted(miss_set):
                f.write(word + "\n")
        print(f"\nMiss words saved to {miss_log_path}, total miss:{len(miss_set)}")
    except Exception as e:
        print(f"[WRITE LOG ERROR] {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as top_err:
        print(f"[TOP LEVEL CRASH] {top_err}")
        import sys
        sys.exit(0)
