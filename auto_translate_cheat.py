import os
import json
import re
import time
import shutil
import hashlib
import xml.etree.ElementTree as ET
from ps4_ps5_mc4_tool import decode_mc4, encode_mc4

DICT_PATH = os.environ.get("DICT_PATH", "custom_dict.json")
STATE_FILE = "file_state.json"
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "").strip()

# 【专属游戏大写缩写优先｜最全金手指缩写库】
ABBREV_MAP = {
    "INF": "Infinite",
    "inf": "Infinite",
    "MAX": "Max",
    "max": "Max",
    "MIN": "Min",
    "min": "Min",
    "HP": "Health Points",
    "hp": "Health Points",
    "MP": "Mana Points",
    "mp": "Mana Points",
    "SP": "Stamina Points",
    "sp": "Stamina Points",
    "ATK": "Attack",
    "atk": "Attack",
    "DEF": "Defense",
    "def": "Defense",
    "VIT": "Vitality",
    "vit": "Vitality",
    "STA": "Stamina",
    "sta": "Stamina",
    "AMMO": "Ammunition",
    "ammo": "Ammunition",
    "SEC": "Second",
    "sec": "Second",
    "SECS": "Seconds",
    "secs": "Seconds",
    "PTS": "Points",
    "pts": "Points",
    "LVL": "Level",
    "lvl": "Level",
    "EXP": "Experience",
    "exp": "Experience",
    "GOLD": "Gold",
    "gold": "Gold"
}

translate_dict = {}
lower_full_index = {}
subst_pattern_list = []

miss_log_path = "translate_miss.log"
miss_set = set()
json_miss_english_set = set()
batch_translate_queue = []
BATCH_MAX_SIZE = 45
MAX_TEXT_LEN = 400

prev_file_state = {}
current_file_state = {}


def get_file_hash(filepath: str) -> str:
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def load_file_state():
    global prev_file_state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                prev_file_state = json.load(f)
        except Exception as e:
            print(f"[STATE WARN]读取状态文件失败:{e}，全部文件将执行全量翻译")
            prev_file_state = {}
    else:
        prev_file_state = {}


def save_file_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fw:
            json.dump(current_file_state, fw, ensure_ascii=False, indent=2)
        print(f"[STATE SAVE]已保存本轮文件哈希快照到 {STATE_FILE}")
    except Exception as e:
        print(f"[STATE SAVE ERROR] {e}")


def rebuild_indexes():
    global lower_full_index, subst_pattern_list
    lower_full_index.clear()
    for orig_key in translate_dict:
        k_low = orig_key.lower().strip()
        lower_full_index[k_low] = orig_key
    keys_sorted = sorted(translate_dict.keys(), key=lambda x: len(x), reverse=True)
    subst_pattern_list.clear()
    for k in keys_sorted:
        v = translate_dict[k]
        pat = re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE)
        subst_pattern_list.append((pat, v))


try:
    with open(DICT_PATH, "r", encoding="utf-8") as f:
        translate_dict = json.load(f)
    rebuild_indexes()
except Exception as e:
    print(f"[WARN] 读取词典失败 {DICT_PATH} : {e}")
    translate_dict = {}
    rebuild_indexes()


def expand_abbreviation(text: str) -> str:
    t = text
    # 优先替换大写缩写，精准单词边界匹配
    for abbr, full_txt in ABBREV_MAP.items():
        pat = re.compile(rf"\b{re.escape(abbr)}\b")
        t = pat.sub(full_txt, t)
    return t


def do_substitute(text: str) -> str:
    res = text
    for pat, repl in subst_pattern_list:
        res = pat.sub(repl, res)
    return res


def is_maybe_english(s: str) -> bool:
    s_strip = s.strip()
    if not s_strip:
        return False
    cnt_en = len(re.findall(r'[a-zA-Z]', s_strip))
    total = len(s_strip)
    return cnt_en / total > 0.2


PAT_CHEAT_TEXT = re.compile(r'Cheat Text="(.*?)"', re.IGNORECASE)

deepl_translator = None
if DEEPL_API_KEY:
    try:
        import deepl
        deepl_translator = deepl.Translator(
            DEEPL_API_KEY,
            server_url="https://api-free.deepl.com",
            timeout=12
        )
        print("[INFO] ✅ DeepL Free API 已启用；词典优先翻译，仅新词调用API，翻译成功自动扩充词典")
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
        print(f"[DEEPL BATCH] 批量翻译 {len(texts)} 条新词条 ...")
        res_list = deepl_translator.translate_text(texts, target_lang="ZH")
        for ori, obj in zip(texts, res_list):
            ori_strip = ori.strip()
            trans_result = obj.text.strip()
            if trans_result == "" or trans_result.lower() == ori_strip.lower():
                result_map[ori] = ori
                continue
            result_map[ori] = trans_result
            if ori not in translate_dict:
                translate_dict[ori] = trans_result
                rebuild_indexes()
                print(f"[DICT AUTO ADD] 自动扩充词典：`{ori}` -> `{trans_result}`")
        time.sleep(0.4)
    except deepl.exceptions.QuotaExceededException:
        print("[DEEPL] ⚠️本月免费字符配额用尽，停用API，后续全部仅用本地词典")
        deepl_translator = None
    except deepl.exceptions.TooManyRequestsException:
        print("[DEEPL] ⚠️API限流，本批次全部保留原始英文")
    except Exception as e:
        print(f"[DEEPL BATCH WARN] {repr(e)}")
    return result_map


def translate_text_prepare(text: str):
    """
    优先级：本地词典完整匹配 → 大写缩写精准展开 → 自定义子串替换 → DeepL翻译
    """
    if not text:
        return True, text, False
    src_strip = text.strip()
    src_low = src_strip.lower()
    if src_low in lower_full_index:
        orig_dict_key = lower_full_index[src_low]
        return True, translate_dict[orig_dict_key], False
    step1 = expand_abbreviation(text)
    step2 = do_substitute(step1)
    if is_maybe_english(step2) and 0 < len(step2) <= MAX_TEXT_LEN and deepl_translator is not None:
        return False, step2, True
    else:
        return True, step2, False


need_api_store = []
out_lines = []


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
                        need_api_store.append({"type": "json", "obj": obj, "key": k, "text": res})
                        batch_translate_queue.append(res)
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
        print(f"[JSON {'MODIFIED' if modified else 'NO CHANGE'}] {filepath}")
    except Exception as e:
        print(f"[PROCESS ERROR] {filepath} | {e}")


def process_shn_file(filepath):
    global out_lines
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
            if need_api:
                need_api_store.append({"type": "shn", "line": line, "match": match, "text": res})
                batch_translate_queue.append(res)
                out_lines.append(line)
            else:
                if raw_inner != res:
                    new_line = line[:match.start(1)] + res + line[match.end(1):]
                    out_lines.append(new_line)
                    changed = True
                else:
                    out_lines.append(line)
        else:
            out_lines.append(line)
    try:
        with open(filepath, "w", encoding="utf-8") as fw:
            fw.writelines(out_lines)
        print(f"[SHN {'MODIFIED' if changed else 'NO CHANGE'}] {filepath}")
    except Exception as e:
        print(f"[SHN WRITE ERROR] {filepath} | {e}")


def _translate_xml_attr(node, attr_name: str):
    val = node.get(attr_name)
    if val is None or not val.strip():
        return
    orig = val.strip()
    is_ok, res_txt, need_api = translate_text_prepare(orig)
    if need_api:
        need_api_store.append({
            "type": "mc4xml_attr",
            "node": node,
            "attr": attr_name,
            "text": res_txt
        })
        batch_translate_queue.append(res_txt)
        miss_set.add(orig)
    else:
        if res_txt != orig:
            node.set(attr_name, res_txt)


def process_mc4_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            mc4_raw_text = f.read()
    except Exception as e:
        print(f"[MC4 SKIP READ] {filepath} | {e}")
        return

    info = decode_mc4(mc4_raw_text)
    if info["status"] not in ("decrypted", "plaintext"):
        print(f"[MC4 SKIP DECRYPT] {filepath} status={info['status']} reason={info.get('reason','')}")
        return

    inner_xml = info["inner"]
    try:
        root = ET.fromstring(inner_xml)
    except Exception as e:
        print(f"[MC4 XML PARSE FAIL] {filepath} | {e}, keep original")
        return

    for tag_name in ("Cheat", "StartUP"):
        for elem in root.findall(f".//{tag_name}"):
            _translate_xml_attr(elem, "Text")
            _translate_xml_attr(elem, "Description")

    try:
        new_inner_xml = ET.tostring(root, encoding="unicode", xml_declaration=False)
        new_mc4_b64 = encode_mc4(new_inner_xml, info)
        with open(filepath, "w", encoding="utf-8") as fw:
            fw.write(new_mc4_b64)
        print(f"[MC4 PROCESSED] {filepath}")
    except Exception as e:
        print(f"[MC4 ENCODE FAIL] {filepath} | {e}, keep original file")


def scan_all_files(root_dir, run_shn: bool = True):
    file_counter = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "conf" in dirnames:
            dirnames.remove("conf")
        for fname in filenames:
            fullpath = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(fullpath, root_dir).replace("\\","/")
            file_counter += 1
            if file_counter % 20 == 0:
                print(f"[SCAN PROGRESS] 已扫描 {file_counter} 文件")

            current_hash = get_file_hash(fullpath)
            current_file_state[rel_path] = current_hash
            if rel_path in prev_file_state and prev_file_state[rel_path] == current_hash:
                ext = fname.lower()
                if ext.endswith((".json",".shn",".mc4")):
                    print(f"[SKIP UNCHANGED] {rel_path} 文件无变更，跳过翻译")
                continue

            try:
                ext = fname.lower()
                if ext.endswith(".json"):
                    print(f"Processing JSON(changed): {fullpath}")
                    process_json_file(fullpath)
                elif ext.endswith(".shn") and run_shn:
                    print(f"Processing SHN(changed): {fullpath}")
                    process_shn_file(fullpath)
                elif ext.endswith(".mc4"):
                    print(f"Processing MC4(changed): {fullpath}")
                    process_mc4_file(fullpath)
            except Exception as e:
                print(f"[SCAN FILE SKIP] {fullpath} | {e}")

            if len(batch_translate_queue) >= BATCH_MAX_SIZE:
                flush_batch_translate(batch_translate_queue)
                batch_translate_queue.clear()


def apply_batch_result(trans_map: dict):
    global out_lines
    for item in need_api_store:
        ori_txt = item["text"]
        final = trans_map.get(ori_txt, ori_txt)
        if item["type"] == "json":
            obj = item["obj"]
            k = item["key"]
            obj[k] = final
        elif item["type"] == "shn":
            m = item["match"]
            new_line = item["line"][:m.start(1)] + final + item["line"][m.end(1):]
            try:
                idx = out_lines.index(item["line"])
                out_lines[idx] = new_line
            except ValueError:
                pass
        elif item["type"] == "mc4xml_attr":
            node = item["node"]
            attr_name = item["attr"]
            node.set(attr_name, final)


def save_updated_dict():
    try:
        sorted_dict = dict(sorted(translate_dict.items(), key=lambda x: x[0].lower()))
        with open(DICT_PATH, "w", encoding="utf-8") as fw:
            json.dump(sorted_dict, fw, ensure_ascii=False, indent=2)
        print(f"[DICT SAVE] 已保存自动扩充后的词典到 {DICT_PATH}")
    except Exception as e:
        print(f"[DICT SAVE ERROR] {e}")


def main():
    global need_api_store, batch_translate_queue
    ROOT_DIR = os.getcwd()
    load_file_state()
    try:
        print("===== STAGE 1: 增量扫描全部文件，仅处理变更的json+shn+mc4 =====")
        scan_all_files(ROOT_DIR, run_shn=True)
        print("[STAGE1 DONE] 第一阶段文件扫描完成，执行剩余批量翻译")
        trans_result = flush_batch_translate(batch_translate_queue)
        apply_batch_result(trans_result)

        if len(json_miss_english_set) > 0:
            print(f"\n===== STAGE 2: 二次批量翻译JSON漏网英文 =====")
            all_miss_list = list(json_miss_english_set)
            for i in range(0, len(all_miss_list), BATCH_MAX_SIZE):
                slice_list = all_miss_list[i:i+BATCH_MAX_SIZE]
                flush_batch_translate(slice_list)
            rebuild_indexes()
            print("\n===== STAGE3: 使用扩充完成的新词典，重新扫描全部JSON文件（shn/mc4不再处理） =====")
            need_api_store.clear()
            batch_translate_queue.clear()
            scan_all_files(ROOT_DIR, run_shn=False)
        else:
            print("[STAGE2‑3] 没有漏网英文词条，跳过二次翻译&重扫JSON")
        save_updated_dict()
        save_file_state()
    except Exception as e:
        print(f"[SCAN FATAL ERROR] {e}")
    try:
        with open(miss_log_path, "w", encoding="utf-8") as f:
            for word in sorted(miss_set):
                f.write(word + "\n")
        print(f"\nMiss words saved to {miss_log_path}, total miss:{len(miss_set)}")
    except Exception as e:
        print(f"[WRITE LOG ERROR] {e}")


if __name__ == "__main__":
    main()
