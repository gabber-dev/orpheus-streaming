from transformers import PreTrainedTokenizerBase
import logging
from typing import Tuple
from .constants import START_TOKEN, END_TOKENS
from sentence_tokenizer import SentenceSplitter, merge_sentences
from dataclasses import dataclass


class PromptWindow:
    def __init__(
        self,
        tokenizer: PreTrainedTokenizerBase,
        max_context_text_tokens: int,
        voice: str | None,
        previous_audio_tokens: int,
    ):
        self._previous_audio: list[int] = []
        self._prompt = []
        self._tokenizer: PreTrainedTokenizerBase = tokenizer
        self._sentence_splitter = SentenceSplitter()
        self._sentences: list[str] = []
        self._voice = voice
        self._max_context_text_tokens = max_context_text_tokens
        self._inference_queue = list[Tuple[str, list[int]]]()
        self._previous_text = ""
        self._previous_audio_tokens = previous_audio_tokens

    def push_text(self, text: str):
        new_sentences = self._sentence_splitter.push(text)
        self._sentences.extend(new_sentences)

    def eos(self):
        new_sentences = self._sentence_splitter.eos()
        print("NEIL prompt window eos", self._sentences, new_sentences)
        self._sentences.extend(new_sentences)

    def push_previous_inference(self, input_text: str, audio: list[int]):
        self._previous_text = input_text
        self._previous_audio = audio

    def get_next_inference(self) -> "PromptWindowInference | None":
        sentences = self._sentences.copy()
        if len(sentences) == 0:
            return None

        new_complete_sentence_text = " ".join(sentences)
        tokens = (
            self._tokenizer(
                self._previous_text + new_complete_sentence_text, return_tensors="pt"
            )
            .input_ids[0]
            .tolist()
        )

        unused_sentences = []
        while len(tokens) > self._max_context_text_tokens:
            if len(sentences) > 1:
                s = sentences.pop()  # Remove last sentence
                unused_sentences.insert(0, s)
                new_complete_sentence_text = " ".join(sentences)
                context_text = ""
                tokens = (
                    self._tokenizer(
                        context_text + new_complete_sentence_text, return_tensors="pt"
                    )
                    .input_ids[0]
                    .tolist()
                )
            else:
                break

        merged = merge_sentences(new_complete_sentence_text)
        logging.info(
            f"Prompt window inference context text: {self._previous_text}, new text: {new_complete_sentence_text}"
        )
        self._sentences = unused_sentences
        return PromptWindowInference(
            context_text=self._previous_text,
            context_audio=self._previous_audio,
            new_text=merged,
            tokenizer=self._tokenizer,
            voice=self._voice,
        )


@dataclass
class PromptWindowInference:
    def __init__(
        self,
        *,
        context_text: str,
        context_audio: list[int],
        new_text: str,
        voice: str | None,
        tokenizer: PreTrainedTokenizerBase,
    ):
        self.context_text = context_text
        self.context_audio = context_audio
        self.new_text = new_text
        self.voice = voice
        self.tokenizer = tokenizer

    def tokenize(self) -> list[int]:
        context_text_prompt = self.context_text
        new_text_prompt = self.new_text
        if self.voice is not None:
            context_text_prompt = f"{self.voice}: {self.context_text}"
            new_text_prompt = f"{self.voice}: {self.new_text}"

        context_text_tokens: list[int] = []
        if self.context_text != "":
            context_text_tokens = (
                self.tokenizer(context_text_prompt, return_tensors="pt")
                .input_ids[0]
                .tolist()
            )
        new_text_tokens = (
            self.tokenizer(new_text_prompt, return_tensors="pt").input_ids[0].tolist()
        )

        full_tokens: list[int] = (
            [START_TOKEN]
            + context_text_tokens
            + END_TOKENS
            + self.context_audio
            + [START_TOKEN]
            + new_text_tokens
            + END_TOKENS
        )

        return full_tokens
