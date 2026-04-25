import torch
import torch.nn as nn
import logging

logger = logging.getLogger(__name__)

class QuantInstitutionalLSTM(nn.Module):
    """
    Red Neuronal con Memoria (LSTM) para Análisis Sectorial Cuantamental.
    Procesa ventanas de tiempo (Películas) paramétricas (ej. 30 velas) para
    comprender el contexto de la divergencia VWAP y la intención de liquidez institucional
    ANTES de predecir la expansión del precio.
    """
    def __init__(self, input_dim: int, hidden_dim: int = 128, num_layers: int = 2, dropout: float = 0.3):
        super(QuantInstitutionalLSTM, self).__init__()
        
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        
        # Capa de Normalización previa a la lectura recurrente
        self.batch_norm = nn.BatchNorm1d(num_features=input_dim)
        
        # El núcleo de Memoria a largo/corto plazo
        # batch_first=True -> Entradas de dimensión [Lote, Secuencia, Features]
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
            batch_first=True
        )
        
        # Red de Atención Básica (Self-Attention) sobre el tensor temporal (opcional, extrae el clímax)
        self.attention_weights = nn.Linear(hidden_dim, 1)
        
        # Capas de Decodificación del Cerebro
        self.fc1 = nn.Linear(hidden_dim, 64)
        self.relu = nn.ReLU()
        self.dropout_layer = nn.Dropout(dropout)
        
        # Proyección Final: Asimetría del Triple Barrier (1 nodo, 0 a 1)
        # 1 = Alta Probabilidad Asimétrica, 0 = Ignorar Contexto
        self.out = nn.Linear(64, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        """
        x dimensionalidad esperada: [Batch, Seq_len, Features]
        """
        batch_size, seq_len, num_feats = x.size()
        
        # Normalizacion temporal para la red
        # BatchNorm1d requiere [Batch, Features, Seq_len]
        x_norm = x.permute(0, 2, 1)
        x_norm = self.batch_norm(x_norm)
        x_norm = x_norm.permute(0, 2, 1) # Devolver a [Batch, Seq, Feat]
        
        # Pasa por el núcleo LSTM (No necesitamos inicializar estados ocultos explícitamente a 0s, 
        # Pytorch lo hace internamente por defecto).
        lstm_out, (hn, cn) = self.lstm(x_norm)
        
        # ATENCIÓN: El mercado no es plano. Alguna de las 30 velas tuvo la "Huella Mágica"
        # Aplicamos una red lineal para sacar el score de importancia de cada vela (Atención temporal)
        att_scores = self.attention_weights(lstm_out) # [Batch, Seq, 1]
        att_weights = torch.softmax(att_scores, dim=1) # Normalizar pesos a 1
        
        # Multiplicamos el vector oculto de la vela por la importancia de la vela
        context_vector = torch.sum(att_weights * lstm_out, dim=1) # Queda contraído a [Batch, Hidden]
        
        # Pasamos el contexto detectado por las capas lineales densas finales
        fc_out = self.fc1(context_vector)
        fc_out = self.relu(fc_out)
        fc_out = self.dropout_layer(fc_out)
        
        # Emitir Probabilidad de Triple Barrier [0.0 ... 1.0]
        final_probability = self.sigmoid(self.out(fc_out))
        
        # Convertir a arreglo 1D plano en vez de [batch, 1]
        return final_probability.squeeze(-1) 

def initialize_device():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info(f"Arquitectura Deep Learning anclada a Dispositivo Hardware: {device}")
    return device
