import os
import json
import re
import time
import requests

# 环境变量读取词典路径
DICT_PATH = os.environ.get("DICT_PATH", "custom_dict.json")
# LibreTranslate公共演示服务，无需API密钥
LIBRE_API_URL = "https://translate.argosopentech.com/translate"

# 加载自定义翻译词典
try:
    with open(DICT_PATH, "r", encoding="utf-8") as f:
        translate_dict = json.load(f)
except Exception as e:
    print(f"[WARN] 读取词典失败 {DICT_PATH} : {e}")
    translate_dict = {}

miss_log_path = "translate_miss.log"
miss_set = set()


def is_maybe_english(s: str) -> bool:
    """判断文本是否疑似英文，过滤纯中文、数字、符号，减少无效接口调用"""
    s_strip = s.strip()
    if not s_strip:
        return False
    cnt_en = len(re.findall(r'[a-zA-Z]', s_strip))
    total = len(s_strip)
    return cnt_en / total > 0.2


# 匹配shn文件 Cheat Text="xxx"
PAT_CHEAT_TEXT = re.compile(r'Cheat Text="(.*?)"', re.IGNORECASE)


def build_case_insensitive_pattern(d):
    """构建大小写不敏感正则，长词条优先匹配，避免短词抢占"""
    keys = sorted(d.keys(), key=len, reverse=True)
    escaped_keys = [re.escape(k) for k in keys]
    pattern = re.compile("|".join(escaped_keys), flags=re.IGNORECASE)
    return pattern


re_pattern = build_case_insensitive_pattern(translate_dict)


def libre_translate(text: str):
    """调用公共LibreTranslate接口；失败/超时返回None，不会抛出异常"""
    if not text or len(text.strip()) == 0:
        return None
    payload = {
        "q": text,
        "source": "en",
        "target": "zh",
        "format": "text"
    }
    try:
        time.sleep(0.4)  # 请求间隔，防止公共接口限流429
        resp = requests.post(LIBRE_API_URL, data=payload, timeout=12)
        resp.raise_for_status()
        json_resp = resp.json()
        return json_resp["translatedText"]
    except Exception as e:
        print(f"[LibreTranslate WARN] 公共接口请求失败: {repr(e)}")
        return None


def translate_text(text: str):
    """
    翻译优先级：
    1.本地词典完整大小写不敏感匹配
    2.本地词典局部片段子串替换
    3.公共LibreTranslate接口兜底翻译
    全部失败返回原始文本
    """
    if not text:
        return text
    src_strip = text.strip()

    # 第一步：完整词条匹配
    match_full = None
    for eng_key, chn_val in translate_dict.items():
        if eng_key.lower() == src_strip.lower():
            match_full = chn_val
            break
    if match_full is not None:
        return match_full

    # 第二步：局部片段替换
    def sub_callback(match_obj):
        hit_raw = match_obj.group(0)
        hit_lower = hit_raw.lower()
        for eng_key, chn_val in translate_dict.items():
            if eng_key.lower() == hit_lower:
                return chn_val
        return hit_raw

    local_result = re_pattern.sub(sub_callback, text)
    if local_result != text:
        return local_result

    # 第三步：词典完全无命中，疑似英文调用公共翻译接口
    if is_maybe_english(text):
        api_result = libre_translate(text)
        if api_result:
            return f"{text}｜{api_result}"

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
                        if val_strip and is_maybe_english(val_strip):
                            miss_set.add(val_strip)
                elif isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    try:
        walk(data)
        # BUG修复：无论是否修改强制写回磁盘，保证json文件不会丢失
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if modified:
            print(f"[JSON MODIFIED] {filepath}")
        else:
            print(f"[JSON NO CHANGE, FORCE SAVE] {filepath}")
    except Exception as e:
        print(f"[PROCESS ERROR] {filepath} | {e}")


def process_shn_file(filepath):
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
            translated_inner = translate_text(raw_inner)
            strip_raw = raw_inner.strip()
            if strip_raw and is_maybe_english(strip_raw):
                miss_set.add(strip_raw)

            if raw_inner != translated_inner:
                new_text_in_quotes = translated_inner
                new_line = line[:match.start(1)] + new_text_in_quotes + line[match.end(1):]
                out_lines.append(new_line)
                changed = True
            else:
                out_lines.append(line)
        else:
            out_lines.append(line)
    # BUG修复：无论有无改动强制写入，修复丢失最后一行问题
    try:
        with open(filepath, "w", encoding="utf-8") as fw:
            fw.writelines(out_lines)
        if changed:
            print(f"[SHN MODIFIED] {filepath}")
        else:
            print(f"[SHN NO CHANGE, FORCE SAVE] {filepath}")
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
    # 输出未命中词条日志
    try:
        with open(miss_log_path, "w", encoding="utf-8") as f:
            for word in sorted(miss_set):
                f.write(word + "\n")
        print(f"\nMiss words saved to {miss_log_path}, total miss:{len(miss_set)}")
    except Exception as e:
        print(f"[WRITE LOG ERROR] {e}")


if __name__ == "__main__":
    main()
