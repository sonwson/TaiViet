TAI_VIET_RULES = {
    # 1. PHỤ ÂM (CONSONANTS): Chia theo cặp Tổ Thấp (Suffix -ò) và Tổ Cao (Suffix -ō)
    "consonants": {
        # Nhóm K
        "ꪀ": {"ipa": "k", "group": "low", "name": "kò"},
        "ꪁ": {"ipa": "k", "group": "high", "name": "kō"},
        "ꪂ": {"ipa": "khh", "group": "low", "name": "khhò"},
        "ꪃ": {"ipa": "khh", "group": "high", "name": "khhō"},
        "ꪄ": {"ipa": "kh", "group": "low", "name": "khò"},
        "ꪅ": {"ipa": "kh", "group": "high", "name": "khō"},
        
        # Nhóm NG, CH, CHH
        "ꪆ": {"ipa": "g", "group": "low", "name": "gò"},
        "ꪇ": {"ipa": "g", "group": "high", "name": "gō"},
        "ꪈ": {"ipa": "ng", "group": "low", "name": "ngò"},
        "ꪉ": {"ipa": "ng", "group": "high", "name": "ngō"},
        "ꪊ": {"ipa": "ch", "group": "low", "name": "chò"},
        "ꪋ": {"ipa": "ch", "group": "high", "name": "chō"},
        "ꪌ": {"ipa": "chh", "group": "low", "name": "chhò"},
        "ꪍ": {"ipa": "chh", "group": "high", "name": "chhō"},
        
        # Nhóm NH, Đ, T, TH, S
        "ꪎ": {"ipa": "s", "group": "low", "name": "sò"},
        "ꪏ": {"ipa": "s", "group": "high", "name": "sō"},
        "ꪐ": {"ipa": "nh", "group": "low", "name": "nhò"},
        "ꪑ": {"ipa": "nh", "group": "high", "name": "nhō"},
        "ꪒ": {"ipa": "đ", "group": "low", "name": "đò"},
        "ꪓ": {"ipa": "đ", "group": "high", "name": "đō"},
        "ꪔ": {"ipa": "t", "group": "low", "name": "tò"},
        "ꪕ": {"ipa": "t", "group": "high", "name": "tō"},
        "ꪖ": {"ipa": "th", "group": "low", "name": "thò"},
        "ꪗ": {"ipa": "th", "group": "high", "name": "thō"},
        
        # Nhóm B, P, PH, F, N
        "ꪘ": {"ipa": "n", "group": "low", "name": "nò"},
        "ꪙ": {"ipa": "n", "group": "high", "name": "nō"},
        "ꪚ": {"ipa": "b", "group": "low", "name": "bò"},
        "ꪛ": {"ipa": "b", "group": "high", "name": "bō"},
        "ꪜ": {"ipa": "p", "group": "low", "name": "pò"},
        "ꪝ": {"ipa": "p", "group": "high", "name": "pō"},
        "ꪞ": {"ipa": "fh", "group": "low", "name": "fhò"},
        "ꪟ": {"ipa": "fh", "group": "high", "name": "fhō"},
        "ꪠ": {"ipa": "ph", "group": "low", "name": "phò"},
        "ꪡ": {"ipa": "ph", "group": "high", "name": "phō"},
        
        # Nhóm L, V, H, O
        "ꪢ": {"ipa": "m", "group": "low", "name": "m   ò"},
        "ꪣ": {"ipa": "m", "group": "high", "name": "mō"},
        "ꪤ": {"ipa": "d", "group": "low", "name": "dò"},
        "ꪥ": {"ipa": "d", "group": "high", "name": "dō"},
        "ꪦ": {"ipa": "r", "group": "low", "name": "rò"},
        "ꪧ": {"ipa": "r", "group": "high", "name": "rō"},
        "ꪨ": {"ipa": "l", "group": "low", "name": "lò"},
        "ꪩ": {"ipa": "l", "group": "high", "name": "lō"},      
        "ꪪ": {"ipa": "v", "group": "low", "name": "vò"},
        "ꪫ": {"ipa": "v", "group": "high", "name": "vō"},
        "ꪬ": {"ipa": "h", "group": "low", "name": "hò"},
        "ꪭ": {"ipa": "h", "group": "high", "name": "hō"},
        "ꪮ": {"ipa": "o", "group": "low", "name": "oò"},
        "ꪯ": {"ipa": "o", "group": "high", "name": "oō"},
    },

    # 2. NGUYÊN ÂM (VOWELS): Quan trọng nhất là vị trí (Position) so với phụ âm
    "vowels": {
        "ꪱ": {"ipa": "a", "pos": "right"},
        "ꪰ": {"ipa": "ă", "pos": "above"},
        "ꪲ": {"ipa": "i", "pos": "above"},
        "ꪳ": {"ipa": "ư", "pos": "above"},
        "ꪴ": {"ipa": "u", "pos": "below"},
        "ꪵ": {"ipa": "e", "pos": "left"},
        "ꪶ": {"ipa": "ô", "pos": "left"},
        "ꪷ": {"ipa": "o", "pos": "above"},
        "ꪸ": {"ipa": "ia/iê", "pos": "above"},
        "ꪹ": {"ipa": "ưa/ươ", "pos": "left"},
        "ꪺ": {"ipa": "ua/uô", "pos": "above"},
        "ꪻ": {"ipa": "aư", "pos": "left"},
        "ꪼ": {"ipa": "ay", "pos": "left"},
        "ꪽ": {"ipa": "ăn", "pos": "right"},
        "ꪾ": {"ipa": "ăm", "pos": "above"},
        "꪿": {"ipa": "au", "pos": "left"}, # Dấu ꪿ kết hợp vị trí trái
    },

    # 3. DẤU THANH (TONE MARKS): Kết hợp với Tổ Cao/Thấp để ra 8 thanh
    "tones": {
        "꪿": {"name": "mài siềng 1", "role": "thanh_2_hoặc_5"},
        "꫁": {"name": "mài siềng 2", "role": "thanh_3_hoặc_6"},
    },

    # 4. KÝ TỰ ĐẶC BIỆT & SỐ (SPECIAL SYMBOLS)
    "specials": {
        "ꫀ": "nưng (số 1)",
        "ꫛ": "kồn (người)",
        "ꫜ": "lãi sặm (dấu lặp)",
        "꫞": "hō hỡi (mở đầu bài hát)",
        "꫟": "chāo hỡi (kết thúc)",
    }
}
