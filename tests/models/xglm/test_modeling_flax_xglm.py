# Copyright 2021 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import unittest

from transformers import XGLMConfig, XGLMTokenizer, is_flax_available
from transformers.testing_utils import require_flax, require_sentencepiece, slow

from ...test_modeling_flax_common import FlaxModelTesterMixin, ids_tensor, random_attention_mask


if is_flax_available():
    import jax
    import jax.numpy as jnp
    import numpy as np

    from transformers.models.xglm.modeling_flax_xglm import FlaxXGLMForCausalLM, FlaxXGLMModel


@require_flax
class FlaxXGLMModelTester:
    def __init__(
        self,
        parent,
        batch_size=14,
        seq_length=7,
        is_training=True,
        use_input_mask=True,
        use_labels=True,
        vocab_size=99,
        d_model=32,
        num_hidden_layers=2,
        num_attention_heads=4,
        ffn_dim=37,
        activation_function="gelu",
        activation_dropout=0.1,
        attention_dropout=0.1,
        max_position_embeddings=512,
        initializer_range=0.02,
        scope=None,
    ):
        self.parent = parent
        self.batch_size = batch_size
        self.seq_length = seq_length
        self.is_training = is_training
        self.use_input_mask = use_input_mask
        self.use_labels = use_labels
        self.vocab_size = vocab_size
        self.hidden_size = d_model
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.ffn_dim = ffn_dim
        self.activation_function = activation_function
        self.activation_dropout = activation_dropout
        self.attention_dropout = attention_dropout
        self.max_position_embeddings = max_position_embeddings
        self.initializer_range = initializer_range
        self.scope = None
        self.bos_token_id = 0
        self.eos_token_id = 2
        self.pad_token_id = 1

    def prepare_config_and_inputs(self):
        input_ids = np.clip(ids_tensor([self.batch_size, self.seq_length], self.vocab_size), 3, self.vocab_size)

        input_mask = None
        if self.use_input_mask:
            input_mask = random_attention_mask([self.batch_size, self.seq_length])

        config = XGLMConfig(
            vocab_size=self.vocab_size,
            d_model=self.hidden_size,
            num_layers=self.num_hidden_layers,
            attention_heads=self.num_attention_heads,
            ffn_dim=self.ffn_dim,
            activation_function=self.activation_function,
            activation_dropout=self.activation_dropout,
            attention_dropout=self.attention_dropout,
            max_position_embeddings=self.max_position_embeddings,
            initializer_range=self.initializer_range,
            use_cache=True,
            bos_token_id=self.bos_token_id,
            eos_token_id=self.eos_token_id,
            pad_token_id=self.pad_token_id,
        )

        return (config, input_ids, input_mask)

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()
        config, input_ids, attention_mask = config_and_inputs
        inputs_dict = {"input_ids": input_ids, "attention_mask": attention_mask}
        return config, inputs_dict

    def check_use_cache_forward(self, model_class_name, config, input_ids, attention_mask):
        max_decoder_length = 20
        model = model_class_name(config)

        past_key_values = model.init_cache(input_ids.shape[0], max_decoder_length)
        attention_mask = jnp.ones((input_ids.shape[0], max_decoder_length), dtype="i4")

        position_ids = jnp.broadcast_to(
            jnp.arange(input_ids.shape[-1] - 1)[None, :], (input_ids.shape[0], input_ids.shape[-1] - 1)
        )
        outputs_cache = model(
            input_ids[:, :-1],
            attention_mask=attention_mask,
            past_key_values=past_key_values,
            position_ids=position_ids,
        )

        position_ids = jnp.array(input_ids.shape[0] * [[input_ids.shape[-1] - 1]], dtype="i4")
        outputs_cache_next = model(
            input_ids[:, -1:],
            attention_mask=attention_mask,
            past_key_values=outputs_cache.past_key_values,
            position_ids=position_ids,
        )

        outputs = model(input_ids)

        diff = np.max(np.abs(outputs_cache_next[0][:, -1, :5] - outputs[0][:, -1, :5]))
        self.parent.assertTrue(diff < 1e-3, msg=f"Max diff is {diff}")

    def check_use_cache_forward_with_attn_mask(self, model_class_name, config, input_ids, attention_mask):
        max_decoder_length = 20
        model = model_class_name(config)

        attention_mask_cache = jnp.concatenate(
            [attention_mask, jnp.zeros((attention_mask.shape[0], max_decoder_length - attention_mask.shape[1]))],
            axis=-1,
        )

        past_key_values = model.init_cache(input_ids.shape[0], max_decoder_length)
        position_ids = jnp.broadcast_to(
            jnp.arange(input_ids.shape[-1] - 1)[None, :], (input_ids.shape[0], input_ids.shape[-1] - 1)
        )

        outputs_cache = model(
            input_ids[:, :-1],
            attention_mask=attention_mask_cache,
            past_key_values=past_key_values,
            position_ids=position_ids,
        )
        position_ids = jnp.array(input_ids.shape[0] * [[input_ids.shape[-1] - 1]], dtype="i4")
        outputs_cache_next = model(
            input_ids[:, -1:],
            past_key_values=outputs_cache.past_key_values,
            attention_mask=attention_mask_cache,
            position_ids=position_ids,
        )

        outputs = model(input_ids, attention_mask=attention_mask)
        diff = np.max(np.abs(outputs_cache_next[0][:, -1, :5] - outputs[0][:, -1, :5]))
        self.parent.assertTrue(diff < 1e-3, msg=f"Max diff is {diff}")


@require_sentencepiece
@require_flax
class FlaxXGLMModelTest(FlaxModelTesterMixin, unittest.TestCase):
    all_model_classes = (FlaxXGLMModel, FlaxXGLMForCausalLM) if is_flax_available() else ()

    def setUp(self):
        self.model_tester = FlaxXGLMModelTester(self)

    def test_use_cache_forward(self):
        for model_class_name in self.all_model_classes:
            config, input_ids, attention_mask = self.model_tester.prepare_config_and_inputs()
            self.model_tester.check_use_cache_forward(model_class_name, config, input_ids, attention_mask)

    def test_use_cache_forward_with_attn_mask(self):
        for model_class_name in self.all_model_classes:
            config, input_ids, attention_mask = self.model_tester.prepare_config_and_inputs()
            self.model_tester.check_use_cache_forward_with_attn_mask(
                model_class_name, config, input_ids, attention_mask
            )

    @slow
    def test_batch_generation(self):
        tokenizer = XGLMTokenizer.from_pretrained("XGLM", padding_side="left")
        inputs = tokenizer(["Hello this is a long string", "Hey"], return_tensors="np", padding=True, truncation=True)

        model = FlaxXGLMForCausalLM.from_pretrained("facebook/xglm-564M")
        model.config.num_beams = 1
        model.config.do_sample = False

        jit_generate = jax.jit(model.generate)

        output_sequences = jit_generate(inputs["input_ids"], attention_mask=inputs["attention_mask"]).sequences

        output_string = tokenizer.batch_decode(output_sequences, skip_special_tokens=True)

        expected_string = [
            "Hello this is a long string of questions, but I'm not sure if I'm",
            "Hey, I'm a newbie to the forum and I'",
        ]

        self.assertListEqual(output_string, expected_string)

    @slow
    def test_model_from_pretrained(self):
        for model_class_name in self.all_model_classes:
            model = model_class_name.from_pretrained("facebook/xglm-564M")
            outputs = model(np.ones((1, 1)))
            self.assertIsNotNone(outputs)
