import re


def split_sentences(
    text: str,
    min_sentence_len: int = 20,
    max_sentence_len: int = 256,
    sentence_cutoff_symbol: str = "--",
) -> tuple[list[str], str]:
    """Splits text into complete sentences and a partial sentence.
    Returns (complete_sentences, partial_sentence).
    Sentences longer than max_sentence_len are truncated with sentence_cutoff_symbol."""
    alphabets = r"([A-Za-z])"
    prefixes = r"(Mr|St|Mrs|Ms|Dr)[.]"
    suffixes = r"(Inc|Ltd|Jr|Sr|Co)"
    starters = r"(Mr|Mrs|Ms|Dr|Prof|Capt|Cpt|Lt|He\s|She\s|It\s|They\s|Their\s|Our\s|We\s|But\s|However\s|That\s|This\s|Wherever)"
    acronyms = r"([A-Z][.][A-Z][.](?:[A-Z][.])?)"
    websites = r"[.](com|net|org|io|gov|edu|me)"
    digits = r"([0-9])"
    multiple_dots = r"\.{2,}"

    # fmt: off
    text = " " + text + "  "
    text = text.replace("\n"," ")
    text = re.sub(prefixes,"\\1<prd>",text)
    text = re.sub(websites,"<prd>\\1",text)
    text = re.sub(digits + "[.]" + digits,"\\1<prd>\\2",text)
    text = re.sub(multiple_dots, lambda match: "<prd>" * len(match.group(0)), text)
    if "Ph.D" in text:
        text = text.replace("Ph.D.","Ph<prd>D<prd>")
    text = re.sub(r"\s" + alphabets + "[.] "," \\1<prd> ",text)
    text = re.sub(acronyms+" "+starters,"\\1<stop> \\2",text)
    text = re.sub(alphabets + "[.]" + alphabets + "[.]" + alphabets + "[.]","\\1<prd>\\2<prd>\\3<prd>",text)
    text = re.sub(alphabets + "[.]" + alphabets + "[.]","\\1<prd>\\2<prd>",text)
    text = re.sub(r" "+suffixes+"[.] "+starters," \\1<stop> \\2",text)
    text = re.sub(r" "+suffixes+"[.]"," \\1<prd>",text)
    text = re.sub(r" " + alphabets + "[.]"," \\1<prd>",text)
    if "”" in text:
        text = text.replace(".”","”.")
    if "\"" in text:
        text = text.replace(".\"","\".")
    if "!" in text:
        text = text.replace("!\"","\"!")
    if "?" in text:
        text = text.replace("?\"","\"?")
    text = text.replace(".",".<stop>")
    text = text.replace("?","?<stop>")
    text = text.replace("!","!<stop>")
    text = text.replace("<prd>",".")
    sentences = text.split("<stop>")
    sentences = [s.strip() for s in sentences]
    if sentences and not sentences[-1]:
        sentences = sentences[:-1]
    # fmt: on

    complete_sentences = []
    buff = ""
    for sentence in sentences:
        buff += " " + sentence
        # Check if buff exceeds max_sentence_len
        while len(buff) > max_sentence_len:
            # Find the last space before max_sentence_len
            cutoff_point = buff.rfind(" ", 0, max_sentence_len)
            if cutoff_point == -1:  # No space found, force cut at max_sentence_len
                cutoff_point = max_sentence_len - len(sentence_cutoff_symbol)
            truncated_sentence = buff[1:cutoff_point].strip() + sentence_cutoff_symbol
            if len(
                truncated_sentence
            ) >= min_sentence_len and truncated_sentence.endswith((".", "?", "!")):
                complete_sentences.append(truncated_sentence)
            buff = " " + buff[cutoff_point:].strip()

        # Check if buff is a complete sentence within bounds
        if len(buff) > min_sentence_len and buff.strip().endswith((".", "?", "!")):
            complete_sentences.append(buff[1:])
            buff = ""

    # Handle the leftover buff
    partial_sentence = buff[1:].strip() if buff else ""
    if partial_sentence and partial_sentence.endswith((".", "?", "!")):
        if len(partial_sentence) <= max_sentence_len:
            complete_sentences.append(partial_sentence)
        else:
            # Truncate partial_sentence if it exceeds max_sentence_len
            cutoff_point = partial_sentence.rfind(" ", 0, max_sentence_len)
            if cutoff_point == -1:
                cutoff_point = max_sentence_len - len(sentence_cutoff_symbol)
            truncated_sentence = (
                partial_sentence[:cutoff_point].strip() + sentence_cutoff_symbol
            )
            if len(truncated_sentence) >= min_sentence_len:
                complete_sentences.append(truncated_sentence)
            partial_sentence = partial_sentence[cutoff_point:].strip()
        partial_sentence = (
            "" if partial_sentence.endswith((".", "?", "!")) else partial_sentence
        )

    return complete_sentences, partial_sentence


def tokenize(text: str, tokenizer) -> list[int]:
    tokens = tokenizer(text, return_tensors="pt").input_ids[0].tolist()
    return tokens
