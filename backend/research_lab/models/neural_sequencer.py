"""
Neural Sequencer — TCN + LSTM Market State Predictor
=======================================================
Transitions from XGBoost "letters" (point-in-time features) to
neural "words" (temporal sequences of market states).

Architecture:
  1. TCN (1D-CNN): Reads "syllables" — geometric patterns within
     a 20-day sliding window (V-bottoms, consolidations, Wyckoff).
  2. LSTM: Composes "words" — puts TCN patterns into chronological
     narrative context across market regimes.

Input:  [batch, seq_len=20, n_features]
Output: [batch, 3] — probabilities for {BEARISH, NEUTRAL, BULLISH}

Dependencies: torch (PyTorch).  Pure domain math — no external APIs.
"""
import logging
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


@dataclass
class SequencerConfig:
    """Hyperparameters for the TCN+LSTM architecture."""
    seq_len: int = 20              # Sliding window length (trading days)
    n_features: int = 20           # Number of input dimensions (set dynamically)
    n_classes: int = 3             # BEARISH=0, NEUTRAL=1, BULLISH=2

    # TCN (Temporal Convolutional Network)
    tcn_channels: list[int] = None  # Channel progression per residual block
    tcn_kernel_size: int = 3        # Convolution kernel width
    tcn_dropout: float = 0.2        # Spatial dropout between layers

    # LSTM
    lstm_hidden: int = 64           # Hidden state size
    lstm_layers: int = 2            # Stacked LSTM layers
    lstm_dropout: float = 0.3       # Dropout between LSTM layers

    # Training
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4      # L2 regularization
    batch_size: int = 64
    max_epochs: int = 100
    patience: int = 10              # Early stopping patience

    def __post_init__(self):
        if self.tcn_channels is None:
            self.tcn_channels = [32, 64, 64]


# ── TCN Building Blocks ──────────────────────────────────────────


class CausalConv1d(nn.Module):
    """1D convolution with causal padding (no future leakage)."""

    def __init__(self, in_channels: int, out_channels: int,
                 kernel_size: int, dilation: int = 1):
        super().__init__()
        self.padding = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(
            in_channels, out_channels, kernel_size,
            padding=self.padding, dilation=dilation,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.conv(x)
        # Trim future padding to maintain causality
        if self.padding > 0:
            out = out[:, :, :-self.padding]
        return out


class TemporalBlock(nn.Module):
    """
    Single TCN residual block:
        Input → CausalConv → ReLU → Dropout → CausalConv → ReLU → Dropout
                                                      ↓
                                               + Residual (1x1 conv if channels differ)
    """

    def __init__(self, in_channels: int, out_channels: int,
                 kernel_size: int, dilation: int, dropout: float):
        super().__init__()
        self.conv1 = CausalConv1d(in_channels, out_channels, kernel_size, dilation)
        self.conv2 = CausalConv1d(out_channels, out_channels, kernel_size, dilation)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

        # Residual connection (1x1 conv if channel dimensions change)
        self.residual = (
            nn.Conv1d(in_channels, out_channels, 1)
            if in_channels != out_channels else nn.Identity()
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.dropout(self.relu(self.conv1(x)))
        out = self.dropout(self.relu(self.conv2(out)))
        return out + self.residual(x)


class TCN(nn.Module):
    """
    Temporal Convolutional Network — The "Syllable Reader."

    Stacks TemporalBlocks with exponentially increasing dilation
    to achieve a receptive field that covers the full sequence
    without recurrence.
    """

    def __init__(self, n_features: int, channels: list[int],
                 kernel_size: int, dropout: float):
        super().__init__()
        layers = []
        in_ch = n_features
        for i, out_ch in enumerate(channels):
            dilation = 2 ** i
            layers.append(TemporalBlock(in_ch, out_ch, kernel_size, dilation, dropout))
            in_ch = out_ch
        self.network = nn.Sequential(*layers)
        self.out_channels = channels[-1]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [batch, seq_len, features] → need [batch, features, seq_len] for Conv1d
        return self.network(x.transpose(1, 2)).transpose(1, 2)


# ── Full Architecture ────────────────────────────────────────────


class NeuralSequencer(nn.Module):
    """
    TCN+LSTM Hybrid — From "Letters" to "Words."

    Pipeline:
        Raw features [B, 20, N] → TCN → pattern embeddings [B, 20, 64]
                                       → LSTM → temporal narrative [B, 64]
                                       → FC → class probabilities [B, 3]
    """

    def __init__(self, config: SequencerConfig):
        super().__init__()
        self.config = config

        # Stage 1: TCN extracts local patterns (V-bottoms, consolidations)
        self.tcn = TCN(
            n_features=config.n_features,
            channels=config.tcn_channels,
            kernel_size=config.tcn_kernel_size,
            dropout=config.tcn_dropout,
        )

        # Stage 2: LSTM reads the pattern sequence in temporal order
        self.lstm = nn.LSTM(
            input_size=self.tcn.out_channels,
            hidden_size=config.lstm_hidden,
            num_layers=config.lstm_layers,
            dropout=config.lstm_dropout if config.lstm_layers > 1 else 0,
            batch_first=True,
        )

        # Stage 3: Classification head
        self.classifier = nn.Sequential(
            nn.Dropout(config.lstm_dropout),
            nn.Linear(config.lstm_hidden, config.n_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: [batch, seq_len, n_features]

        Returns:
            logits: [batch, n_classes] (raw, pre-softmax)
        """
        # TCN: extract local geometric patterns
        tcn_out = self.tcn(x)                    # [B, seq_len, tcn_channels[-1]]

        # LSTM: read pattern sequence, take final hidden state
        lstm_out, (h_n, _) = self.lstm(tcn_out)  # h_n: [n_layers, B, hidden]
        final_state = h_n[-1]                    # [B, hidden] — last layer

        # Classify
        logits = self.classifier(final_state)    # [B, n_classes]
        return logits


# ── Training Utilities ───────────────────────────────────────────


def create_sequences(
    features: np.ndarray,
    labels: np.ndarray,
    seq_len: int = 20,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert flat feature matrix into overlapping sequences for the TCN+LSTM.

    Args:
        features: [n_samples, n_features] — the enriched quaternion matrix.
        labels: [n_samples] — next-bar labels (-1, 0, 1).
        seq_len: Sliding window length.

    Returns:
        X: [n_sequences, seq_len, n_features]
        y: [n_sequences] — label of the LAST bar in each window.
    """
    n = len(features)
    if n <= seq_len:
        raise ValueError(f"Not enough samples ({n}) for seq_len={seq_len}")

    X = np.array([features[i:i + seq_len] for i in range(n - seq_len)])
    y = labels[seq_len:]  # Label corresponds to the prediction AFTER the window
    return X, y


def walk_forward_split(
    X: np.ndarray,
    y: np.ndarray,
    n_splits: int = 5,
    train_ratio: float = 0.6,
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """
    Walk-forward (expanding window) cross-validation.

    Unlike k-fold, this respects temporal ordering:
    - Train: [0, ..., t]
    - Test: [t+1, ..., t+gap]
    - Next fold: expand train window, slide test forward.

    This prevents future leakage that standard CV introduces.

    Returns:
        List of (X_train, y_train, X_test, y_test) tuples.
    """
    n = len(X)
    min_train = int(n * train_ratio)
    test_size = (n - min_train) // n_splits

    splits = []
    for i in range(n_splits):
        train_end = min_train + i * test_size
        test_end = min(train_end + test_size, n)
        if train_end >= n or test_end <= train_end:
            break
        splits.append((
            X[:train_end], y[:train_end],
            X[train_end:test_end], y[train_end:test_end],
        ))

    return splits


def train_one_fold(
    model: NeuralSequencer,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    config: SequencerConfig,
    device: torch.device,
) -> dict:
    """
    Train a single walk-forward fold with early stopping.

    Returns:
        Dict with fold metrics: val_accuracy, val_loss, best_epoch.
    """
    model = model.to(device)

    # Shift labels from {-1, 0, 1} to {0, 1, 2} for CrossEntropyLoss
    y_train_shifted = y_train + 1
    y_val_shifted = y_val + 1

    train_dataset = torch.utils.data.TensorDataset(
        torch.FloatTensor(X_train),
        torch.LongTensor(y_train_shifted),
    )
    train_loader = torch.utils.data.DataLoader(
        train_dataset, batch_size=config.batch_size, shuffle=True,
    )

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=5,
    )
    criterion = nn.CrossEntropyLoss()

    best_val_loss = float('inf')
    patience_counter = 0
    best_epoch = 0

    for epoch in range(config.max_epochs):
        # Train
        model.train()
        train_loss = 0
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            optimizer.zero_grad()
            logits = model(X_batch)
            loss = criterion(logits, y_batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_loss += loss.item()

        # Validate
        model.eval()
        with torch.no_grad():
            X_v = torch.FloatTensor(X_val).to(device)
            y_v = torch.LongTensor(y_val_shifted).to(device)
            val_logits = model(X_v)
            val_loss = criterion(val_logits, y_v).item()
            val_preds = val_logits.argmax(dim=1)
            val_acc = (val_preds == y_v).float().mean().item()

        scheduler.step(val_loss)

        # Early stopping
        if val_loss < best_val_loss - 1e-4:
            best_val_loss = val_loss
            patience_counter = 0
            best_epoch = epoch
        else:
            patience_counter += 1
            if patience_counter >= config.patience:
                logger.debug(f"  Early stop at epoch {epoch} (best: {best_epoch})")
                break

    return {
        "val_accuracy": val_acc,
        "val_loss": best_val_loss,
        "best_epoch": best_epoch,
    }


def evaluate_sharpe(
    model: NeuralSequencer,
    X_test: np.ndarray,
    y_test: np.ndarray,
    device: torch.device,
) -> dict:
    """
    Compute trading Sharpe from model predictions on held-out data.

    Strategy: go LONG on BULLISH predictions, SHORT on BEARISH,
    FLAT on NEUTRAL. Sharpe = mean(daily_returns) / std(daily_returns) * sqrt(252).
    """
    model.eval()
    with torch.no_grad():
        X_t = torch.FloatTensor(X_test).to(device)
        logits = model(X_t)
        preds = logits.argmax(dim=1).cpu().numpy() - 1  # Back to {-1, 0, 1}

    # Actual returns (labels are already the actual direction)
    actual_returns = y_test.astype(float)

    # Strategy returns: position × actual direction
    # Using a fixed 0.5% daily move proxy when direction is correct
    strategy_returns = preds * actual_returns * 0.005

    if len(strategy_returns) < 2 or np.std(strategy_returns) < 1e-8:
        return {"sharpe": 0.0, "accuracy": 0.0, "n_trades": 0}

    sharpe = (np.mean(strategy_returns) / np.std(strategy_returns)) * np.sqrt(252)
    accuracy = np.mean(preds == y_test)
    n_trades = int(np.sum(preds != 0))

    return {
        "sharpe": float(sharpe),
        "accuracy": float(accuracy),
        "n_trades": n_trades,
    }
