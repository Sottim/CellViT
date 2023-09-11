# -*- coding: utf-8 -*-
# Copyright (c) Facebook, Inc. and its affiliates.
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
#
# Mostly copy-paste from timm library.
# https://github.com/rwightman/pytorch-image-models/blob/master/timm/models/vision_transformer.py


import math
import warnings
from functools import partial
from pathlib import Path
from typing import Callable, List, Tuple, Union

import torch
import torch.multiprocessing
import torch.nn as nn
from torchvision import transforms

torch.multiprocessing.set_sharing_strategy("file_system")

from einops import rearrange
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def _no_grad_trunc_normal_(tensor, mean, std, a, b):
    # Cut & paste from PyTorch official master until it's in a few official releases - RW
    # Method based on https://people.sc.fsu.edu/~jburkardt/presentations/truncated_normal.pdf
    def norm_cdf(x):
        # Computes standard normal cumulative distribution function
        return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

    if (mean < a - 2 * std) or (mean > b + 2 * std):
        warnings.warn(
            "mean is more than 2 std from [a, b] in nn.init.trunc_normal_. "
            "The distribution of values may be incorrect.",
            stacklevel=2,
        )

    with torch.no_grad():
        # Values are generated by using a truncated uniform distribution and
        # then using the inverse CDF for the normal distribution.
        # Get upper and lower cdf values
        l = norm_cdf((a - mean) / std)
        u = norm_cdf((b - mean) / std)

        # Uniformly fill tensor with values from [l, u], then translate to
        # [2l-1, 2u-1].
        tensor.uniform_(2 * l - 1, 2 * u - 1)

        # Use inverse cdf transform for normal distribution to get truncated
        # standard normal
        tensor.erfinv_()

        # Transform to proper mean, std
        tensor.mul_(std * math.sqrt(2.0))
        tensor.add_(mean)

        # Clamp to ensure it's in the proper range
        tensor.clamp_(min=a, max=b)
        return tensor


def trunc_normal_(tensor, mean=0.0, std=1.0, a=-2.0, b=2.0):
    ## type: (Tensor, float, float, float, float) -> Tensor
    return _no_grad_trunc_normal_(tensor, mean, std, a, b)


def drop_path(x, drop_prob: float = 0.0, training: bool = False):
    if drop_prob == 0.0 or not training:
        return x
    keep_prob = 1 - drop_prob
    shape = (x.shape[0],) + (1,) * (
        x.ndim - 1
    )  # work with diff dim tensors, not just 2D ConvNets
    random_tensor = keep_prob + torch.rand(shape, dtype=x.dtype, device=x.device)
    random_tensor.floor_()  # binarize
    output = x.div(keep_prob) * random_tensor
    return output


class DropPath(nn.Module):
    """Drop paths (Stochastic Depth) per sample  (when applied in main path of residual blocks)."""

    def __init__(self, drop_prob=None):
        super(DropPath, self).__init__()
        self.drop_prob = drop_prob

    def forward(self, x):
        return drop_path(x, self.drop_prob, self.training)


class Mlp(nn.Module):
    def __init__(
        self,
        in_features: int,
        hidden_features: int = None,
        out_features: int = None,
        act_layer: Callable = nn.GELU,
        drop: float = 0.0,
    ):
        """Multi-Layer-Perceptron, with two layers (one bottleneck)

        Args:
            in_features (int): Input features
            hidden_features (int, optional): Hidden features (Bottleneck). Defaults to None.
            out_features (int, optional): Out features. Defaults to None.
            act_layer (Callable, optional): Activation Function. Defaults to nn.GELU.
            drop (float, optional): Dropout. Defaults to 0.0.
        """
        super().__init__()
        out_features = out_features or in_features
        hidden_features = hidden_features or in_features
        self.fc1 = nn.Linear(in_features, hidden_features)
        self.act = act_layer()
        self.fc2 = nn.Linear(hidden_features, out_features)
        self.drop = nn.Dropout(drop)

    def forward(self, x):
        x = self.fc1(x)
        x = self.act(x)
        x = self.drop(x)
        x = self.fc2(x)
        x = self.drop(x)
        return x


class Attention(nn.Module):
    """Attention Module (Multi-Head Attention, MHA)

    Args:
        dim (int): Embedding dimension
        num_heads (int, optional): Number of attention heads. Defaults to 8.
        qkv_bias (bool, optional): If bias should be used for query (q), key (k), and value (v). Defaults to False.
        qk_scale (float, optional): Scaling parameter. Defaults to None.
        attn_drop (float, optional): Dropout for attention layer. Defaults to 0.0.
        proj_drop (float, optional): Dropout for projection layers. Defaults to 0.0.
    """

    def __init__(
        self,
        dim: int,
        num_heads: int = 8,
        qkv_bias: bool = False,
        qk_scale: float = None,
        attn_drop: float = 0.0,
        proj_drop: float = 0.0,
    ):
        super().__init__()
        self.num_heads = num_heads
        head_dim = dim // num_heads
        self.scale = qk_scale or head_dim**-0.5  # 1/(sqrt(head_dim))

        self.qkv = nn.Linear(dim, dim * 3, bias=qkv_bias)
        self.attn_drop = nn.Dropout(attn_drop)
        self.proj = nn.Linear(dim, dim)
        self.proj_drop = nn.Dropout(proj_drop)

    def forward(self, x):
        B, N, C = x.shape
        qkv = (
            self.qkv(x)
            .reshape(B, N, 3, self.num_heads, C // self.num_heads)
            .permute(2, 0, 3, 1, 4)
        )
        q, k, v = qkv[0], qkv[1], qkv[2]

        attn = (q @ k.transpose(-2, -1)) * self.scale
        attn = attn.softmax(dim=-1)
        attn = self.attn_drop(attn)

        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        x = self.proj(x)
        x = self.proj_drop(x)
        return x, attn


class Block(nn.Module):
    def __init__(
        self,
        dim: int,
        num_heads: int,
        mlp_ratio: float = 4.0,
        qkv_bias: bool = False,
        qk_scale: float = None,
        drop: float = 0.0,
        attn_drop: float = 0.0,
        drop_path: float = 0.0,
        act_layer: Callable = nn.GELU,
        norm_layer: Callable = nn.LayerNorm,
    ):
        """Transformer Block

        Block consists of Norm Layer, MHA (Multi-Head Attention), Norm and MLP

        Args:
            dim (int): Embedding dimension
            num_heads (int): Number of attention heads. Defaults to 8.
            mlp_ratio (float, optional): MLP ratio for hidden MLP dimension (Bottleneck = dim*mlp_ratio). Defaults to 4.0.
            qkv_bias (bool, optional): If bias should be used for query (q), key (k), and value (v). Defaults to False.
            qk_scale (float, optional): Scaling parameter. Defaults to None.
            drop (float, optional): Dropout in MLP. Defaults to 0.0.
            attn_drop (float, optional): Dropout for attention layer. Defaults to 0.0.
            drop_path (float, optional): Dropout for skip connection. Defaults to 0.0.
            act_layer (Callable, optional): Activation function. Defaults to nn.GELU.
            norm_layer (Callable, optional): Normalization layer. Defaults to nn.LayerNorm.
        """
        super().__init__()
        self.norm1 = norm_layer(dim)
        self.attn = Attention(
            dim,
            num_heads=num_heads,
            qkv_bias=qkv_bias,
            qk_scale=qk_scale,
            attn_drop=attn_drop,
            proj_drop=drop,
        )
        self.drop_path = DropPath(drop_path) if drop_path > 0.0 else nn.Identity()
        self.norm2 = norm_layer(dim)
        mlp_hidden_dim = int(dim * mlp_ratio)
        self.mlp = Mlp(
            in_features=dim,
            hidden_features=mlp_hidden_dim,
            act_layer=act_layer,
            drop=drop,
        )

    def forward(self, x, return_attention=False):
        y, attn = self.attn(self.norm1(x))
        if return_attention:
            return attn
        x = x + self.drop_path(y)
        x = x + self.drop_path(self.mlp(self.norm2(x)))
        return x


class PatchEmbed(nn.Module):
    """Image to Patch Embedding (without positional embedding)

    Args:
        img_size (int, optional): Input image size. Defaults to 224.
        patch_size (int, optional): Patch Token size (one dimension only, cause tokens are squared). Defaults to 16.
        in_chans (int, optional): Number of input channels. Defaults to 3.
        embed_dim (int, optional): Embedding dimension. Defaults to 768.
    """

    def __init__(
        self,
        img_size: int = 224,
        patch_size: int = 16,
        in_chans: int = 3,
        embed_dim: int = 768,
    ):
        super().__init__()
        num_patches = (img_size // patch_size) * (img_size // patch_size)
        self.img_size = img_size
        self.patch_size = patch_size
        self.num_patches = num_patches

        self.proj = nn.Conv2d(
            in_chans, embed_dim, kernel_size=patch_size, stride=patch_size
        )

    def forward(self, x):
        B, C, H, W = x.shape
        x = self.proj(x).flatten(2).transpose(1, 2)
        return x


class VisionTransformer(nn.Module):
    """Vision Transformer"""

    def __init__(
        self,
        img_size: List[int] = [224],
        patch_size: int = 16,
        in_chans: int = 3,
        num_classes: int = 0,
        embed_dim: int = 768,
        depth: int = 12,
        num_heads: int = 12,
        mlp_ratio: float = 4.0,
        qkv_bias: bool = False,
        qk_scale: float = None,
        drop_rate: float = 0.0,
        attn_drop_rate: float = 0.0,
        drop_path_rate: float = 0.0,
        norm_layer: Callable = nn.LayerNorm,
        **kwargs
    ):
        """Vision Transformer with 1D positional embedding

        Args:
            img_size (int, optional): Input image size. Defaults to 224.
            patch_size (int, optional): Patch Token size (one dimension only, cause tokens are squared). Defaults to 16.
            in_chans (int, optional): Number of input channels. Defaults to 3.
            num_classes (int, optional): Number of output classes. if num classes = 0, raw tokens are returned (nn.Identity).
                Default to 0.
            embed_dim (int, optional): Embedding dimension. Defaults to 768.
            depth(int, optional): Number of Transformer Blocks. Defaults to 12.
            num_heads (int, optional): Number of attention heads per Transformer Block. Defaults to 12.
            mlp_ratio (float, optional): MLP ratio for hidden MLP dimension (Bottleneck = dim*mlp_ratio).
                Defaults to 4.0.
            qkv_bias (bool, optional): If bias should be used for query (q), key (k), and value (v). Defaults to False.
            qk_scale (float, optional): Scaling parameter. Defaults to None.
            drop_rate (float, optional): Dropout in MLP. Defaults to 0.0.
            attn_drop_rate (float, optional): Dropout for attention layer. Defaults to 0.0.
            drop_path_rate (float, optional): Dropout for skip connection. Defaults to 0.0.
            norm_layer (Callable, optional): Normalization layer. Defaults to nn.LayerNorm.
        """
        super().__init__()
        self.num_features = self.embed_dim = embed_dim
        self.patch_embed = PatchEmbed(
            img_size=img_size[0],
            patch_size=patch_size,
            in_chans=in_chans,
            embed_dim=embed_dim,
        )
        num_patches = self.patch_embed.num_patches

        self.cls_token = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.pos_embed = nn.Parameter(torch.zeros(1, num_patches + 1, embed_dim))
        self.pos_drop = nn.Dropout(p=drop_rate)

        dpr = [
            x.item() for x in torch.linspace(0, drop_path_rate, depth)
        ]  # stochastic depth decay rule
        self.blocks = nn.ModuleList(
            [
                Block(
                    dim=embed_dim,
                    num_heads=num_heads,
                    mlp_ratio=mlp_ratio,
                    qkv_bias=qkv_bias,
                    qk_scale=qk_scale,
                    drop=drop_rate,
                    attn_drop=attn_drop_rate,
                    drop_path=dpr[i],
                    norm_layer=norm_layer,
                )
                for i in range(depth)
            ]
        )
        self.norm = norm_layer(embed_dim)

        # Classifier head
        self.head = (
            nn.Linear(embed_dim, num_classes) if num_classes > 0 else nn.Identity()
        )

        trunc_normal_(self.pos_embed, std=0.02)
        trunc_normal_(self.cls_token, std=0.02)
        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=0.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)

    def interpolate_pos_encoding(self, x, w, h):
        npatch = x.shape[1] - 1
        N = self.pos_embed.shape[1] - 1
        if npatch == N and w == h:
            return self.pos_embed
        class_pos_embed = self.pos_embed[:, 0]
        patch_pos_embed = self.pos_embed[:, 1:]
        dim = x.shape[-1]
        w0 = w // self.patch_embed.patch_size
        h0 = h // self.patch_embed.patch_size
        # we add a small number to avoid floating point error in the interpolation
        # see discussion at https://github.com/facebookresearch/dino/issues/8
        w0, h0 = w0 + 0.1, h0 + 0.1
        patch_pos_embed = nn.functional.interpolate(
            patch_pos_embed.reshape(
                1, int(math.sqrt(N)), int(math.sqrt(N)), dim
            ).permute(0, 3, 1, 2),
            scale_factor=(w0 / math.sqrt(N), h0 / math.sqrt(N)),
            mode="bicubic",
        )
        assert (
            int(w0) == patch_pos_embed.shape[-2]
            and int(h0) == patch_pos_embed.shape[-1]
        )
        patch_pos_embed = patch_pos_embed.permute(0, 2, 3, 1).view(1, -1, dim)
        return torch.cat((class_pos_embed.unsqueeze(0), patch_pos_embed), dim=1)

    def prepare_tokens(self, x):
        B, nc, w, h = x.shape
        x = self.patch_embed(x)  # patch linear embedding

        # add the [CLS] token to the embed patch tokens
        cls_tokens = self.cls_token.expand(B, -1, -1)
        x = torch.cat((cls_tokens, x), dim=1)

        # add positional encoding to each token
        x = x + self.interpolate_pos_encoding(x, w, h)

        return self.pos_drop(x)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward pass

        Args:
            x (torch.Tensor): Input batch

        Returns:
            Tuple[torch.Tensor]: Class token (raw)
        """

        x = self.prepare_tokens(x)
        for blk in self.blocks:
            x = blk(x)
        x = self.norm(x)
        return x[:, 0]

    def get_last_selfattention(self, x):
        x = self.prepare_tokens(x)
        for i, blk in enumerate(self.blocks):
            if i < len(self.blocks) - 1:
                x = blk(x)
            else:
                # return attention of the last block
                return blk(x, return_attention=True)

    def get_intermediate_layers(self, x, n=1):
        x = self.prepare_tokens(x)
        # we return the output tokens from the `n` last blocks
        output = []
        for i, blk in enumerate(self.blocks):
            x = blk(x)
            if len(self.blocks) - i <= n:
                output.append(self.norm(x))
        return output


def vit_tiny(patch_size=16, **kwargs):
    model = VisionTransformer(
        patch_size=patch_size,
        embed_dim=192,
        depth=12,
        num_heads=3,
        mlp_ratio=4,
        qkv_bias=True,
        norm_layer=partial(nn.LayerNorm, eps=1e-6),
        **kwargs
    )
    return model


def vit_small(patch_size=16, **kwargs):
    model = VisionTransformer(
        patch_size=patch_size,
        embed_dim=384,
        depth=12,
        num_heads=6,
        mlp_ratio=4,
        qkv_bias=True,
        norm_layer=partial(nn.LayerNorm, eps=1e-6),
        **kwargs
    )
    return model


def vit_base(patch_size=16, **kwargs):
    model = VisionTransformer(
        patch_size=patch_size,
        embed_dim=768,
        depth=12,
        num_heads=12,
        mlp_ratio=4,
        qkv_bias=True,
        norm_layer=partial(nn.LayerNorm, eps=1e-6),
        **kwargs
    )
    return model


class DINOHead(nn.Module):
    def __init__(
        self,
        in_dim,
        out_dim,
        use_bn=False,
        norm_last_layer=True,
        nlayers=3,
        hidden_dim=2048,
        bottleneck_dim=256,
    ):
        super().__init__()
        nlayers = max(nlayers, 1)
        if nlayers == 1:
            self.mlp = nn.Linear(in_dim, bottleneck_dim)
        else:
            layers = [nn.Linear(in_dim, hidden_dim)]
            if use_bn:
                layers.append(nn.BatchNorm1d(hidden_dim))
            layers.append(nn.GELU())
            for _ in range(nlayers - 2):
                layers.append(nn.Linear(hidden_dim, hidden_dim))
                if use_bn:
                    layers.append(nn.BatchNorm1d(hidden_dim))
                layers.append(nn.GELU())
            layers.append(nn.Linear(hidden_dim, bottleneck_dim))
            self.mlp = nn.Sequential(*layers)
        self.apply(self._init_weights)
        self.last_layer = nn.utils.weight_norm(
            nn.Linear(bottleneck_dim, out_dim, bias=False)
        )
        self.last_layer.weight_g.data.fill_(1)
        if norm_last_layer:
            self.last_layer.weight_g.requires_grad = False

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=0.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)

    def forward(self, x):
        x = self.mlp(x)
        x = nn.functional.normalize(x, dim=-1, p=2)
        x = self.last_layer(x)
        return x


class ViT256_16(nn.Module):
    def __init__(
        self,
        model256_path: Union[Path, str],
        device: str,
    ) -> None:
        """ViT256-16 Model for Inference. Calculates embeddings for each 256x256 patch within a WSI.

        Args:
            model256_path (Union[Path, str]): Path to checkpoint file
            device (str): Device to work on
        """
        super().__init__()
        self.device = device

        # load bare model, disable gradient and set eval mode
        self.model256 = VisionTransformer(
            patch_size=16,
            num_classes=0,
            embed_dim=384,
            depth=12,
            num_heads=6,
            mlp_ratio=4,
            qkv_bias=True,
            norm_layer=partial(nn.LayerNorm, eps=1e-6),
        )
        for p in self.model256.parameters():
            p.requires_grad = False
        self.model256.eval()
        self.model256.to(device)

        # load pretrained network weights
        checkpoint_key = "teacher"  # use teacher networks since it outperforms student
        state_dict = torch.load(str(model256_path), map_location=device)[checkpoint_key]
        # remove `module.` prefix
        state_dict = {k.replace("module.", ""): v for k, v in state_dict.items()}
        # remove `backbone.` prefix induced by multicrop wrapper
        state_dict = {k.replace("backbone.", ""): v for k, v in state_dict.items()}
        # msg = self.model256.load_state_dict(state_dict, strict=False)
        # logger.info(
        #     f"Pretrained weights found at {model256_path} and loaded with msg: {msg}"
        # )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass of Vision Transformer for given image tensor x

        Args:
            x (torch.Tensor): Input image tensor with shape [B x C x W x H].

        Returns:
            torch.Tensor: [w_256 x h_256 x 192] cls token.
        """
        # prepare input tensor

        # 1. Crop to have a 256 divisible image tensor:
        # [B x 3 x W x H]
        num_patches = x.shape[0]
        batch_256, w_256, h_256 = self.prepare_img_tensor(x)
        # 2. Unfold tensor to create 256x256 patches in a w_256xh_256 grid:
        # [B x 3 x w_256 x h_256 x 256 x 256]
        batch_256 = batch_256.unfold(2, 256, 256).unfold(3, 256, 256)
        # 3. Rearrange dimensions (flatten batch to have a sequence of tokens -> Sequence length = b*16*16):
        # [B' x 3 x 256 x 256], where B' = (B*w_256*h_256)
        batch_256 = rearrange(batch_256, "b c p1 p2 w h -> (b p1 p2) c w h")

        # 4. B' may be too large for ViT-256. We further take minibatches of 256.
        features_cls256 = []
        for mini_bs in range(0, batch_256.shape[0], 256):
            # 4.1. Creating [2048 x 3 x 256 x 256] image batches.
            minibatch_256 = batch_256[mini_bs : mini_bs + 256].to(
                self.device, non_blocking=True
            )
            # 4.2. Extracting ViT-256 features from [2048 x 3 x 256 x 256] image batches.
            features_cls256.append(self.model256(minibatch_256).detach().cpu())

        # 5. [B x 384], where 384 == dim of ViT-256 [ClS] token.
        features_cls256 = torch.vstack(features_cls256)
        assert features_cls256.shape[0] == num_patches
        assert features_cls256.shape[1] == 384

        return features_cls256

    def prepare_img_tensor(
        self, x: torch.Tensor, patch_size: int = 256
    ) -> torch.Tensor:
        """Prepare image tensor to be divisible by 256

        Args:
            x (torch.Tensor): Current image as tensor
            patch_size (int, optional): Patch-size. Defaults to 256.

        Returns:
            torch.Tensor: Cropped tensor, divisible by 256.
        """
        make_divisble = lambda l, patch_size: (l - (l % patch_size))
        b, c, w, h = x.shape
        load_size = make_divisble(w, patch_size), make_divisble(h, patch_size)
        w_256, h_256 = w // patch_size, h // patch_size
        img_new = transforms.CenterCrop(load_size)(x)

        return img_new, w_256, h_256
