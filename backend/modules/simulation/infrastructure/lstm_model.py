"""
Quantitative Institutional LSTM — Deep Learning Model
=======================================================
Migrated from _legacy/lstm_model.py into simulation infrastructure.
"""
import torch
import torch.nn as nn
import logging

logger = logging.getLogger(__name__)

class QuantInstitutionalLSTM(nn.Module):
    """Attention-based LSTM for Triple Barrier probability prediction."""
    def __init__(self, input_dim: int, hidden_dim: int = 128, num_layers: int = 2, dropout: float = 0.3):
        super(QuantInstitutionalLSTM, self).__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.batch_norm = nn.BatchNorm1d(num_features=input_dim)
        self.lstm = nn.LSTM(input_size=input_dim, hidden_size=hidden_dim, num_layers=num_layers, dropout=dropout if num_layers > 1 else 0.0, batch_first=True)
        self.attention_weights = nn.Linear(hidden_dim, 1)
        self.fc1 = nn.Linear(hidden_dim, 64)
        self.relu = nn.ReLU()
        self.dropout_layer = nn.Dropout(dropout)
        self.out = nn.Linear(64, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        batch_size, seq_len, num_feats = x.size()
        x_norm = x.permute(0, 2, 1)
        x_norm = self.batch_norm(x_norm)
        x_norm = x_norm.permute(0, 2, 1)
        lstm_out, (hn, cn) = self.lstm(x_norm)
        att_scores = self.attention_weights(lstm_out)
        att_weights = torch.softmax(att_scores, dim=1)
        context_vector = torch.sum(att_weights * lstm_out, dim=1)
        fc_out = self.fc1(context_vector)
        fc_out = self.relu(fc_out)
        fc_out = self.dropout_layer(fc_out)
        final_probability = self.sigmoid(self.out(fc_out))
        return final_probability.squeeze(-1)

def initialize_device():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info(f"Deep Learning device: {device}")
    return device
