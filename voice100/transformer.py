# Copyright 2020 Katsuya Iida. All rights reserved.

import torch
from torch import nn
from torch.nn import init
import numpy as np
import math

__all__ = ["Transformer"]

_NEG_INF_FP32 = -1e9
_NEG_INF_FP16 = np.finfo(np.float16).min

# Variables

variable_space = ''
trainable_variables = {}
regsitered_modules = {}

class _VariableScope:
    def __init__(self, name):
        self.name = name
    def __enter__(self):
        global variable_space
        self.parent = variable_space
        if variable_space:
            variable_space += '/' + self.name
        else:
            variable_space = self.name
    def __exit__(self, a, b, c):
        global variable_space
        variable_space = self.parent

def variable_scope(name):
    return _VariableScope(name)

def has_current_module():
    return variable_space in regsitered_modules

def set_current_module(m):
    regsitered_modules[variable_space] = m

def current_module():
    return regsitered_modules[variable_space]

def get_variable(name):
    return trainable_variables[variable_space + '/' + name]

def set_variable(name, value):
    trainable_variables[variable_space + '/' + name] = value

def set_variables(vars):
    global trainable_variables
    trainable_variables = {
        k: torch.nn.Parameter(torch.tensor(v, dtype=torch.float32), requires_grad=False)
        for k, v in vars.items()
    }

def list_variables():
    return [
        (k, v.shape)
        for k, v in trainable_variables.items()
    ]

# Misc

def load_numpy_state_layer_norm(layer):
    with variable_scope('layer_normalization'):
        layer.weight.copy_(get_variable('gamma'))
        layer.bias.copy_(get_variable('beta'))

class EinsumLinear(nn.Module):
    def __init__(self, subscripts: str, in_shape, out_shape, use_bias=False,
        device=None, dtype=None) -> None:
        factory_kwargs = {'device': device, 'dtype': dtype}
        super().__init__()
        self.subscripts = subscripts
        self.in_shape = in_shape
        self.out_shape = out_shape
        self.use_bias = use_bias
        self.weight = nn.Parameter(torch.empty(in_shape + out_shape, **factory_kwargs))
        if use_bias:
            self.bias = nn.Parameter(torch.empty(out_shape, **factory_kwargs))
        else:
            self.bias = None
        self.reset_parameters()

    def _calc_fan_in_out(self, gain):
        fan_in = 1
        for x in self.in_shape: fan_in *= x
        fan_out = 1
        for x in self.out_shape: fan_out *= x
        return gain * math.sqrt(6 / (fan_in + fan_out))

    def reset_parameters(self) -> None:
        a = self._calc_fan_in_out(math.sqrt(2))
        nn.init.normal_(self.weight, mean=0, std=a)
        if self.use_bias:
            nn.init.normal_(self.bias, mean=0, std=a)

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        y = torch.einsum(self.subscripts, input, self.weight)
        if self.bias is not None:
            y += self.bias
        return y

def load_numpy_state_dense_layer(name, layer):
    with variable_scope(name):
        layer.weight.copy_(get_variable('kernel'))
        if layer.bias is not None:
            layer.bias.copy_(get_variable('bias'))

# Transformer layers

class EmbeddingSharedWeights(nn.Module):
    __constants__ = ['vocab_size', 'hidden_size']
    voacb_size: int
    hidden_size: int

    def __init__(self, vocab_size, hidden_size):
        super(EmbeddingSharedWeights, self).__init__()
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.shared_weights = torch.nn.Parameter(torch.Tensor(vocab_size, hidden_size), requires_grad=False)
        self.reset_parameters()

    def reset_parameters(self) -> None:
        a = 1 / math.sqrt(self.hidden_size)
        nn.init.normal_(self.shared_weights, mean=0, std=a)

    def embedding(self, inputs):
        embedded_inputs = self.shared_weights[inputs, :]
        embedded_inputs *= self.hidden_size ** 0.5
        return embedded_inputs

    def linear(self, inputs):
        batch_size = -1 # torch.shape(inputs)[0]
        length = inputs.shape[1]
        x = torch.reshape(inputs, [-1, self.hidden_size])
        logits = torch.matmul(x, self.shared_weights.transpose(0, 1))
        return torch.reshape(logits, [batch_size, length, self.vocab_size])

def get_padding_bias(x: torch.Tensor, padding_value=0, dtype=torch.float32) -> torch.Tensor:
    """
    Args:
        x: tensor of shape [batch_size, length]
    Returns:
        float tensor of shape [batch_size, 1, 1, length]
    """
    assert x.dim() == 2
    neg_inf = _NEG_INF_FP16 if dtype == torch.float16 else _NEG_INF_FP32
    padding = (x == padding_value).to(dtype)
    attention_bias = padding * neg_inf
    attention_bias = attention_bias[:,None,None,:]
    return attention_bias

def get_decoder_self_attention_bias(length, device, dtype=torch.float32):
    neg_inf = _NEG_INF_FP16 if dtype == torch.float16 else _NEG_INF_FP32
    r = torch.arange(0, length, device=device)
    y = (torch.reshape(r, [-1, 1]) < torch.reshape(r, [1, -1])).to(dtype) * neg_inf
    return y[None, None, :, :]

def get_position_encoding(
        length, hidden_size, device, min_timescale=1.0, max_timescale=1.0e4):
    """Return positional encoding.

    Returns:
        Tensor with shape [length, hidden_size]
    """
    position = torch.arange(0, length, device=device, dtype=torch.float32)
    num_timescales = hidden_size // 2
    log_timescale_increment = (
            math.log(float(max_timescale) / float(min_timescale)) /
            (num_timescales - 1))
    inv_timescales = min_timescale * torch.exp(
            torch.arange(0, num_timescales, device=device, dtype=torch.float32) * -log_timescale_increment)
    scaled_time = position[:, None] * inv_timescales[None, :]
    signal = torch.cat([torch.sin(scaled_time), torch.cos(scaled_time)], axis=1)
    return signal

class PrePostProcessingWrapper(nn.Module):

    def __init__(self, layer, hidden_size: int, dropout: float = 0.1):
        super().__init__()
        self.layer_norm = nn.LayerNorm(hidden_size, eps=1e-6)
        self.layer = layer
        self.dropout = nn.Dropout(dropout, inplace=True)

    def load_numpy_state(self):
        with variable_scope("pre_post_processing_wrapper"):
            load_numpy_state_layer_norm(self.layer_norm)
            if isinstance(self.layer, nn.Module):
                self.layer.load_numpy_state()

    def forward(self, x, *args):
        y = self.layer_norm(x)
        y = self.layer(y, *args)
        y = self.dropout(y)
        return x + y

class AttentionLayer(nn.Module):

    def __init__(self, hidden_size: int, num_heads: int, dropout: float = 0.1):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_heads = num_heads
        depth = hidden_size // num_heads
        self.query_layer = EinsumLinear(subscripts='abc,cde->abde', in_shape=[hidden_size], out_shape=[num_heads, depth])
        self.key_layer = EinsumLinear(subscripts='abc,cde->abde', in_shape=[hidden_size], out_shape=[num_heads, depth])
        self.value_layer = EinsumLinear(subscripts='abc,cde->abde', in_shape=[hidden_size], out_shape=[num_heads, depth])
        self.dropout = nn.Dropout(dropout, inplace=False)
        self.output_transform = EinsumLinear(subscripts='abcd,cde->abe', in_shape=[num_heads, depth], out_shape=[hidden_size])

    def load_numpy_state(self):
        with variable_scope('attention'):
            load_numpy_state_dense_layer('query', self.query_layer)
            load_numpy_state_dense_layer('key', self.key_layer)
            load_numpy_state_dense_layer('value', self.value_layer)
            load_numpy_state_dense_layer('output_transform', self.output_transform)

    def forward(self, query_input, source_input, bias):
        return self.attention_layer(query_input, source_input, bias, 'attention')

    def attention_layer(self, query_input, source_input, bias, name):
        with variable_scope(name):
            query = self.query_layer(query_input)
            key = self.key_layer(source_input)
            value = self.value_layer(source_input)

            depth = (self.hidden_size // self.num_heads)
            query *= depth ** -0.5

            logits = torch.einsum('btnh,bfnh->bnft', key, query)
            if bias is not None:
                logits += bias
            weights = torch.softmax(logits, dim=3)
            weights = self.dropout(weights)
            attention_output = torch.einsum('bnft,btnh->bfnh', weights, value)

            attention_output = self.output_transform(attention_output)

        return attention_output

class SelfAttentionLayer(AttentionLayer):
    def load_numpy_state(self):
        with variable_scope('self_attention'):
            load_numpy_state_dense_layer('query', self.query_layer)
            load_numpy_state_dense_layer('key', self.key_layer)
            load_numpy_state_dense_layer('value', self.value_layer)
            load_numpy_state_dense_layer('output_transform', self.output_transform)

    def forward(self, query_input, bias, **args):
        return self.attention_layer(query_input, query_input, bias, name='self_attention', **args)

class FeedForwardNetwork(nn.Module):

    def __init__(self, hidden_size, filter_size):
        super().__init__()
        self.filter_layer = EinsumLinear(
            subscripts='abc,cd->abd',
            in_shape=[hidden_size],
            out_shape=[filter_size],
            use_bias=True)
        self.activation = nn.ReLU()
        self.output_layer = EinsumLinear(
            subscripts='abc,cd->abd',
            in_shape=[filter_size],
            out_shape=[hidden_size],
            use_bias=True)

    def load_numpy_state(self):
        with variable_scope("feed_forward_network"):
            load_numpy_state_dense_layer('filter_layer', self.filter_layer)
            load_numpy_state_dense_layer('output_layer', self.output_layer)

    def forward(self, input):
        with variable_scope("feed_forward_network"):
            x = self.filter_layer(input)
            x = self.activation(x)
            x = self.output_layer(x)
            return x

# Transformer

class TransformerEncoderLayer(nn.Module):

    def __init__(self, hidden_size: int, filter_size: int, num_heads: int):
        super().__init__()
        self.hidden_size = hidden_size
        self.self_attention = PrePostProcessingWrapper(SelfAttentionLayer(hidden_size, num_heads), hidden_size)
        self.ffn = PrePostProcessingWrapper(FeedForwardNetwork(hidden_size, filter_size), hidden_size)

    def load_numpy_state(self):
        with variable_scope("self_attention"):
            self.self_attention.load_numpy_state()
        with variable_scope("ffn"):
            self.ffn.load_numpy_state()

    def forward(self, inputs, attention_bias):
        x = self.self_attention(inputs, attention_bias)
        x = self.ffn(x)
        return x

class TransformerEncoder(nn.Module):

    def __init__(self, num_layers: int, hidden_size: int, filter_size: int, num_heads: int, dropout: float = 0.1):
        super().__init__()
        self.num_layers = num_layers
        self.hidden_size = hidden_size
        layers = []
        for i in range(self.num_layers):
            layers.append(TransformerEncoderLayer(hidden_size=hidden_size, filter_size=filter_size, num_heads=num_heads))
        self.layers = nn.ModuleList(layers)
        self.dropout = nn.Dropout(dropout, inplace=True)
        self.layer_norm = nn.LayerNorm(hidden_size, eps=1e-6)

    def load_numpy_state(self):
        with variable_scope("encode"):
            with variable_scope('encoder_stack'):
                for n in range(self.num_layers):
                    with variable_scope("layer_%d" % n):
                        self.layers[n].load_numpy_state()

                load_numpy_state_layer_norm(self.layer_norm)

    def forward(self, inputs, embedded_inputs):
        attention_bias = get_padding_bias(inputs, dtype=embedded_inputs.dtype)
        length = embedded_inputs.shape[1]
        pos_encoding = get_position_encoding(length, self.hidden_size, device=embedded_inputs.device)
        pos_encoding = pos_encoding.to(embedded_inputs.dtype)
        encoder_inputs = self.dropout(embedded_inputs + pos_encoding)
        return self.encoder_stack(encoder_inputs, attention_bias), attention_bias

    def encoder_stack(self, encoder_inputs, attention_bias):
        for layer in self.layers:
            encoder_inputs = layer(encoder_inputs, attention_bias)
        return self.layer_norm(encoder_inputs)

class TransformerDecoderLayer(nn.Module):

    def __init__(self, hidden_size: int, filter_size: int, num_heads: int):
        super().__init__()
        self.hidden_size = hidden_size
        self.self_attention = PrePostProcessingWrapper(SelfAttentionLayer(hidden_size, num_heads), hidden_size)
        self.encdec_attention = PrePostProcessingWrapper(AttentionLayer(hidden_size, num_heads), hidden_size)
        self.ffn = PrePostProcessingWrapper(FeedForwardNetwork(hidden_size, filter_size), hidden_size)

    def load_numpy_state(self):
        with variable_scope("self_attention"):
            self.self_attention.load_numpy_state()
        with variable_scope("encdec_attention"):
            self.encdec_attention.load_numpy_state()
        with variable_scope("ffn"):
            self.ffn.load_numpy_state()

    def forward(self, decoder_inputs, encoder_outputs,
        decoder_self_attention_bias, attention_bias):
        x = self.self_attention(decoder_inputs, decoder_self_attention_bias)
        x = self.encdec_attention(x, encoder_outputs, attention_bias)
        x = self.ffn(x)
        return x

class TransformerDecoder(nn.Module):

    def __init__(self, num_layers: int, hidden_size: int, filter_size: int, num_heads: int, dropout: float = 0.1):
        super().__init__()
        self.num_layers = num_layers
        self.hidden_size = hidden_size
        self.layers = nn.ModuleList()
        for i in range(self.num_layers):
            self.layers.append(TransformerDecoderLayer(hidden_size=hidden_size, filter_size=filter_size, num_heads=num_heads))
        self.dropout = nn.Dropout(dropout, inplace=True)
        self.layer_norm = nn.LayerNorm(hidden_size, eps=1e-6)

    def load_numpy_state(self):
        with variable_scope("decode"):
            with variable_scope('decoder_stack'):
                for n in range(self.num_layers):
                    with variable_scope("layer_%d" % n):
                        self.layers[n].load_numpy_state()

                load_numpy_state_layer_norm(self.layer_norm)

    def forward(self, embedded_targets, encoder_outputs, attention_bias):
        length = embedded_targets.shape[1]
        pos_encoding = get_position_encoding(length, self.hidden_size, device=embedded_targets.device)
        pos_encoding = pos_encoding.to(embedded_targets.dtype)
        decoder_inputs = self.dropout(embedded_targets + pos_encoding)

        decoder_self_attention_bias = get_decoder_self_attention_bias(
            length, device=embedded_targets.device, dtype=embedded_targets.dtype)
        return self.decoder_stack(
            decoder_inputs,
            encoder_outputs,
            decoder_self_attention_bias,
            attention_bias)

    def decoder_stack(
        self, decoder_inputs, encoder_outputs, decoder_self_attention_bias, attention_bias
        ):
        x = decoder_inputs
        for layer in self.layers:
            x = layer(x, encoder_outputs, decoder_self_attention_bias, attention_bias)
        return self.layer_norm(x)

class Transformer(nn.Module):
    __constants__ = ['vocab_size', 'hidden_size']

    def __init__(self, vocab_size: int, hidden_size: int, filter_size: int, num_layers: int, num_heads: int):
        super().__init__()
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.dtype = torch.float32
        self.encode = TransformerEncoder(hidden_size=hidden_size, filter_size=filter_size, num_layers=num_layers, num_heads=num_heads)
        self.decode = TransformerDecoder(hidden_size=hidden_size, filter_size=filter_size, num_layers=num_layers, num_heads=num_heads)
        self.embedding_softmax_layer = EmbeddingSharedWeights(self.vocab_size, self.hidden_size)

    def load_numpy_state(self):
        self.encode.load_numpy_state()
        self.decode.load_numpy_state()
        with variable_scope('encode/embedding_shared_weights/embedding_and_softmax'):
            self.embedding_softmax_layer.shared_weights.copy_(get_variable('weights'))

    def forward(self, inputs, targets):
        embedded_inputs = self.embedding_softmax_layer.embedding(inputs)
        embedded_targets = self.embedding_softmax_layer.embedding(targets)
        encoder_outputs, attention_bias = self.encode(inputs, embedded_inputs)
        decoder_outputs = self.decode(embedded_targets, encoder_outputs, attention_bias)
        logits = self.embedding_softmax_layer.linear(decoder_outputs)
        return logits

def load_model(file):
    arr = np.load(file)
    set_variables(arr)
    return Transformer(64003, 512, 2048, 6, 8)
