# Copyright (C) 2021 Katsuya Iida. All rights reserved.

from argparse import ArgumentParser
from typing import Optional
from .transformer import Translation
import pytorch_lightning as pl
import torch
from torch import nn
from .datasets import AudioTextDataModule

class CharToAudioModel(pl.LightningModule):
    def __init__(self, vocab_size, hidden_size, filter_size, num_layers, num_headers, learning_rate):
        super().__init__()
        self.save_hyperparameters()
        self.transformer = Translation(vocab_size, hidden_size, filter_size, num_layers, num_headers)
        self.criteria = nn.CrossEntropyLoss(reduction='none')
    
    def forward(self, src_ids, src_ids_len, tgt_in_ids):
        logits = self.transformer(src_ids, src_ids_len, tgt_in_ids)
        return logits

    def _calc_batch_loss(self, batch):
        (f0, f0_len, spec, codeap, aligntext), (text, text_len) = batch

        src_ids = text
        src_ids_len = text_len
        tgt_in_ids = aligntext[:, :-1]
        tgt_out_ids = aligntext[:, 1:]
        tgt_out_mask = (torch.arange(tgt_out_ids.shape[1], device=tgt_out_ids.device)[None, :] < f0_len[:, None] - 1).float()

        logits = self.forward(src_ids, src_ids_len, tgt_in_ids)
        logits = torch.transpose(logits, 1, 2)
        loss = self.criteria(logits, tgt_out_ids)
        loss = torch.sum(loss * tgt_out_mask) / torch.sum(tgt_out_mask)
        return loss

    def training_step(self, batch, batch_idx):
        loss = self._calc_batch_loss(batch)
        self.log('train_loss', loss)
        return loss

    def validation_step(self, batch, batch_idx):
        loss = self._calc_batch_loss(batch)
        self.log('val_loss', loss)

    def test_step(self, batch, batch_idx):
        loss = self._calc_batch_loss(batch)
        self.log('test_loss', loss)

    def configure_optimizers(self):
        optimizer = torch.optim.Adam(
            self.parameters(),
            lr=self.hparams.learning_rate,
            betas=(0.9, 0.98),
            weight_decay=0.0001)
        scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.95)
        return {"optimizer": optimizer, "lr_scheduler": scheduler}

    @staticmethod
    def add_model_specific_args(parent_parser):
        parser = ArgumentParser(parents=[parent_parser], add_help=False)
        parser.add_argument('--hidden_size', type=int, default=256)
        parser.add_argument('--filter_size', type=int, default=1024)
        parser.add_argument('--num_layers', type=int, default=4)
        parser.add_argument('--num_headers', type=int, default=8)
        parser.add_argument('--learning_rate', type=float, default=5e-4)
        return parser

    @staticmethod
    def from_argparse_args(args):
        return CharToAudioModel(
            vocab_size=args.vocab_size,
            hidden_size=args.hidden_size,
            filter_size=args.filter_size,
            num_layers=args.num_layers,
            num_headers=args.num_headers,
            learning_rate=args.learning_rate)

def cli_main():
    pl.seed_everything(1234)

    parser = ArgumentParser()
    parser = pl.Trainer.add_argparse_args(parser)
    parser = AudioTextDataModule.add_data_specific_args(parser)
    parser = CharToAudioModel.add_model_specific_args(parser)    
    args = parser.parse_args()

    data = AudioTextDataModule.from_argparse_args(args)
    model = CharToAudioModel.from_argparse_args(args)
    trainer = pl.Trainer.from_argparse_args(args)

    if False:
        model = CharToAudioModel.load_from_checkpoint(args.resume_from_checkpoint)
        test(data, model)
        os.exit()

    trainer.fit(model, data)

def test(data, model):
    from .text import CharTokenizer
    tokenizer = CharTokenizer()
    model.eval()
    data.setup()
    from tqdm import tqdm
    for batch in data.train_dataloader():
        (f0, f0_len, spec, codeap, aligntext), (text, text_len) = batch
        print('===')
        tgt_in = torch.zeros([text.shape[0], 1], dtype=torch.long)
        #print(text.shape, text_len.shape, tgt_in.shape)
        for i in tqdm(range(200)):
            logits = model.forward(text, text_len, tgt_in)
            tgt_out = logits.argmax(axis=-1)
            if False:
                for j in range(text.shape[0]):
                    print(tokenizer.decode(text[j, :]))
                    print(tokenizer.decode(aligntext[j, :]))
                    print(tokenizer.decode(tgt_out[j, :]))
            tgt_in = torch.cat([tgt_in, tgt_out[:, -1:]], axis=1)
        if True:
            for j in range(text.shape[0]):
                print('---')
                print('S:', tokenizer.decode(text[j, :]))
                print('T:', tokenizer.decode(aligntext[j, :]))
                print('H:', tokenizer.decode(tgt_out[j, :]))
        hoge
        if True:
            for i in range(f0.shape[0]):
                print('---')
                x = aligntext[i, :f0_len[i]]
                x = tokenizer.decode(x)
                x = tokenizer.merge_repeated(x)
                print(x)
                x = text[i, :text_len[i]]
                x = tokenizer.decode(x)
                print(x)


if __name__ == '__main__':
    cli_main()