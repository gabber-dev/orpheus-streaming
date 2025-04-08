import re


def get_tag_name(tag):
    # Match either <tag> or </tag> and capture the tag name
    match = re.match(r"<\s*/?\s*([a-zA-Z]+)\s*>", tag)
    if match:
        return match.group(1)  # Return the captured tag name
    return None
