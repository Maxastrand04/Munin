"""Phrase boosting for the ONNX versions of Klang Pianissimo, on top of onnx-asr.

    model = onnx_asr.load_model("KlangAI/pianissimo-sv-onnx", quantization="int8")
    pianissimo_onnx.boost(model, ["Klang AI", "Pianissimo", "RixVox", "Common Voice"])
"""
import functools
import os
import types

import numpy as np
from onnx_asr.utils import log_softmax

from .phrase_boost import PhraseBoost

TOKENIZER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokenizer.model")


def boost(model, phrases, alpha=1.0, tokenizer_path=TOKENIZER):
    """Boost `phrases` with strength `alpha`; an empty list turns boosting off."""
    asr = model.asr
    if not phrases:
        asr.__dict__.pop("_decoding", None)
        return model
    if asr._blank_idx != asr._vocab_size - 1:
        raise ValueError("expected the blank token to be the last token of the vocabulary")
    tree = PhraseBoost(phrases, tokenizer_path, vocab_size=asr._blank_idx)
    asr._decoding = types.MethodType(functools.partial(_boosted_decoding, tree=tree, alpha=alpha), asr)
    return model


def _boosted_decoding(self, encoder_out, encoder_out_lens, /, *, tree, alpha, **kwargs):
    """onnx-asr's transducer decoding loop with the phrase bonus added."""
    need_logprobs = kwargs.get("need_logprobs")
    for encodings, encodings_len in zip(encoder_out, encoder_out_lens, strict=True):
        prev_state = self._create_state()
        tokens, timestamps, logprobs = [], [], []
        boost_state = 0
        t = 0
        emitted_tokens = 0
        while t < encodings_len:
            logits, step, state = self._decode(tokens, prev_state, encodings[t])
            token = int(logits.argmax())
            if token != self._blank_idx:
                bonus, next_states = tree.scores(boost_state)
                token = int(np.argmax(logits[: self._blank_idx] + alpha * bonus))
                boost_state = int(next_states[token])
                prev_state = state
                tokens.append(token)
                timestamps.append(t)
                emitted_tokens += 1
                if need_logprobs:
                    logprobs.append(log_softmax(logits)[token])
            if step > 0:
                t += step
                emitted_tokens = 0
            elif token == self._blank_idx or emitted_tokens == self._max_tokens_per_step:
                t += 1
                emitted_tokens = 0
        yield tokens, timestamps, logprobs if need_logprobs else None
