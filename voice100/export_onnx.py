# Copyright (C) 2021 Katsuya Iida. All rights reserved.

from argparse import ArgumentParser
import torch
from torch import nn

MELSPEC_DIM = 64
BATCH_SIZE = 1


def export_onnx_asr(args):
    from .models import AudioToAlignText

    model = AudioToAlignText.load_from_checkpoint(args.ckpt_path)
    model.eval()

    audio = torch.rand(size=[1, 100, MELSPEC_DIM], dtype=torch.float32)

    torch.onnx.export(
        model,
        audio,
        args.output,
        export_params=True,
        verbose=args.verbose,
        opset_version=args.opset_version,
        do_constant_folding=True,
        input_names=["audio"],
        output_names=["logits"],
        dynamic_axes={
            "audio": {0: "batch_size", 1: "audio_len"},
            "logits": {0: "batch_size", 1: "logits_len"},
        },
    )


def export_onnx_align2(args):
    from voice100.models import TextToAlignText

    model = TextToAlignText.load_from_checkpoint(args.ckpt_path)
    batch_size = 1
    vocab_size = model.hparams["vocab_size"]
    text_len = 10
    input_sample = {
        "text": torch.randint(low=0, high=vocab_size, size=(batch_size, text_len), requires_grad=False),
        "text_len": torch.tensor([text_len], dtype=torch.int64, requires_grad=False)
    }

    model.to_onnx(args.output, input_sample)


def export_onnx_align(args):
    from voice100.models import TextToAlignText

    model = TextToAlignText.load_from_checkpoint(args.ckpt_path)
    model.eval()

    vocab_size = model.hparams["vocab_size"]
    batch_size = 1
    text_len = 100
    text = torch.randint(low=0, high=vocab_size, size=(batch_size, text_len))#, requires_grad=False)
    text_len = torch.tensor([100], dtype=torch.int64)#, requires_grad=False)

    class M(nn.Module):
        def __init__(self, model: TextToAlignText):
            super().__init__()
            self.model = model

        def forward(self, text, text_len):
            return self.model.forward_for_export(text, text_len)

    model = M(model)

    torch.onnx.export(
        model,  # model being run
        (text, text_len),  # model input (or a tuple for multiple inputs)
        args.output,  # where to save the model (can be a file or file-like object)
        export_params=True,  # store the trained parameter weights inside the model file
        verbose=args.verbose,
        opset_version=args.opset_version,  # the ONNX version to export the model to
        do_constant_folding=True,  # whether to execute constant folding for optimization
        input_names=["text", "text_len"],  # the model's input names
        output_names=["align"],  # the model's output names
        dynamic_axes={
            # "text": {0: "batch_size", 1: "text_len"},  # variable length axes
            # "align": {0: "batch_size", 1: "text_len"},
            "text": {1: "text_len"},  # variable length axes
            "align": {1: "text_len"},
        },
    )


class AlignTextToAudioPredictModel(nn.Module):
    def __init__(self, model) -> None:
        super().__init__()
        self.model = model

    def forward(self, aligntext):
        return self.model.predict(aligntext)


def export_onnx_tts(args):
    from voice100.models.tts import AlignTextToAudioModel

    model = AlignTextToAudioModel.load_from_checkpoint(args.ckpt_path)
    vocab_size = model.hparams["vocab_size"]
    model.eval()
    model = AlignTextToAudioPredictModel(model)

    aligntext_len = 100
    aligntext = torch.randint(
        low=0, high=vocab_size, size=(BATCH_SIZE, aligntext_len), requires_grad=False
    )

    torch.onnx.export(
        model,  # model being run
        aligntext,
        args.output,
        export_params=True,  # store the trained parameter weights inside the model file
        verbose=args.verbose,
        opset_version=args.opset_version,  # the ONNX version to export the model to
        do_constant_folding=True,  # whether to execute constant folding for optimization
        input_names=["aligntext"],  # the model's input names
        output_names=["f0", "logspc", "codeap"],  # the model's output names
        dynamic_axes={
            "aligntext": {0: "batch_size", 1: "aligntext_len"},  # variable length axes
            "f0": {0: "batch_size", 1: "audio_len"},
            "logspc": {0: "batch_size", 1: "audio_len"},
            "codeap": {0: "batch_size", 1: "audio_len"},
        },
    )


def export_onnx_tts_mt(args):
    from voice100.models.tts import AlignTextToAudioMultiTaskModel

    model = AlignTextToAudioMultiTaskModel.load_from_checkpoint(args.ckpt_path)
    vocab_size = model.hparams["vocab_size"]
    model.eval()
    model = AlignTextToAudioPredictModel(model)

    aligntext_len = 100
    aligntext = torch.randint(
        low=0, high=vocab_size, size=(BATCH_SIZE, aligntext_len), requires_grad=False
    )

    torch.onnx.export(
        model,  # model being run
        aligntext,
        args.output,
        export_params=True,  # store the trained parameter weights inside the model file
        verbose=args.verbose,
        opset_version=args.opset_version,  # the ONNX version to export the model to
        do_constant_folding=True,  # whether to execute constant folding for optimization
        input_names=["aligntext"],  # the model's input names
        output_names=["f0", "logspc", "codeap", "logits"],  # the model's output names
        dynamic_axes={
            "aligntext": {0: "batch_size", 1: "aligntext_len"},  # variable length axes
            "f0": {0: "batch_size", 1: "audio_len"},
            "logspc": {0: "batch_size", 1: "audio_len"},
            "codeap": {0: "batch_size", 1: "audio_len"},
            "logits": {0: "batch_size", 1: "aligntext_len"},
        },
    )


def cli_main():
    parser = ArgumentParser()
    parser.add_argument("--ckpt_path", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--model", type=str, choices=["asr", "align", "tts", "tts_mt"], required=True)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--opset_version", type=int, default=13)

    args = parser.parse_args()

    if args.model == "asr":
        export_onnx_asr(args)
    elif args.model == "align":
        export_onnx_align(args)
    elif args.model == "tts":
        export_onnx_tts(args)
    elif args.model == "tts_mt":
        export_onnx_tts_mt(args)
    else:
        raise ValueError()


if __name__ == "__main__":
    cli_main()
