import os
import json
import re
import time

DICT_PATH = os.environ.get("DICT_PATH", "custom_dict.json")
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "").strip()

# 加载本地自定义词典
try:
    with open(DICT_PATH, "r", encoding="utf-8") as f:
        translate_dict = json.load(f)
except Exception as e:
    print(f"[WARN] 读取词典失败 {DICT_PATH} : {e}")
    translate_dict = {}

miss_log_path = "translate_miss.log"
miss_set = set()
json_miss_english_set = set()

batch_translate_queue = []
BATCH_MAX_SIZE = 45
MAX_TEXT_LEN = 400

def is_maybe_english(s: str) -> bool:
    s_strip = s.strip()
    if not s_strip:
        return False
    cnt_en = len(re.findall(r'[a-zA-Z]', s_strip))
    total = len(s_strip)
    return cnt_en / total > 0.2

PAT_CHEAT_TEXT = re.compile(r'Cheat Text="(.*?)"', re.IGNORECASE)

def build_case_insensitive_pattern(d):
    keys = sorted(d.keys(), key=len, reverse=True)
    escaped_keys = [re.escape(k) for k in keys]
    pattern = re.compile("|".join(escaped_keys), flags=re.IGNORECASE)
    return pattern

# 全局正则对象，词典更新后需要重新赋值
re_pattern = build_case_insensitive_pattern(translate_dict)

deepl_translator = None
if DEEPL_API_KEY:
    try:
        import deepl
        deepl_translator = deepl.Translator(
            DEEPL_API_KEY,
            server_url="https://api-free.deepl.com",
            timeout=10
        )
        print("[INFO] ✅ DeepL Free API 已启用；新词翻译后自动扩充词典，同一轮CI重刷JSON")
    except ImportError:
        print("[WARN] ❗ deepl python SDK未安装，关闭API翻译，仅使用现有词典")
        deepl_translator = None
    except Exception as e:
        print(f"[WARN] ❗ DeepL初始化失败: {e}，仅使用现有词典")
        deepl_translator = None


def flush_batch_translate(text_list) -> dict:
    result_map = {}
    if not deepl_translator or len(text_list) == 0:
        return result_map
    texts = text_list[:]
    try:
        print(f"[DEEPL BATCH] 批量翻译 {len(texts)} 条文本 ...")
        res_list = deepl_translator.translate_text(texts, target_lang="ZH")
        for ori, obj in zip(texts, res_list):
            result_map[ori] = obj.text
            if ori not in translate_dict:
                translate_dict[ori] = obj.text
                print(f"[DICT AUTO ADD] 自动扩充词典：`{ori}` -> `{obj.text}`")
        time.sleep(0.3)
    except deepl.exceptions.QuotaExceededException:
        print("[DEEPL] ⚠️本月免费字符配额用尽，停用API")
        deepl_translator = None
    except deepl.exceptions.TooManyRequestsException:
        print("[DEEPL] ⚠️批量请求限流，本批次跳过")
    except Exception as e:
        print(f"[DEEPL BATCH WARN] {repr(e)}")
    return result_map


def translate_text_prepare(text: str):
    """
    返回 (is_local_ok:bool, result_text:str, need_api:bool)
    shn只走到本地词典，不会送入API队列
    """
    global re_pattern
    if not text:
        return True, text, False
    src_strip = text.strip()

    #1 完整词典匹配
    match_full = None
    for eng_key, chn_val in translate_dict.items():
        if eng_key.lower() == src_strip.lower():
            match_full = chn_val
            break
    if match_full is not None:
        return True, match_full, False

    #2 局部子串替换
    def sub_callback(match_obj):
        hit_raw = match_obj.group(0)
        hit_lower = hit_raw.lower()
        for eng_key, chn_val in translate_dict.items():
            if eng_key.lower() == hit_lower:
                return chn_val
        return hit_raw
    local_result = re_pattern.sub(sub_callback, text)
    if local_result != text:
        return True, local_result, False

    # 词典完全未命中：判断是英文，加入待二次翻译集合
    if is_maybe_english(text) and 0 < len(text) <= MAX_TEXT_LEN:
        json_miss_english_set.add(text.strip())

    #3 JSON才允许送入API队列；shn不会走到这里
    if is_maybe_english(text) and 0 < len(text) <= MAX_TEXT_LEN and deepl_translator is not None:
        return False, text, True
    return True, text, False


need_api_store = []

def process_json_file(filepath):
    global re_pattern
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
                    is_ok, res, need_api = translate_text_prepare(v)
                    if is_ok:
                        if res != original:
                            obj[k] = res
                            modified = True
                        else:
                            val_strip = v.strip()
                            if val_strip and is_maybe_english(val_strip):
                                miss_set.add(val_strip)
                    else:
                        need_api_store.append({"type":"json","obj":obj,"key":k,"text":original})
                        batch_translate_queue.append(original)
                        miss_set.add(original.strip())
                elif isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
    try:
        walk(data)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if modified:
            print(f"[JSON MODIFIED] {filepath}")
        else:
            print(f"[JSON NO CHANGE, FORCE SAVE] {filepath}")
    except Exception as e:
        print(f"[PROCESS ERROR] {filepath} | {e}")


def process_shn_file(filepath):
    """SHN：只使用本地词典，**绝不调用API，不自动扩充词典**，保证文件正确性，只执行一轮"""
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
            is_ok, res, _ = translate_text_prepare(raw_inner)
            strip_raw = raw_inner.strip()
            if strip_raw and is_maybe_english(strip_raw):
                miss_set.add(strip_raw)
            if raw_inner != res:
                new_text_in_quotes = res
                new_line = line[:match.start(1)] + new_text_in_quotes + line[match.end(1):]
                out_lines.append(new_line)
                changed = True
            else:
                out_lines.append(line)
        else:
            out_lines.append(line)
    try:
        with open(filepath, "w", encoding="utf-8") as fw:
            fw.writelines(out_lines)
        if changed:
            print(f"[SHN MODIFIED] {filepath}")
        else:
            print(f"[SHN NO CHANGE, FORCE SAVE] {filepath}")
    except Exception as e:
        print(f"[SHN WRITE ERROR] {filepath} | {e}")


def scan_all_files(root_dir, run_shn:bool=True):
    """
    run_shn=True：处理json+shn；run_shn=False：仅重扫json，跳过shn
    """
    file_counter = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "conf" in dirnames:
            dirnames.remove("conf")
        for fname in filenames:
            fullpath = os.path.join(dirpath, fname)
            file_counter += 1
            if file_counter % 20 == 0:
                print(f"[SCAN PROGRESS] 已扫描 {file_counter} 文件")
            try:
                if fname.lower().endswith(".json"):
                    print(f"Processing JSON: {fullpath}")
                    process_json_file(fullpath)
                elif fname.lower().endswith(".shn") and run_shn:
                    print(f"Processing SHN: {fullpath}")
                    process_shn_file(fullpath)
            except Exception as e:
                print(f"[SCAN FILE SKIP] {fullpath} | {e}")
            if len(batch_translate_queue) >= BATCH_MAX_SIZE:
                flush_batch_translate(batch_translate_queue)
                batch_translate_queue.clear()


def apply_batch_result(trans_map:dict):
    """把批量翻译结果回填JSON内存对象，输出格式 原文｜译文"""
    for item in need_api_store:
        ori_txt = item["text"]
        if ori_txt in trans_map:
            final = f"{ori_txt}｜{trans_map[ori_txt]}"
        else:
            final = ori_txt
        if item["type"] == "json":
            obj = item["obj"]
            k = item["key"]
            obj[k] = final


def save_updated_dict():
    """把运行过程中自动扩充后的完整词典写回工作目录conf"""
    try:
        with open(DICT_PATH, "w", encoding="utf-8") as fw:
            json.dump(translate_dict, fw, ensure_ascii=False, indent=2)
        print(f"[DICT SAVE] 已保存自动扩充后的词典到 {DICT_PATH}")
    except Exception as e:
        print(f"[DICT SAVE ERROR] {e}")


def main():
    global need_api_store,batch_translate_queue,re_pattern
    ROOT_DIR = os.getcwd()
    try:
        # ----------------第一轮：完整扫描json+shn----------------
        print("===== STAGE 1: 第一轮扫描全部文件(json+shn) =====")
        scan_all_files(ROOT_DIR, run_shn=True)
        print("[STAGE1 DONE] 第一阶段文件扫描完成，执行剩余批量翻译")
        trans_result = flush_batch_translate(batch_translate_queue)
        apply_batch_result(trans_result)

        # ==========二次处理所有JSON收集漏网未命中英文词条============
        if len(json_miss_english_set) >0:
            print(f"\n===== STAGE 2: 二次批量翻译JSON漏网英文，共 {len(json_miss_english_set)} 条 =====")
            all_miss_list = list(json_miss_english_set)
            for i in range(0, len(all_miss_list), BATCH_MAX_SIZE):
                slice_list = all_miss_list[i:i+BATCH_MAX_SIZE]
                flush_batch_translate(slice_list)
            # ⚠️词典已经扩充完成，**必须重新生成大小写不敏感正则pattern**
            re_pattern = build_case_insensitive_pattern(translate_dict)
            print("\n===== STAGE3: 使用扩充完成的新词典，重新扫描全部JSON文件（shn不再处理） =====")
            # 清空旧的api存储队列，不需要再次api调用，只走本地新词典
            need_api_store.clear()
            batch_translate_queue.clear()
            # 只重新扫描JSON，run_shn=False，shn不再碰
            scan_all_files(ROOT_DIR, run_shn=False)
        else:
            print("[STAGE2‑3] 没有漏网英文词条，跳过二次翻译&重扫JSON")

        # 将扩充完毕的词典写入work_out/conf/custom_dict.json产物
        save_updated_dict()

    except Exception as e:
        print(f"[SCAN FATAL ERROR] {e}")

    #输出miss日志
    try:
        with open(miss_log_path, "w", encoding="utf-8") as f:
            for word in sorted(miss_set):
                f.write(word + "\n")
        print(f"\nMiss words saved to {miss_log_path}, total miss:{len(miss_set)}")
    except Exception as e:
        print(f"[WRITE LOG ERROR] {e}")


if __name__ == "__main__":
    main()
