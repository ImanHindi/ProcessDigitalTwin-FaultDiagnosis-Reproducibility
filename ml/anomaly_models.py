from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import torch
from torch import nn


class DenseDenoisingAutoencoder(nn.Module):
    def __init__(self, input_dim: int, latent_dim: int = 24):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 128), nn.GELU(),
            nn.Linear(128, 64), nn.GELU(),
            nn.Linear(64, latent_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 64), nn.GELU(),
            nn.Linear(64, 128), nn.GELU(),
            nn.Linear(128, input_dim),
        )

    def forward(self, x):
        return self.decoder(self.encoder(x))


class VariationalAutoencoder(nn.Module):
    def __init__(self, input_dim: int, latent_dim: int = 16):
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Linear(input_dim, 128), nn.GELU(),
            nn.Linear(128, 64), nn.GELU(),
        )
        self.mu = nn.Linear(64, latent_dim)
        self.logvar = nn.Linear(64, latent_dim)
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 64), nn.GELU(),
            nn.Linear(64, 128), nn.GELU(),
            nn.Linear(128, input_dim),
        )

    def encode(self, x):
        h = self.backbone(x)
        return self.mu(h), self.logvar(h)

    @staticmethod
    def reparameterize(mu, logvar):
        std = torch.exp(0.5 * logvar)
        return mu + torch.randn_like(std) * std

    def forward(self, x):
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        return self.decoder(z), mu, logvar

    def reconstruct_deterministic(self, x):
        mu, _ = self.encode(x)
        return self.decoder(mu)


class ConditionalVariationalAutoencoder(nn.Module):
    def __init__(self, input_dim: int, n_modes: int = 7, latent_dim: int = 16):
        super().__init__()
        self.input_dim = input_dim
        self.n_modes = n_modes
        enc_dim = input_dim + n_modes
        self.backbone = nn.Sequential(
            nn.Linear(enc_dim, 128), nn.GELU(),
            nn.Linear(128, 64), nn.GELU(),
        )
        self.mu = nn.Linear(64, latent_dim)
        self.logvar = nn.Linear(64, latent_dim)
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim + n_modes, 64), nn.GELU(),
            nn.Linear(64, 128), nn.GELU(),
            nn.Linear(128, input_dim),
        )

    def _one_hot(self, mode):
        mode = torch.clamp(mode.long(), 0, self.n_modes - 1)
        return torch.nn.functional.one_hot(mode, self.n_modes).float()

    def encode(self, x, mode):
        m = self._one_hot(mode)
        h = self.backbone(torch.cat([x, m], dim=1))
        return self.mu(h), self.logvar(h), m

    @staticmethod
    def reparameterize(mu, logvar):
        std = torch.exp(0.5 * logvar)
        return mu + torch.randn_like(std) * std

    def forward(self, x, mode):
        mu, logvar, m = self.encode(x, mode)
        z = self.reparameterize(mu, logvar)
        recon = self.decoder(torch.cat([z, m], dim=1))
        return recon, mu, logvar

    def reconstruct_deterministic(self, x, mode):
        mu, _, m = self.encode(x, mode)
        return self.decoder(torch.cat([mu, m], dim=1))


class LSTMEncoderDecoder(nn.Module):
    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 64,
        latent_dim: int = 32,
        num_layers: int = 1,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim
        self.num_layers = num_layers
        self.encoder = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
        )
        self.to_latent = nn.Linear(hidden_dim, latent_dim)
        self.decoder = nn.LSTM(
            input_size=latent_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
        )
        self.output = nn.Linear(hidden_dim, input_dim)

    def forward(self, x):
        _, (h, _) = self.encoder(x)
        latent = self.to_latent(h[-1])
        repeated = latent.unsqueeze(1).repeat(1, x.shape[1], 1)
        decoded, _ = self.decoder(repeated)
        return self.output(decoded)


def build_model(model_type: str, config: dict) -> nn.Module:
    if model_type == 'dae':
        return DenseDenoisingAutoencoder(
            int(config['input_dim']), int(config.get('latent_dim', 24))
        )
    if model_type == 'vae':
        return VariationalAutoencoder(
            int(config['input_dim']), int(config.get('latent_dim', 16))
        )
    if model_type == 'cvae':
        return ConditionalVariationalAutoencoder(
            int(config['input_dim']),
            int(config.get('n_modes', 7)),
            int(config.get('latent_dim', 16)),
        )
    if model_type == 'lstm_ae':
        return LSTMEncoderDecoder(
            int(config['input_dim']),
            int(config.get('hidden_dim', 64)),
            int(config.get('latent_dim', 32)),
            int(config.get('num_layers', 1)),
        )
    raise ValueError(f'Unsupported anomaly model type: {model_type}')


def preprocess_array(X, medians, means, scales, clip=10.0):
    X = np.asarray(X, dtype=np.float32)
    medians = np.asarray(medians, dtype=np.float32)
    means = np.asarray(means, dtype=np.float32)
    scales = np.asarray(scales, dtype=np.float32)
    X = np.where(np.isfinite(X), X, medians)
    X = (X - means) / scales
    return np.clip(X, -clip, clip).astype(np.float32, copy=False)


def torch_load_compat(path, map_location='cpu'):
    try:
        return torch.load(path, map_location=map_location, weights_only=False)
    except TypeError:
        return torch.load(path, map_location=map_location)


def load_deep_anomaly_artifact(path, device='cpu'):
    package = torch_load_compat(path, map_location=device)
    model = build_model(package['model_type'], package['model_config'])
    model.load_state_dict(package['state_dict'])
    model.to(device)
    model.eval()
    return package, model


def score_window_model(package, model, X, modes=None, batch_size=2048, device='cpu'):
    Xp = preprocess_array(
        X,
        package['imputer_medians'],
        package['scaler_mean'],
        package['scaler_scale'],
    )
    result = np.empty(len(Xp), dtype=np.float32)
    model.eval()
    with torch.no_grad():
        for start in range(0, len(Xp), batch_size):
            stop = min(start + batch_size, len(Xp))
            xb = torch.from_numpy(Xp[start:stop]).to(device)
            if package['model_type'] == 'dae':
                recon = model(xb)
            elif package['model_type'] == 'vae':
                recon = model.reconstruct_deterministic(xb)
            elif package['model_type'] == 'cvae':
                if modes is None:
                    raise ValueError('CVAE scoring requires process modes.')
                # Make an owned, writable array before converting to a tensor.
                # Some pandas/NumPy views are read-only, which triggers a
                # PyTorch undefined-behavior warning with torch.as_tensor().
                mode_batch = np.array(
                    modes[start:stop],
                    dtype=np.int64,
                    copy=True,
                )
                mb = torch.from_numpy(mode_batch).to(
                    device=device,
                    dtype=torch.long,
                )
                recon = model.reconstruct_deterministic(xb, mb)
            else:
                raise ValueError('score_window_model supports DAE/VAE/CVAE only.')
            err = torch.mean((recon - xb) ** 2, dim=1)
            result[start:stop] = err.detach().cpu().numpy().astype(np.float32)
    return result


def score_sequence_model(package, model, sequences, batch_size=512, device='cpu'):
    seq = np.asarray(sequences, dtype=np.float32)
    result = np.empty(len(seq), dtype=np.float32)
    model.eval()
    with torch.no_grad():
        for start in range(0, len(seq), batch_size):
            stop = min(start + batch_size, len(seq))
            xb = torch.from_numpy(seq[start:stop]).to(device)
            recon = model(xb)
            err = torch.mean((recon - xb) ** 2, dim=(1, 2))
            result[start:stop] = err.detach().cpu().numpy().astype(np.float32)
    return result
