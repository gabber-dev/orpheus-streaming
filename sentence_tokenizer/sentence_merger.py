import re
import logging
from .utils import get_tag_name


# vibe coded slop...
def merge_sentences(content: str) -> str:
    if not content:
        return ""

    # Split content into tags and text parts
    parts = re.split(r"(<\s*\/?\s*[a-zA-Z]+\s*>)", content)
    # Filter out empty strings and strip whitespace
    parts = [part.strip() for part in parts if part.strip()]

    if not parts:
        return ""

    result = []
    current_tag_name: str | None = None
    current_content = []
    i = 0

    while i < len(parts):
        part = parts[i]

        # Check if this is a tag
        if part.startswith("<"):
            # Opening tag
            if not part.startswith("</"):
                tag_name = get_tag_name(part)

                # If we have accumulated untagged content, add it
                if current_content and not current_tag_name:
                    result.append(" ".join(current_content))
                    current_content = []

                # If we have content with same tag
                if current_tag_name == tag_name and current_content:
                    # Look ahead for content and closing tag
                    if (
                        i + 1 < len(parts)
                        and i + 2 < len(parts)
                        and parts[i + 2] == f"</{tag_name}>"
                    ):
                        current_content.append(parts[i + 1])
                        i += 3
                        continue

                # If we have content with different tag
                if (
                    current_content
                    and current_tag_name
                    and current_tag_name != tag_name
                ):
                    logging.warning(
                        f"Mismatched tags: {current_tag_name} and {tag_name}, using {current_tag_name}"
                    )
                    result.append(
                        f"<{current_tag_name}>{' '.join(current_content)}</{current_tag_name}>"
                    )
                    current_content = []

                # Start new tagged content
                current_tag_name = tag_name
                if (
                    i + 1 < len(parts)
                    and i + 2 < len(parts)
                    and parts[i + 2] == f"</{tag_name}>"
                ):
                    current_content = [parts[i + 1]]
                    i += 3
                else:
                    result.append(part)
                    i += 1
            else:
                # Unexpected closing tag
                if not current_tag_name:
                    result.append(part)
                i += 1
        else:
            # Plain text
            if current_content and current_tag_name:
                result.append(
                    f"<{current_tag_name}>{' '.join(current_content)}</{current_tag_name}>"
                )
                current_tag_name = None
                current_content = [part]
            elif current_content and not current_tag_name:
                current_content.append(part)
            else:
                current_content = [part]
            i += 1

    # Handle remaining content
    if current_content:
        if current_tag_name:
            result.append(
                f"<{current_tag_name}>{' '.join(current_content)}</{current_tag_name}>"
            )
        else:
            result.append(" ".join(current_content))

    # Join results without spaces between adjacent tags
    final_result = ""
    for j, part in enumerate(result):
        if j > 0:
            # If previous part ends with > and current starts with <, no space
            if result[j - 1].endswith(">") and part.startswith("<"):
                final_result += part
            else:
                final_result += " " + part
        else:
            final_result = part

    return final_result
