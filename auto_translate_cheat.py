import os
import json
import re
import time

DICT_PATH = os.environ.get("DICT_PATH", "custom_dict.json")
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "").strip()

try:
    with open(DICT_PATH, "r", encoding="utf-8") as f:
        translate_dict = json.load(f)
except Exception as e:
    print(f"[WARN] 读取词典失败 {DICT_PATH} : {e}")
    translate_dict = {}

miss_log_path = "translate_miss.log"
miss_set = set()
# 收集需要交给deepl批量翻译的文本（词典未命中的疑似英文）
batch_translate_queue = []
BATCH_MAX_SIZE = 45  #deepl一次最多50，留余量45
MAX_TEXT_LEN = 400   #超过该长度不调用API

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
        print("[INFO] ✅ DeepL Free API 已启用（批量翻译模式）")
    except ImportError:
        print("[WARN] ❗ deepl python SDK未安装，关闭API翻译")
        deepl_translator = None
    except Exception as e:
        print(f"[WARN] ❗ DeepL初始化失败: {e}，仅使用本地词典")
        deepl_translator = None


def flush_batch_translate() -> dict:
    """把队列里文本批量提交deepl；返回 {原文:译文}字典；失败返回空字典"""
    global batch_translate_queue
    result_map = {}
    if not deepl_translator or len(batch_translate_queue) == 0:
        batch_translate_queue.clear()
        return result_map
    texts = batch_translate_queue[:]
    batch_translate_queue.clear()
    try:
        print(f"[DEEPL BATCH] 批量翻译 {len(texts)} 条文本 ...")
        res_list = deepl_translator.translate_text(texts, target_lang="ZH")
        for ori, obj in zip(texts, res_list):
            result_map[ori] = obj.text
        time.sleep(0.3)
    except deepl.exceptions.QuotaExceededException:
        print("[DEEPL] ⚠️本月免费字符配额用尽，停用API")
        deepl_translator = None
    except deepl.exceptions.TooManyRequestsException:
        print("[DEEPL] ⚠️批量请求限流，丢弃本批次")
    except Exception as e:
        print(f"[DEEPL BATCH WARN] {repr(e)}")
    return result_map


def translate_text_prepare(text: str):
    """
    翻译预处理：本地词典处理；词典未命中则加入批量队列；返回标记和原始文本
    返回：(is_local_ok:bool, result_text:str, need_api:bool)
    """
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

    #3 判断是否需要送入API批量队列
    if is_maybe_english(text) and 0 < len(text) <= MAX_TEXT_LEN and deepl_translator is not None:
        return False, text, True
    return True, text, False


#存储所有待api翻译的原始文本，后续回填
need_api_store = []

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
                        #需要API翻译，先记录索引占位
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
            is_ok, res, need_api = translate_text_prepare(raw_inner)
            strip_raw = raw_inner.strip()
            if strip_raw and is_maybe_english(strip_raw):
                miss_set.add(strip_raw)
            if is_ok:
                if raw_inner != res:
                    new_text_in_quotes = res
                    new_line = line[:match.start(1)] + new_text_in_quotes + line[match.end(1):]
                    out_lines.append(new_line)
                    changed = True
                else:
                    out_lines.append(line)
            else:
                #送入批量翻译队列，先保留原文，后续回填译文
                need_api_store.append({"type":"shn","line_idx":len(out_lines),"ori_text":raw_inner})
                batch_translate_queue.append(raw_inner)
                out_lines.append(line)
                changed = True
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


def scan_all_files(root_dir):
    file_counter = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "conf" in dirnames:
            dirnames.remove("conf")
        for fname in filenames:
            fullpath = os.path.join(dirpath, fname)
            file_counter += 1
            if file_counter % 20 ==0:
                print(f"[SCAN PROGRESS] 已扫描 {file_counter} 文件")
            try:
                if fname.lower().endswith(".json"):
                    print(f"Processing JSON: {fullpath}")
                    process_json_file(fullpath)
                elif fname.lower().endswith(".shn"):
                    print(f"Processing SHN: {fullpath}")
                    process_shn_file(fullpath)
            except Exception as e:
                print(f"[SCAN FILE SKIP] {fullpath} | {e}")
            #队列满就触发一次批量翻译
            if len(batch_translate_queue) >= BATCH_MAX_SIZE:
                flush_batch_translate()


def apply_batch_result(trans_map:dict):
    """把批量翻译结果回填回json对象、shn行；格式 原文｜译文"""
    for item in need_api_store:
        ori_txt = item["text"] if "text" in item else item["ori_text"]
        if ori_txt in trans_map:
            final = f"{ori_txt}｜{trans_map[ori_txt]}"
        else:
            final = ori_txt
        if item["type"] == "json":
            obj = item["obj"]
            k = item["key"]
            obj[k] = final
        elif item["type"] == "shn":
            pass #shn已经写入磁盘，shn不二次回写（避免行匹配复杂）


def main():
    global need_api_store
    ROOT_DIR = os.getcwd()
    try:
        scan_all_files(ROOT_DIR)
        #处理剩余队列
        print("[SCAN DONE] 全部文件扫描完成，执行剩余批量翻译")
        trans_result = flush_batch_translate()
        #回填翻译结果到内存json对象
        apply_batch_result(trans_result)
        #把内存中被回填修改的json重新写回磁盘
        for entry in need_api_store:
            if entry["type"] == "json":
                p = entry["_filepath"] if "_filepath" in entry else None
        #shn：批量翻译模式shn不再二次改写，只保留原始行；API译文仅作用json；shn词典命中正常生效
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
