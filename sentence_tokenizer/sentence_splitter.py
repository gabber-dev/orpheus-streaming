from nltk.tokenize import sent_tokenize
import re
from dataclasses import dataclass
import logging
from .utils import get_tag_name


class SentenceSplitter:
    def __init__(self):
        self._buffer = ""  # Holds all incoming text

    def push(self, chunk):
        self._buffer += chunk
        parts = re.split(r"(<\s*\/?\s*[a-zA-Z]+\s*>)", self._buffer)

        tags: list[RunningTag] = []
        sentences = []

        running_tag = RunningTag(tag=None, content="")
        tags.append(running_tag)
        print("parts", parts)
        for i in range(len(parts)):
            part = parts[i]
            if part == "":
                continue
            if part.startswith("<") and not part.startswith("</"):
                running_tag = RunningTag(tag=get_tag_name(part), content="")
                tags.append(running_tag)
            elif part.startswith("</"):
                tag_name = get_tag_name(part)
                if running_tag.tag != tag_name:
                    logging.warning(
                        f"Closing tag {tag_name} does not match opening tag {running_tag.tag}"
                    )
                running_tag = RunningTag(tag=None, content="")
                tags.append(running_tag)
            else:
                running_tag.content = part

        for t in tags[:-1]:
            tokenized = sent_tokenize(t.content)
            for sentence in tokenized:
                if t.tag:
                    sentences.append(f"<{t.tag}>{sentence}</{t.tag}>")
                else:
                    sentences.append(sentence)

        if len(tags) == 0:
            return sentences

        last_running_tag = tags[-1]
        if last_running_tag.tag:
            tokenized = sent_tokenize(last_running_tag.content)
            for sentence in tokenized[:-1]:
                sentences.append(
                    f"<{last_running_tag.tag}>{sentence.strip()}</{last_running_tag.tag}>"
                )

            if len(tokenized) > 0:
                self._buffer = f"<{last_running_tag.tag}>{tokenized[-1]}"
            else:
                self._buffer = f"<{last_running_tag.tag}>"
        else:
            tokenized = sent_tokenize(last_running_tag.content)
            for sentence in tokenized[:-1]:
                sentences.append(sentence.strip())

            if len(tokenized) > 0:
                self._buffer = tokenized[-1]
            else:
                self._buffer = ""

        return sentences

    def eos(self):
        sentences = self.push("<eos>")
        self._buffer = ""
        return sentences


@dataclass
class RunningTag:
    tag: str | None
    content: str
