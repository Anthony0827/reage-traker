"""
Insult Detection Module (Real-time Spanish STT via Vosk)

This module provides real-time detection of Spanish insults using Vosk
speech-to-text and a custom Spanish stemmer for lexicon matching.

Privacy: No transcript text is ever displayed to the user.
"""

import json
import os
import csv
import re
import time
import vosk
import sounddevice as sd
from typing import Optional, List, Dict, Any


class SpanishStemmer:
    """
    Pure Python Spanish stemmer using suffix stripping.
    
    Covers common Spanish verb/person/number inflections for insult base forms.
    No external dependencies (no NLTK).
    """
    
    # Sufijos de inflexión (sin guion). IMPORTANTE: van ordenados de MÁS LARGO
    # a más corto para que "tontos" elimine "os" antes que "o" y todas las
    # formas (tonto/tonta/tontos/tontas) colapsen al mismo radical "tont".
    # (Bug anterior: los sufijos llevaban guion "-os" y endswith no casaba
    #  nunca con palabras reales, así que NO se normalizaba nada.)
    SUFFIXES = (
        "iendo", "ando", "amos", "áis", "ais",
        "os", "as", "es", "an", "en",
        "ar", "er", "ir",
        "o", "a",
    )

    @staticmethod
    def stem(word: str) -> str:
        """
        Strip longest matching Spanish suffix from word.

        Args:
            word: Input word to stem

        Returns:
            Stemmed word (lowercase)
        """
        if not word:
            return ""

        word = word.lower().strip()

        # Try each suffix in order (longest first)
        for suffix in SpanishStemmer.SUFFIXES:
            if word.endswith(suffix):
                stem = word[:-len(suffix)]
                # Basic validation: stem should have at least 2 chars
                if len(stem) >= 2:
                    return stem

        # No suffix matched, return original
        return word


class InsultDetector:
    """
    Real-time Spanish insult detector using Vosk STT.
    
    Architecture:
    - Independent sounddevice.InputStream at 16kHz mono
    - Vosk KaldiRecognizer for speech recognition
    - Pre-stemmed lexicon set for O(1) matching
    - No debounce (increment per match)
    
    Privacy guarantee: No transcript text ever displayed.
    """
    
    BLOCK_SIZE = 1024  # frames per capture block
    
    def __init__(self, model_path: Optional[str] = None,
                 device_index: Optional[int] = None):
        """
        Initialize the insult detector.

        Args:
            model_path: Path to Vosk model directory. If None, uses
                       RAGE_VOSK_MODEL env var or default 'models/vosk-es'.
            device_index: Índice del micrófono (sounddevice) que debe escuchar.
                       None = micrófono predeterminado del sistema. CLAVE: si el
                       usuario eligió un micro concreto en la app, hay que pasarlo
                       aquí o el detector escucharía otro micro y no oiría nada.

        Attributes:
            level: Always 0.0 (no volume tracking)
            is_insult_active: False (insults don't affect mic indicator)
            last_error: Empty string (set on failure)
            _insult_count: Total insults detected
            _insult_peak_count: Peak insults in single block
            _running: Whether detector is active
            _stream: sounddevice stream instance
            _recognizer: Vosk KaldiRecognizer instance
            _lexicon_stems: Set of pre-stemmed insult base forms
            _model_name: Name of loaded model
        """
        self.level: float = 0.0
        self.is_insult_active: bool = False
        self.last_error: str = ""
        self._insult_count: int = 0
        self._insult_peak_count: int = 0
        self._running: bool = False
        self._stream = None
        self._recognizer = None
        self._lexicon_stems: set = set()
        self._model_name: str = ""
        self._last_detected: Dict[str, float] = {}  # stem → timestamp, para debounce
        self._device_index: Optional[int] = device_index

        # Determine model path
        if model_path is None:
            model_path = os.environ.get("RAGE_VOSK_MODEL", "models/vosk-es")
        self._model_path = model_path
    
    def _load_lexicon(self, lexicon_path: str) -> bool:
        """
        Load and pre-stem insult lexicon from CSV file.
        
        Args:
            lexicon_path: Path to insults.csv
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(lexicon_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0].strip():
                        insult = row[0].strip().lower()
                        # Pre-stem all insults at load time
                        stem = SpanishStemmer.stem(insult)
                        self._lexicon_stems.add(stem)
            return True
        except Exception as e:
            print(f"Warning: Could not load lexicon: {e}")
            return False
    
    def _callback(self, indata, frames: int, time_info, status):
        """
        Audio callback para procesamiento en tiempo real.

        indata: array numpy int16 de sounddevice (NO bytes).
        Vosk espera bytes PCM16 mono 16kHz → hay que convertir.
        Solo procesamos resultados FINALES para evitar doble conteo.
        Debounce: mínimo 2 s entre detecciones del mismo stem.
        """
        if not self._recognizer:
            return

        # Convertir numpy int16 → bytes PCM que acepta Vosk
        audio_bytes = indata.flatten().tobytes()

        if self._recognizer.AcceptWaveform(audio_bytes):
            result = json.loads(self._recognizer.Result())
            text = result.get("text", "")
            if text:
                self._process_text(text)

    def _process_text(self, text: str) -> None:
        """Tokeniza, stemiza y compara contra el léxico con debounce."""
        now = time.time()
        for token in text.split():
            clean = re.sub(r'[^\w]', '', token).lower().strip()
            if not clean:
                continue
            stemmed = SpanishStemmer.stem(clean)
            if stemmed not in self._lexicon_stems:
                continue
            # Debounce: ignorar el mismo stem si fue detectado hace < 2 s
            if now - self._last_detected.get(stemmed, 0) < 2.0:
                continue
            self._last_detected[stemmed] = now
            self._insult_count += 1
            if self._insult_count > self._insult_peak_count:
                self._insult_peak_count = self._insult_count
    
    def start(self) -> bool:
        """
        Start audio streaming and model loading.
        
        Lifecycle:
        1. Load model from RAGE_VOSK_MODEL or default path
        2. Initialize Vosk KaldiRecognizer at 16kHz
        3. Load and pre-stem lexicon from data/insultos.csv
        4. Create sounddevice.InputStream with callback
        5. Return True on success, False on failure
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            # Update model path attribute
            self._model_path = os.environ.get("RAGE_VOSK_MODEL", self._model_path)
            self._model_name = os.path.basename(self._model_path)
            
            # Cargar modelo Vosk (el idioma ya está integrado en el modelo)
            model = vosk.Model(self._model_path)

            # KaldiRecognizer a 16kHz — no existe SetLanguage, el modelo ya es español
            self._recognizer = vosk.KaldiRecognizer(model, 16000)

            # Cargar léxico
            lexicon_path = os.path.join(os.path.dirname(__file__),
                                        '..', 'data', 'insultos.csv')
            if not self._load_lexicon(lexicon_path):
                self.last_error = "lexicon not found"
                return False

            # Stream de audio: sounddevice llama al callback con arrays numpy.
            # Abrimos en el micro elegido por el usuario; si ese índice falla
            # (p. ej. no soporta 16 kHz), reintentamos en el predeterminado
            # para no quedarnos sin detección por una incompatibilidad puntual.
            def _open(device):
                return sd.InputStream(
                    samplerate=16000,
                    channels=1,
                    dtype='int16',
                    device=device,
                    callback=self._callback,
                )

            try:
                self._stream = _open(self._device_index)
                self._stream.start()
            except Exception as exc_dev:
                if self._device_index is None:
                    raise
                print(f"[!] Insultos: el micro {self._device_index} no se pudo "
                      f"abrir ({exc_dev}); uso el predeterminado.")
                self._stream = _open(None)
                self._stream.start()

            self._running = True
            self.is_insult_active = True

            return True

        except Exception as e:
            self.last_error = f"stream: {str(e)}"
            self._running = False
            return False
    
    def stop(self):
        """
        Stop audio streaming and cleanup resources.
        
        Closes the sounddevice stream and resets state flags.
        Does not reset counters (use reset() for that).
        """
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        
        if self._recognizer:
            self._recognizer = None
        
        self._running = False
        self.is_insult_active = False
    
    def reset(self):
        """Resetea contadores sin cerrar el stream. También limpia el debounce cache."""
        self._insult_count = 0
        self._insult_peak_count = 0
        self._last_detected.clear()
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get current summary statistics.
        
        Returns:
            Dictionary with keys:
            - 'insult_count': Total insults detected (int)
            - 'insult_peak_count': Peak insults in single block (int)
            - 'insult_model_name': Name of loaded model (str)
            - 'last_error': Last error message (str)
        """
        return {
            'insult_count': self._insult_count,
            'insult_peak_count': self._insult_peak_count,
            'insult_model_name': self._model_name,
            'last_error': self.last_error
        }
    
    def list_insults(self) -> List[str]:
        """
        Return list of matched insult base forms.
        
        Returns:
            List of insult base forms from current lexicon.
            (Not transcript data - just the lexicon entries)
        """
        return sorted(list(self._lexicon_stems))
