#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ps4_ps5_mc4_tool.py — PS4 / PS5 金手指 .mc4 容器 解碼／還原 工具（獨立單檔版）

從 ps1_converter 專案抽出以下模組合併而成，可獨立執行、不依賴專案其餘程式碼：
    - ai/ps_cheats.py   （.mc4 容器偵測、解密、封裝、平台判斷）
    - ai/_aes_pure.py   （零相依純 Python AES-128/192/256，ECB + CBC）

.mc4 是 PS4（CUSAxxxxx）／PS5（PPSAxxxxx）金手指工具常見的加密容器格式：
    base64( AES-256-CBC( PKCS7( <Trainer>...</Trainer> 或 JSON ) ) )
本檔內建了業界工具 Bucanero mc4-cheat-decrypter (0.1.0) 所使用的固定金鑰／IV，
因此大多數 .mc4 檔可以「不用填任何金鑰」直接解密；若使用者的檔案是用別的金鑰
加密的，可透過命令列參數或函式參數覆寫金鑰／IV。

── 用法（命令列） ──────────────────────────────────────────────
    # 解碼：把 .mc4 還原成明文 .mc4.xml（或 .json，依內容自動判斷副檔名）
    python ps4_ps5_mc4_tool.py decode input.mc4 -o output.mc4.xml

    # 還原（重新加密）：把翻譯/編輯後的明文封回 .mc4
    python ps4_ps5_mc4_tool.py encode input.mc4.xml -o output.mc4 \
        [--like original.mc4]      # 若提供，會依原始封裝方式（明文/加密）封回
        [--key HEXSTRING] [--iv HEXSTRING]   # 自訂 AES 金鑰／IV（32/48/64 hex 字元）

    # 只想看看檔案是什麼格式 / 哪個平台
    python ps4_ps5_mc4_tool.py detect input.mc4

── 用法（當模組匯入） ──────────────────────────────────────────
    from ps4_ps5_mc4_tool import decode_mc4, encode_mc4, detect_ps_format

    with open("input.mc4", "r", encoding="utf-8") as f:
        text = f.read()
    info = decode_mc4(text)
    if info["status"] in ("plaintext", "decrypted"):
        xml_or_json = info["inner"]          # 明文 <Trainer>... 或 JSON
        # ...在這裡編輯／翻譯 xml_or_json...
        packed_b64 = encode_mc4(xml_or_json, info)   # 封回同樣的容器格式
"""

import re
import io
import gzip
import base64
import binascii
import zlib
import argparse
import sys
import os

# ════════════════════════════════════════════════════════════════════
#  第一部分：純 Python AES（128/192/256，ECB + CBC），零相依
#  來源：ai/_aes_pure.py（標準 FIPS-197 AES 實作）
# ════════════════════════════════════════════════════════════════════

_SBOX = (
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
)
_INV_SBOX = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i
_INV_SBOX = tuple(_INV_SBOX)

_RCON = (0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36,
         0x6c,0xd8,0xab,0x4d,0x9a)


def _xtime(a):
    a <<= 1
    if a & 0x100:
        a ^= 0x11b
    return a & 0xff


def _mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r & 0xff


def _key_expansion(key):
    nk = len(key) // 4
    nr = {4: 10, 6: 12, 8: 14}[nk]
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[b] for b in temp]
            temp[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            temp = [_SBOX[b] for b in temp]
        w.append([w[i - nk][j] ^ temp[j] for j in range(4)])
    return w, nr


def _add_round_key(s, w, rnd):
    for c in range(4):
        for r in range(4):
            s[r][c] ^= w[rnd * 4 + c][r]


def _bytes_to_state(block):
    return [[block[r + 4 * c] for c in range(4)] for r in range(4)]


def _state_to_bytes(s):
    return bytes(s[r][c] for c in range(4) for r in range(4))


def _encrypt_block(block, w, nr):
    s = _bytes_to_state(block)
    _add_round_key(s, w, 0)
    for rnd in range(1, nr):
        s = [[_SBOX[s[r][c]] for c in range(4)] for r in range(4)]      # SubBytes
        s = [s[r][r:] + s[r][:r] for r in range(4)]                    # ShiftRows
        # MixColumns
        for c in range(4):
            a = [s[r][c] for r in range(4)]
            s[0][c] = _mul(a[0], 2) ^ _mul(a[1], 3) ^ a[2] ^ a[3]
            s[1][c] = a[0] ^ _mul(a[1], 2) ^ _mul(a[2], 3) ^ a[3]
            s[2][c] = a[0] ^ a[1] ^ _mul(a[2], 2) ^ _mul(a[3], 3)
            s[3][c] = _mul(a[0], 3) ^ a[1] ^ a[2] ^ _mul(a[3], 2)
        _add_round_key(s, w, rnd)
    s = [[_SBOX[s[r][c]] for c in range(4)] for r in range(4)]
    s = [s[r][r:] + s[r][:r] for r in range(4)]
    _add_round_key(s, w, nr)
    return _state_to_bytes(s)


def _decrypt_block(block, w, nr):
    s = _bytes_to_state(block)
    _add_round_key(s, w, nr)
    for rnd in range(nr - 1, 0, -1):
        s = [s[r][-r:] + s[r][:-r] if r else s[r] for r in range(4)]   # InvShiftRows
        s = [[_INV_SBOX[s[r][c]] for c in range(4)] for r in range(4)]  # InvSubBytes
        _add_round_key(s, w, rnd)
        # InvMixColumns
        for c in range(4):
            a = [s[r][c] for r in range(4)]
            s[0][c] = _mul(a[0],14) ^ _mul(a[1],11) ^ _mul(a[2],13) ^ _mul(a[3],9)
            s[1][c] = _mul(a[0],9)  ^ _mul(a[1],14) ^ _mul(a[2],11) ^ _mul(a[3],13)
            s[2][c] = _mul(a[0],13) ^ _mul(a[1],9)  ^ _mul(a[2],14) ^ _mul(a[3],11)
            s[3][c] = _mul(a[0],11) ^ _mul(a[1],13) ^ _mul(a[2],9)  ^ _mul(a[3],14)
    s = [s[r][-r:] + s[r][:-r] if r else s[r] for r in range(4)]
    s = [[_INV_SBOX[s[r][c]] for c in range(4)] for r in range(4)]
    _add_round_key(s, w, 0)
    return _state_to_bytes(s)


def cbc_decrypt(data, key, iv):
    w, nr = _key_expansion(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        blk = data[i:i + 16]
        dec = _decrypt_block(blk, w, nr)
        out.extend(x ^ y for x, y in zip(dec, prev))
        prev = blk
    return bytes(out)


def cbc_encrypt(data, key, iv):
    w, nr = _key_expansion(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        blk = bytes(x ^ y for x, y in zip(data[i:i + 16], prev))
        enc = _encrypt_block(blk, w, nr)
        out.extend(enc)
        prev = enc
    return bytes(out)


def ecb_decrypt(data, key):
    w, nr = _key_expansion(key)
    return b''.join(_decrypt_block(data[i:i + 16], w, nr)
                    for i in range(0, len(data), 16))


def ecb_encrypt(data, key):
    w, nr = _key_expansion(key)
    return b''.join(_encrypt_block(data[i:i + 16], w, nr)
                    for i in range(0, len(data), 16))


# ════════════════════════════════════════════════════════════════════
#  第二部分：PS4 / PS5 金手指格式：偵測 + .mc4 容器解 / 封裝
#  來源：ai/ps_cheats.py
# ════════════════════════════════════════════════════════════════════

# ────────────────────────────────────────────────────────────────────
#  MC4 內建金鑰（AES-256-CBC）
#  來源：Bucanero 的 mc4-cheat-decrypter（0.1.0, 2023）——PS4/PS5 金手指
#  場景通用的 .mc4 加解密工具，金鑰/IV 取自該工具二進位的常數符號。
#  多數 .mc4 檔可用此內建金鑰直接解密；若解不開，可在呼叫時另外
#  提供 key_hex / iv_hex 覆寫。
# ────────────────────────────────────────────────────────────────────
MC4_AES_KEY = b'304c6528f659c766110239a51cl5dd9c'   # 32 bytes
MC4_AES_IV  = b'u@}kzW2u[u(8DWar'                    # 16 bytes

# title id：PS4 = CUSAxxxxx、PS5 = PPSAxxxxx
_CUSA_RE = re.compile(r'\bCUSA\d{5}\b')
_PPSA_RE = re.compile(r'\bPPSA\d{5}\b')

# 一段夠長、只含 base64 字元的 blob（.mc4 讀進來就是這個）
_B64_BLOB_RE = re.compile(r'^[A-Za-z0-9+/\r\n=]+$')


def sniff_platform(text, filename=None):
    """回 'ps5' / 'ps4' / None。先看內容 title id、再看檔名。"""
    if text:
        if _PPSA_RE.search(text[:4000]):
            return 'ps5'
        if _CUSA_RE.search(text[:4000]):
            return 'ps4'
    if filename:
        if _PPSA_RE.search(filename):
            return 'ps5'
        if _CUSA_RE.search(filename):
            return 'ps4'
    return None


def platform_label(plat):
    return {'ps4': 'PS4', 'ps5': 'PS5'}.get(plat, 'PS4/PS5')


def looks_like_mc4_blob(text):
    """這份文字看起來是不是 .mc4 容器（base64 blob）。

    判準：去掉空白後全是 base64 字元、長度夠長、能 base64 解碼、
    且**不是**一眼可見的 XML/JSON（那些有自己的偵測分支、別搶）。
    """
    if not text:
        return False
    s = text.strip()
    if s[:1] in ('<', '{', '['):
        return False
    if len(s) < 64:
        return False
    compact = re.sub(r'\s+', '', s)
    if not _B64_BLOB_RE.match(compact):
        return False
    if len(compact) % 4 != 0:
        return False
    try:
        raw = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return False
    # 太短的當不是；容器至少會有一個 16-byte 區塊
    return len(raw) >= 16


def _try_plaintext(raw):
    """密文 blob 解 base64 後，試著當『明文容器』讀（有些工具的 .mc4
    只是 base64(明文) 或 gzip(明文)，沒真的加密）。
    成功回 (xml_or_json_text, wrap_kind)；失敗回 (None, None)。"""
    # 1) 直接 UTF-8
    for enc in ('utf-8-sig', 'utf-8'):
        try:
            s = raw.decode(enc)
            if '<Trainer' in s[:2000] or '"mods"' in s[:2000] \
               or s.lstrip()[:1] in ('<', '{'):
                return s, 'b64'
        except UnicodeDecodeError:
            pass
    # 2) gzip / zlib / raw-deflate
    for name, fn in (('gzip', lambda b: zlib.decompress(b, 31)),
                     ('zlib', zlib.decompress),
                     ('deflate', lambda b: zlib.decompress(b, -15))):
        try:
            dec = fn(raw)
            s = dec.decode('utf-8', errors='strict')
            if '<Trainer' in s[:2000] or '"mods"' in s[:2000] \
               or s.lstrip()[:1] in ('<', '{'):
                return s, 'b64+' + name
        except Exception:
            pass
    return None, None


def _aes_cbc_dec(raw, key, iv):
    """AES-CBC 解密（原始位元組）。優先 pycryptodome、退到純 Python。"""
    try:
        from Crypto.Cipher import AES
        return AES.new(key, AES.MODE_CBC, iv or (b'\x00' * 16)).decrypt(raw)
    except ImportError:
        return cbc_decrypt(raw, key, iv or (b'\x00' * 16))


def _aes_ecb_dec(raw, key):
    try:
        from Crypto.Cipher import AES
        return AES.new(key, AES.MODE_ECB).decrypt(raw)
    except ImportError:
        return ecb_decrypt(raw, key)


def _aes_decrypt(raw, key, iv):
    """回明文位元組或 None。優先 CBC（樣本特徵），退而 ECB。
    自動去 PKCS7 padding。"""
    for mode_name in ('cbc', 'ecb'):
        try:
            if mode_name == 'cbc':
                dec = _aes_cbc_dec(raw, key, iv)
            else:
                dec = _aes_ecb_dec(raw, key)
        except Exception:
            continue
        # 去 PKCS7
        if dec:
            pad = dec[-1]
            if 1 <= pad <= 16 and dec[-pad:] == bytes([pad]) * pad:
                dec_try = dec[:-pad]
            else:
                dec_try = dec
            try:
                s = dec_try.decode('utf-8')
                low = s[:2000]
                if ('<Trainer' in low or '&lt;Trainer' in low
                        or 'Trainer' in low
                        or low.lstrip()[:1] in ('<', '{')
                        or low.lstrip().startswith('&lt;')):
                    return dec_try
            except UnicodeDecodeError:
                pass
    return None


def _aes_encrypt(plain, key, iv, mode_name='cbc'):
    # PKCS7
    pad = 16 - (len(plain) % 16)
    plain = plain + bytes([pad]) * pad
    try:
        from Crypto.Cipher import AES
        if mode_name == 'cbc':
            return AES.new(key, AES.MODE_CBC, iv or (b'\x00' * 16)).encrypt(plain)
        return AES.new(key, AES.MODE_ECB).encrypt(plain)
    except ImportError:
        if mode_name == 'cbc':
            return cbc_encrypt(plain, key, iv or (b'\x00' * 16))
        return ecb_encrypt(plain, key)


def _hex_to_bytes(h):
    if not h:
        return None
    try:
        return bytes.fromhex(re.sub(r'\s+', '', h))
    except ValueError:
        return None


def decode_mc4(text, key_hex=None, iv_hex=None):
    """把 .mc4 容器解成明文 XML/JSON。

    回 dict：
      status   'plaintext'  → 只是 base64/gzip 包的明文，成功
               'decrypted'  → 用金鑰（自訂或內建）AES 解密成功
               'encrypted'  → 真的加密、又沒可用 key → 無法翻譯
               'bad'        → 連 base64 都不是
      inner    明文 XML/JSON 字串（前兩種才有）
      wrap     封回時要用的方式（'b64' / 'b64+gzip' / 'aes-cbc' …）
      key/iv   解密用到的 key/iv（decrypted 才有，供封回）
      reason   給使用者看的說明
    """
    s = (text or '').strip()
    compact = re.sub(r'\s+', '', s)
    try:
        raw = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return {'status': 'bad', 'inner': None, 'wrap': None,
                'reason': '不是有效的 base64 .mc4 容器'}

    # 1) 沒加密（base64/gzip 包明文）
    inner, wrap = _try_plaintext(raw)
    if inner is not None:
        return {'status': 'plaintext', 'inner': inner, 'wrap': wrap,
                'reason': ''}

    # 2) 用金鑰試 AES：優先使用者指定，否則用內建 MC4 金鑰
    key = _hex_to_bytes(key_hex)
    iv = _hex_to_bytes(iv_hex)
    used_builtin = False
    if not (key and len(key) in (16, 24, 32)):
        key, iv, used_builtin = MC4_AES_KEY, MC4_AES_IV, True
    if key and len(key) in (16, 24, 32):
        dec = _aes_decrypt(raw, key, iv)
        if dec is not None:
            inner = dec.decode('utf-8', errors='replace')
            return {'status': 'decrypted', 'inner': inner,
                    'wrap': 'aes-cbc', 'key': key, 'iv': iv,
                    'builtin_key': used_builtin, 'reason': ''}
        if not used_builtin:
            return {'status': 'encrypted', 'inner': None, 'wrap': None,
                    'reason': ('提供的 AES key 解不開這個 .mc4'
                               '（key 長度或 IV 不對，或不是這支工具加的密）。')}

    # 3) 真的加密、內建與自訂金鑰都解不開
    return {'status': 'encrypted', 'inner': None, 'wrap': None,
            'reason': ('這個 .mc4 用的不是內建 MC4 金鑰、也沒有可用的自訂'
                       '金鑰，無法解開。\n'
                       '→ 請用你的 PS4/PS5 金手指工具匯出明文'
                       '（.mc4.xml / .shn / .json）再處理，\n'
                       '　或用 --key / --iv 參數提供該工具的 AES 金鑰。')}


def encode_mc4(inner_text, info):
    """把（翻譯/編輯後的）明文 XML/JSON 依照原本的包法封回 .mc4 容器（base64）。
    info 是 decode_mc4 的回傳 dict。回 base64 字串。"""
    wrap = info.get('wrap') or 'b64'
    data = inner_text.encode('utf-8')
    if wrap.startswith('b64+gzip') or wrap == 'gzip':
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb') as g:
            g.write(inner_text.encode('utf-8'))
        data = buf.getvalue()
    elif wrap.startswith('b64+zlib') or wrap == 'zlib':
        data = zlib.compress(inner_text.encode('utf-8'))
    elif wrap.startswith('b64+deflate'):
        co = zlib.compressobj(9, zlib.DEFLATED, -15)
        data = co.compress(inner_text.encode('utf-8')) + co.flush()
    elif wrap == 'aes-cbc':
        _k = info.get('key') or MC4_AES_KEY
        _iv = info.get('iv') or MC4_AES_IV
        enc = _aes_encrypt(inner_text.encode('utf-8'), _k, _iv, 'cbc')
        if enc is None:
            # 加密失敗就退回明文 base64，至少不掉資料
            data = inner_text.encode('utf-8')
        else:
            data = enc
    else:  # 'b64' 純明文
        data = inner_text.encode('utf-8')
    return base64.b64encode(data).decode('ascii')


def detect_ps_format(text, filename=None):
    """回 (fmt, platform)。

    fmt: 'ps_json' / 'ps_shn' / 'ps_mc4xml' / 'ps_mc4' / None
    platform: 'ps4' / 'ps5' / None
    """
    if not text:
        return None, None
    plat = sniff_platform(text, filename)
    head = text.lstrip()[:400]

    if head.startswith('{'):
        if '"mods"' in text[:3000]:
            return 'ps_json', plat
    if head.startswith('<?xml') or head.startswith('<Trainer'):
        if '<Cheatline>' in text[:12000] or '<StartUP' in text[:12000]:
            return 'ps_shn', plat
        if '<Trainer' in text[:1500]:
            return 'ps_mc4xml', plat
    # base64 容器（.mc4）——放最後，才不會搶走 XML/JSON
    if looks_like_mc4_blob(text):
        return 'ps_mc4', plat
    return None, plat


# ════════════════════════════════════════════════════════════════════
#  第三部分：命令列工具（CLI）
# ════════════════════════════════════════════════════════════════════

def _read_text_file(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def _cmd_detect(args):
    text = _read_text_file(args.input)
    fmt, plat = detect_ps_format(text, filename=args.input)
    print(f"檔案: {args.input}")
    print(f"格式: {fmt or '無法辨識'}")
    print(f"平台: {platform_label(plat)}")
    if fmt == 'ps_mc4':
        info = decode_mc4(text, key_hex=args.key, iv_hex=args.iv)
        print(f".mc4 狀態: {info['status']}")
        if info.get('reason'):
            print(f"說明: {info['reason']}")


def _cmd_decode(args):
    text = _read_text_file(args.input)
    fmt, plat = detect_ps_format(text, filename=args.input)
    if fmt != 'ps_mc4':
        print(f"警告：這份檔案偵測到的格式是「{fmt}」，不是加密的 .mc4 容器，"
              f"應該已經是明文了。", file=sys.stderr)
        if fmt is None:
            sys.exit(1)

    info = decode_mc4(text, key_hex=args.key, iv_hex=args.iv)
    if info['status'] in ('plaintext', 'decrypted'):
        out_path = args.output
        if not out_path:
            base, _ = os.path.splitext(args.input)
            out_path = base + '.mc4.xml' if info['inner'].lstrip().startswith('<') \
                else base + '.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(info['inner'])
        used = '內建 MC4 金鑰' if info.get('builtin_key') else \
               ('自訂金鑰' if info['status'] == 'decrypted' else '無需金鑰（明文封裝）')
        print(f"解碼成功（{used}），平台：{platform_label(plat)}")
        print(f"已寫入：{out_path}")
    else:
        print(f"解碼失敗：{info['status']}", file=sys.stderr)
        print(info.get('reason', ''), file=sys.stderr)
        sys.exit(1)


def _cmd_encode(args):
    inner_text = _read_text_file(args.input)

    info = {'wrap': 'b64'}  # 預設：純 base64 明文封裝
    if args.like:
        like_text = _read_text_file(args.like)
        info = decode_mc4(like_text, key_hex=args.key, iv_hex=args.iv)
        if info['status'] not in ('plaintext', 'decrypted'):
            print(f"--like 參考檔解不開（{info['status']}），改用預設純明文封裝。",
                  file=sys.stderr)
            info = {'wrap': 'b64'}
    elif args.key:
        key = _hex_to_bytes(args.key)
        iv = _hex_to_bytes(args.iv) or (b'\x00' * 16)
        info = {'wrap': 'aes-cbc', 'key': key, 'iv': iv}

    packed = encode_mc4(inner_text, info)
    out_path = args.output or (os.path.splitext(args.input)[0] + '.mc4')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(packed)
    print(f"封裝方式：{info.get('wrap')}")
    print(f"已寫入：{out_path}")


def main():
    p = argparse.ArgumentParser(
        description='PS4/PS5 金手指 .mc4 容器 解碼／還原 工具')
    sub = p.add_subparsers(dest='cmd', required=True)

    p_detect = sub.add_parser('detect', help='偵測檔案格式與平台（PS4/PS5）')
    p_detect.add_argument('input', help='輸入檔案路徑')
    p_detect.add_argument('--key', help='自訂 AES 金鑰（hex，16/24/32 bytes）')
    p_detect.add_argument('--iv', help='自訂 AES IV（hex，16 bytes）')
    p_detect.set_defaults(func=_cmd_detect)

    p_decode = sub.add_parser('decode', help='把 .mc4 解碼成明文 XML/JSON')
    p_decode.add_argument('input', help='輸入 .mc4 檔案路徑')
    p_decode.add_argument('-o', '--output', help='輸出檔案路徑（預設自動命名）')
    p_decode.add_argument('--key', help='自訂 AES 金鑰（hex，16/24/32 bytes）')
    p_decode.add_argument('--iv', help='自訂 AES IV（hex，16 bytes）')
    p_decode.set_defaults(func=_cmd_decode)

    p_encode = sub.add_parser('encode', help='把明文 XML/JSON 封回 .mc4 容器')
    p_encode.add_argument('input', help='輸入明文檔案路徑（.mc4.xml / .json）')
    p_encode.add_argument('-o', '--output', help='輸出檔案路徑（預設自動命名）')
    p_encode.add_argument('--like', help='參考原始 .mc4，依其封裝方式（明文/加密）封回')
    p_encode.add_argument('--key', help='自訂 AES 金鑰（hex）；若提供則用 AES-CBC 加密封裝')
    p_encode.add_argument('--iv', help='自訂 AES IV（hex，16 bytes），預設全零')
    p_encode.set_defaults(func=_cmd_encode)

    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
