import asyncio
import pytest
from sentence_tokenizer import SentenceSplitter, merge_sentences


@pytest.mark.asyncio
async def test_session_cleanup():
    splitter = SentenceSplitter()

    sentences = splitter.push("Hello world")
    assert len(sentences) == 0
    sentences = splitter.push(" this is a test.")
    assert len(sentences) == 0
    sentences = splitter.push(" <happy>Feeling good!")
    assert sentences[0] == "Hello world this is a test."
    sentences = splitter.push(" Still happy. So happy to be here. </happy>")
    assert sentences[0] == "<happy>Feeling good!</happy>"
    assert sentences[1] == "<happy>Still happy.</happy>"
    assert sentences[2] == "<happy>So happy to be here.</happy>"
    splitter.push("<foo>partial sentence")
    sentences = splitter.eos()
    assert sentences[0] == "<foo>partial sentence</foo>"


@pytest.mark.asyncio
async def test_merging():
    res = merge_sentences("<happy>hello</happy><happy>yo</happy>")
    assert res == "<happy>hello yo</happy>"

    res = merge_sentences("<happy>hello</happy> <happy>yo</happy>")
    assert res == "<happy>hello yo</happy>"
    res = merge_sentences("hello <happy>world</happy>")
    assert res == "hello <happy>world</happy>"
    res = merge_sentences("<happy>hello</happy><sad>yo</sad>")
    assert res == "<happy>hello</happy><sad>yo</sad>"
    res = merge_sentences("plain text here")

    assert res == "plain text here"
    res = merge_sentences("<happy>hello</happy> between <happy>world</happy>")
    assert res == "<happy>hello</happy> between <happy>world</happy>"
