# Copyright (C) 2021 Katsuya Iida. All rights reserved.

from argparse import ArgumentParser
from typing import Tuple, List
import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

from ._base import Voice100ModelBase
from ._layers_v2 import get_conv_layers, generate_padding_mask, WORLDNorm, WORLDLoss


class AlignTextToAudioAlignText(Voice100ModelBase):
    def __init__(
        self,
        vocab_size: int,
        target_vocab_size: int,
        logspc_size: int,
        codeap_size: int,
        encoder_num_layers: int,
        encoder_hidden_size: int,
        decoder_settings: List[List],
        logspc_weight: float = 5.0,
        learning_rate: float = 1e-3,
        f0_size: int = 1,
    ) -> None:
        super().__init__()
        self.save_hyperparameters()
        self.encoder_hidden_size = encoder_hidden_size
        self.vocab_size = vocab_size
        self.target_vocab_size = target_vocab_size
        self.f0_size = f0_size
        self.logspc_size = logspc_size
        self.codeap_size = codeap_size
        self.audio_size = 2 * self.f0_size + self.logspc_size + 2 * self.codeap_size
        self.embedding = nn.Embedding(vocab_size, encoder_hidden_size)
        self.lstm = nn.LSTM(
            input_size=encoder_hidden_size, hidden_size=encoder_hidden_size,
            num_layers=encoder_num_layers, dropout=0.2, bidirectional=True)
        self.decoder = get_conv_layers(2 * encoder_hidden_size, decoder_settings)
        self.projection = nn.Linear(decoder_settings[-1][0], self.audio_size)
        self.target_projection = nn.Linear(decoder_settings[-1][0], self.target_vocab_size)
        self.norm = WORLDNorm(self.logspc_size, self.codeap_size)
        self.criterion = WORLDLoss()
        self.target_criterion = nn.CrossEntropyLoss(reduction='none')
        self.logspc_weight = logspc_weight

    def forward(
        self, aligntext: torch.Tensor, aligntext_len: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:

        x = self.embedding(aligntext)
        x_len = aligntext_len
        # x: [batch_size, aligntext_len, encoder_hidden_size]
        packed_x = pack_padded_sequence(x, x_len.cpu(), batch_first=True, enforce_sorted=False)
        packed_lstm_out, _ = self.lstm(packed_x)
        lstm_out, lstm_out_len = pad_packed_sequence(packed_lstm_out, batch_first=True)
        # x: [batch_size, aligntext_len, encoder_hidden_size]
        target_logits = self.target_projection(x)
        # target_logits: [batch_size, aligntext_len, target_vocab_size]

        x = torch.transpose(lstm_out, -2, -1)
        x = self.decoder(x)
        x = torch.transpose(x, -2, -1)
        x = self.projection(x)
        # world_out: [batch_size, target_len, audio_size]

        hasf0_logits, f0_hat, logspc_hat, hascodeap_logits, codeap_hat = torch.split(x, [
            self.f0_size,
            self.f0_size,
            self.logspc_size,
            self.codeap_size,
            self.codeap_size
        ], dim=2)
        hasf0_logits = hasf0_logits[:, :, 0]
        f0_hat = f0_hat[:, :, 0]
        return hasf0_logits, f0_hat, logspc_hat, hascodeap_logits, codeap_hat, target_logits

    def predict(
        self, aligntext: torch.Tensor, aligntext_len: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:

        hasf0, f0, logspc, hascodeap, codeap, target_logits = self.forward(aligntext, aligntext_len)
        f0, logspc, codeap = self.norm.unnormalize(f0, logspc, codeap)
        f0 = torch.where(
            hasf0 < 0, torch.zeros(size=(1,), dtype=f0.dtype, device=f0.device), f0
        )
        codeap = torch.where(
            hascodeap < 0, torch.zeros(size=(1, 1), dtype=codeap.dtype, device=codeap.device), codeap
        )
        return f0, logspc, codeap, target_logits

    def _calc_batch_loss(self, batch) -> Tuple[torch.Tensor, ...]:
        (f0, f0_len, logspc, codeap), (aligntext, aligntext_len), (targettext, targettext_len) = batch
        if True:
            print(aligntext[0, :aligntext_len[0]].detach().numpy())
            print(targettext[0, :targettext_len[0]].detach().numpy())
        hasf0 = (f0 >= 30.0).to(torch.float32)
        hascodeap = (codeap < -0.2).to(torch.float32)
        f0, logspc, codeap = self.norm.normalize(f0, logspc, codeap)

        hasf0_logits, f0_hat, logspc_hat, hascodeap_logits, codeap_hat, target_logits = self.forward(aligntext, aligntext_len)

        hasf0_loss, f0_loss, logspc_loss, hascodeap_loss, codeap_loss = self.criterion(
            f0_len, hasf0_logits, f0_hat, logspc_hat, hascodeap_logits, codeap_hat, hasf0, f0, logspc, hascodeap, codeap)

        mask = generate_padding_mask(targettext, targettext_len)
        mask_sum = torch.sum(mask)
        x = torch.transpose(target_logits, -2, -1)
        target_loss = self.target_criterion(x, targettext)
        target_loss = torch.sum(target_loss * mask) / mask_sum

        return hasf0_loss, f0_loss, logspc_loss, hascodeap_loss, codeap_loss, target_loss

    def training_step(self, batch, batch_idx) -> torch.Tensor:
        hasf0_loss, f0_loss, logspc_loss, hascodeap_loss, codeap_loss, target_loss = self._calc_batch_loss(batch)
        loss = hasf0_loss + f0_loss + logspc_loss * self.logspc_weight + hascodeap_loss + codeap_loss + target_loss
        self._log_loss('train', loss, hasf0_loss, f0_loss, logspc_loss, hascodeap_loss, codeap_loss, target_loss)
        return loss

    def validation_step(self, batch, batch_idx):
        hasf0_loss, f0_loss, logspc_loss, hascodeap_loss, codeap_loss, target_loss = self._calc_batch_loss(batch)
        loss = hasf0_loss + f0_loss + logspc_loss * self.logspc_weight + hascodeap_loss + codeap_loss + target_loss
        self._log_loss('val', loss, hasf0_loss, f0_loss, logspc_loss, hascodeap_loss, codeap_loss, target_loss)

    def test_step(self, batch, batch_idx):
        hasf0_loss, f0_loss, logspc_loss, hascodeap_loss, codeap_loss, target_loss = self._calc_batch_loss(batch)
        loss = hasf0_loss + f0_loss + logspc_loss * self.logspc_weight + hascodeap_loss + codeap_loss + target_loss
        self._log_loss('test', loss, hasf0_loss, f0_loss, logspc_loss, hascodeap_loss, codeap_loss, target_loss)

    def _log_loss(self, task, loss, hasf0_loss, f0_loss, logspc_loss, hascodeap_loss, codeap_loss, target_loss) -> None:
        self.log(f'{task}_loss', loss)
        self.log(f'{task}_hasf0_loss', hasf0_loss)
        self.log(f'{task}_f0_loss', f0_loss)
        self.log(f'{task}_logspc_loss', logspc_loss)
        self.log(f'{task}_hascodeap_loss', hascodeap_loss)
        self.log(f'{task}_codeap_loss', codeap_loss)
        self.log(f'{task}_target_loss', target_loss)

    def configure_optimizers(self):
        return torch.optim.Adam(
            self.parameters(),
            lr=self.hparams.learning_rate)

    @staticmethod
    def add_model_specific_args(parent_parser):
        parser = ArgumentParser(parents=[parent_parser], add_help=False)
        parser.add_argument('--model_size', choices=["base"], default='base')
        parser.add_argument('--audio_stat', type=str)
        parser.add_argument('--learning_rate', type=float, default=1e-3)
        return parser

    @staticmethod
    def from_argparse_args(args, **kwargs):
        if args.model_size == "base":
            decoder_settings = [
                # out_channels, transpose, kernel_size, stride, padding, bias
                [512, False, 5, 1, 2, False],
                [512, True, 5, 2, 2, False],
                [512, False, 5, 1, 2, False],
            ]
            encoder_num_layers = 2
            encoder_hidden_size = 512
        else:
            raise ValueError("Unknown model_size")
        use_mcep = args.vocoder == "world_mcep"
        model = AlignTextToAudioAlignText(
            encoder_num_layers=encoder_num_layers,
            encoder_hidden_size=encoder_hidden_size,
            decoder_settings=decoder_settings,
            logspc_size=25 if use_mcep else 257,
            codeap_size=1,
            learning_rate=args.learning_rate,
            **kwargs)
        if not args.resume_from_checkpoint:
            if args.audio_stat is None:
                args.audio_stat = f'./data/{args.dataset}-stat.pt'
            model.norm.load_state_dict(torch.load(args.audio_stat))
        return model