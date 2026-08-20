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

# 构建大小写不敏感正则模式，长关键词优先，避免短key优先抢占匹配
def build_case_insensitive_pattern(d):
    keys = sorted(d.keys(), key=len, reverse=True)
    escaped_keys = [re.escape(k) for k in keys]
    pattern = re.compile("|".join(escaped_keys), flags=re.IGNORECASE)
    return pattern

# 全局预编译正则
re_pattern = build_case_insensitive_pattern(translate_dict)

def translate_text(text: str):
    """
    翻译函数：
    1. 优先去除首尾空格后，大小写不敏感完整匹配
    2. 完整匹配失败，则执行大小写不敏感局部子串替换，支持片段局部翻译
    3. 完全匹配 > 局部片段替换；无法翻译返回原文本
    """
    if not text:
        return text
    src_strip = text.strip()

    # ----------第一步：大小写不敏感完整匹配优先----------
    match_full = None
    for eng_key, chn_val in translate_dict.items():
        if eng_key.lower() == src_strip.lower():
            match_full = chn_val
            break
    if match_full is not None:
        return match_full

    # ----------第二步：局部子串大小写不敏感替换（局部片段翻译）----------
    def sub_callback(match_obj):
        hit_raw = match_obj.group(0)
        hit_lower = hit_raw.lower()
        for eng_key, chn_val in translate_dict.items():
            if eng_key.lower() == hit_lower:
                return chn_val
        return hit_raw

    result = re_pattern.sub(sub_callback, text)
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
                        if val_strip:
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
    """处理shn，兼容行前空格、tab；完整匹配+局部子串替换，输出格式 Cheat Text="原文｜译文" """
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
            if strip_raw:
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
    else:
        out_lines.append(line)


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
