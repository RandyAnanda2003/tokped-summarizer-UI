
from fastapi import HTTPException
from scrapper import scrape_all_reviews
from converter import get_product_id
import emoji
import re

def validate_tokopedia_url(url: str):
    if "tokopedia.com" not in url:
        raise HTTPException(
            status_code=400,
            detail="URL harus dari Tokopedia"
        )
def remove_gibberish(text, min_word_len=5, max_repeat_ratio=0.6):
        if not isinstance(text, str):
            return ""

        words = text.split()
        clean_words = []

        for w in words:
            # hapus simbol
            word = re.sub(r'[^a-zA-Z]', '', w.lower())

            if len(word) < min_word_len:
                clean_words.append(w)
                continue

            # hitung rasio karakter unik
            unique_ratio = len(set(word)) / len(word)

            # kalau karakter unik terlalu sedikit → noise
            if unique_ratio < (1 - max_repeat_ratio):
                continue

            # cek ada vokal atau tidak
            if not re.search(r'[aiueo]', word):
                continue

            clean_words.append(w)

        return " ".join(clean_words)

def remove_repeated_phrases(text, min_phrase_len=2):
        words = text.split()
        n = len(words)

        result = []
        i = 0

        while i < n:
            found = False

            for size in range(min_phrase_len, (n - i) // 2 + 1):
                phrase = words[i:i + size]

                repeat = 1
                while words[i + size * repeat:i + size * (repeat + 1)] == phrase:
                    repeat += 1

                if repeat > 1:
                    result.extend(phrase)
                    i += size * repeat
                    found = True
                    break

            if not found:
                result.append(words[i])
                i += 1

        return " ".join(result)

def clean_review_text(text):
        if not isinstance(text, str):
            return ""

        # 1. lowercase
        text = text.lower()

        # 2. hapus emoji
        text = emoji.replace_emoji(text, replace="")

        # 3. hapus emoticon
        emot_pattern = r"""
            (?:
                [:=;][oO\-]?[D\)\]\(\]/\\OpP] |
                [D\)\]\(\]/\\OpP][oO\-]?[=:;] |
                <3 |
                t_t |
                x_x |
                xd
            )
        """
        text = re.sub(emot_pattern, "", text, flags=re.VERBOSE | re.IGNORECASE)

        # 4. hapus ketawa
        laughter_pattern = r'\b(?:ha|he|hi|ho|hu|wk|kw){2,}\b'
        text = re.sub(laughter_pattern, ' ', text)

        # 5. keyboard smash
        random_word_pattern = r'\b[bcdfghjklmnpqrstvwxyz]{6,}\b'
        text = re.sub(random_word_pattern, ' ', text)

        # 6. karakter berlebih
        text = re.sub(r'(.)\1{2,}', r'\1', text)

        # 7. kata nempel
        text = re.sub(r'\b(\w{2,})\1+\b', r'\1', text)

        # 8. hapus titik
        text = text.replace('.', ' ')

        # 9. simbol
        text = re.sub(r'[^a-z\s]', ' ', text)

        # 10. karakter tunggal
        text = re.sub(r'\b[a-z]\b', ' ', text)

        # 11. kata berulang
        text = re.sub(r'\b(\w+)\b(\s+\1){2,}', r'\1', text)

        # 11a. frasa berulang atau kata tak beraturan
        text = remove_repeated_phrases(text)
        text = remove_gibberish(text)

        # 12. rapikan spasi
        text = re.sub(r'\s+', ' ', text).strip()

        return text

def scrap_40_reviews_tokopedia (url:str) -> str :
    url = url
    product_id = get_product_id(url)
    graph_id = product_id["product_id"]
    reviews = scrape_all_reviews(graph_id,max_reviews=70)
    if reviews is None or len(reviews) < 5 :
        raise HTTPException(
            status_code=500,
            detail="tidak terdapat review atau jumlah review kurang dari 5"
        )
    reviews_parsed = list ([r['message'] for r in reviews])
    
    seen = set()
    result = []

    for r in reviews_parsed:
        if not r:
            continue

        cleaned = clean_review_text(r)

        if cleaned and cleaned not in seen :
            seen.add(cleaned)
            result.append(cleaned)
        if result and len(result) == 40 :
            break
        
    # ===============================
    # 5. JOIN DENGAN TITIK
    # ===============================
    if result : 
        joined_text = ". ".join(result) + "."
    else :
        joined_text = ""

    return {
        "total_reviews": len(result),
        "joined_text": joined_text
    }
    


