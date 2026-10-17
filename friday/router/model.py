"""Trained router (Phase 6): the DistilBERT intent classifier in models/router_v2.

On by default. Set FRIDAY_ROUTER_MODEL=0 (or false/off/no) to switch it off; it is read when the
graph is built.
The model loads in a background thread, so a turn never waits for torch: until it is ready,
classify() returns None and the turn goes to the rules and the LLM as before.
If models/router_v2 is missing or fails to load, it stays that way: one log line, no crash.

It answers with (class, confidence). Classes: doc_qa, lists_notes, math_time, music, other,
timers_reminders. Input is the CLEAN text from friday.router.router.normalize.
DEFAULT_THRESHOLD is a provisional value chosen from the MASSIVE dev split (P6-02), not tuned
on real voice data: re-check it once the logged predictions have been labelled.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "router_v2"
MAXLEN = 64
DEFAULT_THRESHOLD = 0.9
ENV_FLAG = "FRIDAY_ROUTER_MODEL"
OFF_VALUES = ("0", "false", "off", "no")
CLASSES = {"doc_qa", "lists_notes", "math_time", "music", "other", "timers_reminders"}

_shared: dict = {}
_shared_lock = threading.Lock()


class ModelClassifier:
    def __init__(self, model_dir: Path = MODEL_DIR, background: bool = True) -> None:
        self.model_dir = Path(model_dir)
        self.error = ""  # the error type if loading failed, else empty
        self._torch = None
        self._tok = None
        self._model = None
        self._names: list[str] = []
        self._run_lock = threading.Lock()  # one forward pass at a time
        self._ready = threading.Event()
        if background:
            threading.Thread(target=self._load, daemon=True, name="router-model-load").start()
        else:
            self._load()

    @property
    def ready(self) -> bool:
        return self._ready.is_set()

    def _load(self) -> None:
        if not (self.model_dir / "config.json").is_file():  # fresh clone: skip the torch import
            self.error = "ModelNotFound"
            print(
                f"Router model not found at {self.model_dir}. Friday keeps using rules + LLM "
                f"(set {ENV_FLAG}=0 to stop looking)."
            )
            return
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            tok = AutoTokenizer.from_pretrained(str(self.model_dir), local_files_only=True)
            model = AutoModelForSequenceClassification.from_pretrained(
                str(self.model_dir), local_files_only=True
            )
            model.eval()
            names = [model.config.id2label[i] for i in range(model.config.num_labels)]
        except Exception as exc:  # noqa: BLE001 - a missing model must never break Friday
            self.error = type(exc).__name__
            print(f"Router model not loaded ({self.error}). Friday keeps using rules + LLM.")
            return
        self._torch, self._tok, self._model, self._names = torch, tok, model, names
        self._ready.set()
        print("Router model ready.")

    def classify(self, clean: str) -> tuple[str, float] | None:
        """(class, confidence), or None when there is nothing to classify or it isn't ready."""
        if not clean.strip() or not self._ready.is_set():
            return None
        try:
            with self._run_lock:
                enc = self._tok(clean, return_tensors="pt", truncation=True, max_length=MAXLEN)
                with self._torch.inference_mode():
                    logits = self._model(
                        input_ids=enc["input_ids"], attention_mask=enc["attention_mask"]
                    ).logits
                probs = self._torch.softmax(logits, dim=-1)[0]
                conf, idx = probs.max(dim=0)
            label = self._names[int(idx)]
        except Exception as exc:  # noqa: BLE001 - one bad turn must fall back to the LLM
            print(f"Router model failed on a turn ({type(exc).__name__}).")
            return None
        return (label if label in CLASSES else "other"), float(conf)


def router_model_enabled() -> bool:
    """On unless FRIDAY_ROUTER_MODEL is 0/false/off/no. Unset or empty means on."""
    return os.environ.get(ENV_FLAG, "").strip().lower() not in OFF_VALUES


def get_default_classifier() -> ModelClassifier | None:
    """The shared classifier unless FRIDAY_ROUTER_MODEL turns it off, else None. Built once."""
    if not router_model_enabled():
        return None
    with _shared_lock:
        if "classifier" not in _shared:
            _shared["classifier"] = ModelClassifier()
        return _shared["classifier"]