import logging
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import warnings

# Suprimir avisos de torch/huggingface
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

# Definición de Caché estática (Singleton) para no recargar el modelo con cada titular
_tokenizer = None
_model = None
_device = "cuda" if torch.cuda.is_available() else "cpu"

def _load_finbert():
    global _tokenizer, _model
    if _model is None:
        logger.info(f"Cargando Red Neuronal FinBERT (Transfer Learning) en {_device}...")
        model_name = "ProsusAI/finbert"
        try:
            _tokenizer = AutoTokenizer.from_pretrained(model_name, clean_up_tokenization_spaces=True)
            _model = AutoModelForSequenceClassification.from_pretrained(model_name).to(_device)
            _model.eval() # Modo inferencia
        except Exception as e:
            logger.error(f"Error cargando FinBERT: {e}")
            raise

def score_headline(headline: str) -> float:
    """
    Analiza un titular usando NLP Institucional (ProsusAI/finbert).
    Diferencia el ruido del pánico verdadero basado en la narrativa.
    Retorna: float [-1.0 a 1.0]
    """
    if not headline or not headline.strip():
        return 0.0
        
    _load_finbert()
    
    # Tokenizar
    inputs = _tokenizer(headline, return_tensors="pt", truncation=True, padding=True).to(_device)
    
    with torch.no_grad():
        outputs = _model(**inputs)
        
    # ProsusAI FinBERT Labels:
    # 0 = positivo, 1 = negativo, 2 = neutral
    probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)[0]
    
    # Extracción Vectorial de Certeza
    prob_pos = probabilities[0].item()
    prob_neg = probabilities[1].item()
    
    # Rango Normalizado [-1, 1]. Neutrales (0-0) arrojarán 0.
    sentiment_score = prob_pos - prob_neg
    return float(sentiment_score)

def get_sentiment_probabilities(headline: str) -> dict:
    """
    Retorna el espectro exacto de emociones detectadas por la IA.
    Útil si el orquestador XGBoost quiere medir la "Certeza del Miedo".
    """
    if not headline or not headline.strip():
        return {'positive': 0.0, 'negative': 0.0, 'neutral': 1.0}
        
    _load_finbert()
    inputs = _tokenizer(headline, return_tensors="pt", truncation=True, padding=True).to(_device)
    
    with torch.no_grad():
        outputs = _model(**inputs)
        
    probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)[0]
    
    return {
        'positive': probabilities[0].item(),
        'negative': probabilities[1].item(),
        'neutral': probabilities[2].item(),
    }
