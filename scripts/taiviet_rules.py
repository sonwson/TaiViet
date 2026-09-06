"""
taiviet_rules.py
================
Quy tắc ngữ âm, chính tả và chuẩn ký tự chữ Thái Việt Nam (Tai Viet Script - Unicode U+AA80..U+AADF).
Bao gồm:
- Phân loại phụ âm Tổ Thấp (Low) / Tổ Cao (High)
- Nguyên âm (trước, sau, trên, dưới, nguyên âm kèm phụ âm cuối)
- Dấu thanh và quy tắc xác định 6 thanh điệu (Tone system)
- Ký hiệu đặc biệt và dấu câu
- Quy tắc cấu trúc âm tiết và hàm tiện ích kiểm tra / phân tích
"""

import re
from typing import Dict, Tuple, Optional, List

# ==============================================================================
# 1. BẢNG MÃ UNICODE VÀ PHÂN LOẠI KÝ TỰ (UNICODE & CHARACTER MAPPINGS)
# ==============================================================================

# Dải Unicode chuẩn của Tai Viet
TAI_VIET_RANGE: Tuple[int, int] = (0xAA80, 0xAADF)

# Bảng phụ âm: Gồm Tổ Thấp (Low) và Tổ Cao (High) tương ứng
CONSONANTS: Dict[str, Dict[str, str]] = {
    # Key: Phiên âm Latinh quy chuẩn
    "k":   {"low": "\uAA80", "high": "\uAA81", "name": "KO"},
    "kh":  {"low": "\uAA82", "high": "\uAA83", "name": "KHO"},
    "khov":{"low": "\uAA84", "high": "\uAA85", "name": "KHOV"},
    "ng":  {"low": "\uAA86", "high": "\uAA87", "name": "NGO"},
    "c":   {"low": "\uAA88", "high": "\uAA89", "name": "CHO"},
    "ch":  {"low": "\uAA8A", "high": "\uAA8B", "name": "TSHO"},
    "nh":  {"low": "\uAA8C", "high": "\uAA8D", "name": "NYO"},
    "d":   {"low": "\uAA8E", "high": "\uAA8F", "name": "DO"},
    "t":   {"low": "\uAA90", "high": "\uAA91", "name": "TO"},
    "th":  {"low": "\uAA92", "high": "\uAA93", "name": "THO"},
    "n":   {"low": "\uAA94", "high": "\uAA95", "name": "NO"},
    "b":   {"low": "\uAA96", "high": "\uAA97", "name": "BO"},
    "p":   {"low": "\uAA98", "high": "\uAA99", "name": "PO"},
    "ph":  {"low": "\uAA9A", "high": "\uAA9B", "name": "PHO"},
    "f":   {"low": "\uAA9C", "high": "\uAA9D", "name": "FO"},
    "m":   {"low": "\uAA9E", "high": "\uAA9F", "name": "MO"},
    "y":   {"low": "\uAAA0", "high": "\uAAA1", "name": "YO"},
    "r":   {"low": "\uAAA2", "high": "\uAAA3", "name": "RO"},
    "l":   {"low": "\uAAA4", "high": "\uAAA5", "name": "LO"},
    "v":   {"low": "\uAAA6", "high": "\uAAA7", "name": "VO"},
    "h":   {"low": "\uAAA8", "high": "\uAAA9", "name": "HO"},
    "o":   {"low": "\uAAAA", "high": "\uAAAB", "name": "O"},
}

# Tập hợp phụ âm theo tổ
LOW_CONSONANTS: Dict[str, str] = {v["low"]: k for k, v in CONSONANTS.items()}
HIGH_CONSONANTS: Dict[str, str] = {v["high"]: k for k, v in CONSONANTS.items()}
ALL_CONSONANTS: Dict[str, str] = {**LOW_CONSONANTS, **HIGH_CONSONANTS}

# Bảng nguyên âm (Vowels & Final-Combined Vowels)
VOWELS: Dict[str, Dict[str, str]] = {
    "a_short": {"char": "\uAAB0", "latin": "ă/a",  "pos": "above",     "name": "MAI KANG"},
    "aa":      {"char": "\uAAB1", "latin": "a",    "pos": "post",      "name": "AA"},
    "i":       {"char": "\uAAB2", "latin": "i",    "pos": "above",     "name": "I"},
    "ue":      {"char": "\uAAB3", "latin": "ư",    "pos": "above",     "name": "UE"},
    "u":       {"char": "\uAAB4", "latin": "u",    "pos": "below",     "name": "U"},
    "ee":      {"char": "\uAAB5", "latin": "e/ê",  "pos": "pre",       "name": "EE"},
    "o":       {"char": "\uAAB6", "latin": "o/ô",  "pos": "pre",       "name": "O"},
    "khit":    {"char": "\uAAB7", "latin": "i/ư",  "pos": "above",     "name": "MAI KHIT"},
    "ia":      {"char": "\uAAB8", "latin": "ia/iê","pos": "post",      "name": "IA"},
    "uea":     {"char": "\uAAB9", "latin": "ưa/ươ","pos": "post",      "name": "UEA"},
    "ua":      {"char": "\uAABA", "latin": "ua/uô","pos": "post",      "name": "UA"},
    "aue":     {"char": "\uAABB", "latin": "ơ/ơư", "pos": "pre",       "name": "AUE"},
    "ay":      {"char": "\uAABC", "latin": "ay/ai","pos": "pre",       "name": "AY"},
    "an":      {"char": "\uAABD", "latin": "an",   "pos": "post_final","name": "AN"},
    "am":      {"char": "\uAABE", "latin": "am",   "pos": "post_final","name": "AM"},
}

VOWEL_CHARS: Dict[str, str] = {v["char"]: k for k, v in VOWELS.items()}
PRE_BASE_VOWELS: List[str] = [v["char"] for v in VOWELS.values() if v["pos"] == "pre"]

# Dấu thanh (Tone Marks)
TONE_MARKS: Dict[str, Dict[str, str]] = {
    "mai_ek":   {"char": "\uAABF", "alias": "\uAAC0", "name": "TONE MAI EK / MAI NUENG"},
    "mai_tho":  {"char": "\uAAC1", "alias": "\uAAC2", "name": "TONE MAI THO / MAI SONG"},
}

TONE_MARK_CHARS: Dict[str, str] = {
    "\uAABF": "mai_ek",
    "\uAAC0": "mai_ek",   # Biến thể Tai Song/Don
    "\uAAC1": "mai_tho",
    "\uAAC2": "mai_tho",  # Biến thể Tai Song/Don
}

# Ký hiệu đặc biệt và dấu chấm câu
SPECIAL_SYMBOLS: Dict[str, str] = {
    "\uAADB": "KON (Người/Biểu trưng)",
    "\uAADC": "SAM (Dấu lặp từ / Mai Sam)",
    "\uAADD": "HO HOI (Ký hiệu kết thúc đoạn)",
    "\uAADE": "KOI KOI (Ký hiệu kết thúc văn bản)",
}

# Phụ âm cuối hợp lệ (Coda consonants)
VALID_FINALS: List[str] = ["k", "ng", "t", "n", "p", "m", "y", "v", "o"]


# ==============================================================================
# 2. QUY TẮC THANH ĐIỆU (6-TONE SYSTEM RULES)
# ==============================================================================

# Ma trận xác định thanh điệu dựa trên: [Tổ phụ âm đầu] + [Dấu thanh]
# Áp dụng cho âm tiết mở / âm tiết khép với phụ âm vang (Live Syllables)
LIVE_TONE_RULES: Dict[Tuple[str, Optional[str]], int] = {
    ("HIGH", None):      1,  # Thanh 1: Cao lên (Rising / Cầm)
    ("HIGH", "mai_ek"):  2,  # Thanh 2: Cao bằng (High Level / Đợi)
    ("HIGH", "mai_tho"): 3,  # Thanh 3: Cao ngã/sắc gắt (High Falling-Glottal / Tấc)
    ("LOW",  None):      4,  # Thanh 4: Thấp giáng/huyền (Low Falling / Lường)
    ("LOW",  "mai_ek"):  5,  # Thanh 5: Thấp bằng (Low Level / Hạng)
    ("LOW",  "mai_tho"): 6,  # Thanh 6: Thấp ngắt/nặng (Low Rising-Glottal / Nặm)
}

# Áp dụng cho âm tiết khép kết thúc bằng âm tắc -p, -t, -k (Dead / Checked Syllables)
DEAD_TONE_RULES: Dict[Tuple[str, str], int] = {
    ("HIGH", "short"): 7,  # Thanh 7: Tắc cao ngắn (tương đương sắc nhẹ)
    ("HIGH", "long"):  2,  # Thanh 2: Tắc cao dài
    ("LOW",  "short"): 8,  # Thanh 8: Tắc thấp ngắn (tương đương nặng nhẹ)
    ("LOW",  "long"):  5,  # Thanh 5: Tắc thấp dài
}


# ==============================================================================
# 3. HÀM KIỂM TRA VÀ PHÂN TÍCH CHÍNH TẢ (VALIDATION & UTILITIES)
# ==============================================================================

def is_tai_viet(char: str) -> bool:
    """Kiểm tra xem ký tự có thuộc bảng mã Tai Viet hay không."""
    if not char:
        return False
    code = ord(char[0])
    return TAI_VIET_RANGE[0] <= code <= TAI_VIET_RANGE[1]


def get_consonant_tone_class(char: str) -> Optional[str]:
    """Xác định tổ phụ âm: 'HIGH' (Tổ Cao), 'LOW' (Tổ Thấp) hoặc None."""
    if char in HIGH_CONSONANTS:
        return "HIGH"
    if char in LOW_CONSONANTS:
        return "LOW"
    return None


def resolve_tone(
    initial_char: str,
    tone_mark_char: Optional[str] = None,
    is_dead_syllable: bool = False,
    is_long_vowel: bool = True
) -> int:
    """
    Quy tắc giải mã thanh điệu chuẩn chữ Thái Việt (Thanh 1 -> 6 hoặc thanh tắc 7, 8).
    """
    consonant_class = get_consonant_tone_class(initial_char)
    if not consonant_class:
        raise ValueError(f"Ký tự '{initial_char}' không phải là phụ âm Tai Viet hợp lệ.")

    tone_mark_type = TONE_MARK_CHARS.get(tone_mark_char) if tone_mark_char else None

    if not is_dead_syllable:
        return LIVE_TONE_RULES.get((consonant_class, tone_mark_type), 0)
    else:
        vowel_len = "long" if is_long_vowel else "short"
        return DEAD_TONE_RULES.get((consonant_class, vowel_len), 0)


def parse_tai_viet_syllable(syllable_str: str) -> Dict[str, Optional[str]]:
    """
    Phân tích cấu trúc một âm tiết chữ Thái:
    [Nguyên âm trước] + [Phụ âm đầu] + [Nguyên âm trên/dưới/sau] + [Phụ âm cuối] + [Dấu thanh]
    """
    result = {
        "pre_vowel": None,
        "initial": None,
        "nucleus_vowel": None,
        "final": None,
        "tone_mark": None,
        "tone_class": None,
        "raw": syllable_str
    }

    for ch in syllable_str:
        if ch in PRE_BASE_VOWELS:
            result["pre_vowel"] = ch
        elif ch in ALL_CONSONANTS:
            if result["initial"] is None:
                result["initial"] = ch
                result["tone_class"] = get_consonant_tone_class(ch)
            else:
                result["final"] = ch
        elif ch in VOWEL_CHARS:
            result["nucleus_vowel"] = ch
        elif ch in TONE_MARK_CHARS:
            result["tone_mark"] = ch

    return result


def is_valid_orthography(syllable_str: str) -> Tuple[bool, str]:
    """
    Kiểm tra tính hợp lệ về mặt chính tả Tai Viet:
    1. Phải có ít nhất 1 phụ âm đầu.
    2. Không được có nhiều hơn 1 dấu thanh.
    3. Nguyên âm đứng trước (pre-base) phải đặt trước phụ âm đầu theo thứ tự hiển thị chuẩn Unicode.
    """
    parsed = parse_tai_viet_syllable(syllable_str)
    
    if not parsed["initial"]:
        return False, "Thiếu phụ âm đầu."
    
    tone_marks = [c for c in syllable_str if c in TONE_MARK_CHARS]
    if len(tone_marks) > 1:
        return False, "Âm tiết chứa nhiều hơn 1 dấu thanh."

    # Kiểm tra vị trí nguyên âm trước
    if parsed["pre_vowel"]:
        first_char = syllable_str[0]
        if first_char != parsed["pre_vowel"]:
            return False, f"Nguyên âm trước {parsed['pre_vowel']} phải đứng ở đầu âm tiết."

    return True, "Hợp lệ"


# ==============================================================================
# 4. CHÍNH TẢ & PHIÊN MÃ (TEST SUITE TRONG FILE)
# ==============================================================================

if __name__ == "__main__":
    # Ví dụ minh họa: Phân tích âm tiết ꪀꪱ (k + aa = ca) và ꪁꪱ꪿ (k_high + aa + mai_ek)
    sample_syllables = ["ꪀꪱ", "ꪁꪱ꪿", "ꪵꪀ", "ꪀꪰꪚ"]
    print("--- KIỂM TRA BỘ QUY TẮC TAI VIET ---")
    for s in sample_syllables:
        parsed = parse_tai_viet_syllable(s)
        valid, msg = is_valid_orthography(s)
        tone = resolve_tone(parsed["initial"], parsed["tone_mark"]) if parsed["initial"] else None
        print(f"Âm tiết: {s} | Hợp lệ: {valid} ({msg}) | Tổ: {parsed['tone_class']} | Thanh: {tone}")