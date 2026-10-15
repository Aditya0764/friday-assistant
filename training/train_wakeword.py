"""T-09: train the "hey friday" wake word (openWakeWord features + own trainer).

Runs on Kaggle (GPU). With --fake it runs a tiny CPU test on stand-in data.

  python training/train_wakeword.py setup   # once: venv, pinned packages, repos
  python training/train_wakeword.py run     # everything else (re-runnable)

Stages inside `run`: data -> generate -> real -> augment -> train -> export.
Each stage checks its own output, so a re-run skips what is already done.
Real recordings come from the private Kaggle dataset (folders pos/ and neg/).
Plan and sources: claude/Wakeword_Study.md. The trainer follows the design of
the MIT-licensed alfiedennen/openwakeword-colab-2026 notebook (own code).
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORK = Path(os.environ.get("WW_WORK", "/tmp/ww"))
OUT = Path(os.environ.get("WW_OUT", "/kaggle/working/ww_out"))
VENV = WORK / "venv"
OWW = WORK / "openWakeWord"
PSG = WORK / "piper-sample-generator"
OWW_COMMIT = "368c03716d1e92591906a84949bc477f3a834455"
PSG_COMMIT = "c9d824c0e2cce8bdeb000c219dc9cbc84df086ea"
PSG_MODEL = PSG / "models" / "en_US-libritts_r-medium.pt"
GH = "https://github.com"
PSG_MODEL_URL = (
    f"{GH}/rhasspy/piper-sample-generator/releases/download/v2.0.0/"
    "en_US-libritts_r-medium.pt"
)
OWW_MODELS_URL = f"{GH}/dscripka/openWakeWord/releases/download/v0.5.1"
HF = "https://huggingface.co/datasets/davidscripka"
ACAV_URL = (
    f"{HF}/openwakeword_features/resolve/main/"
    "openwakeword_features_ACAV100M_2000_hrs_16bit.npy"
)
FMA_URL = "https://os.unil.cloud.switch.ch/fma/fma_small.zip"

NAME = "hey_friday"
PHRASE = "hey friday"
NEAR_MISSES = [
    "friday",
    "it's friday today",
    "happy friday",
    "see you on friday",
    "hey friend",
    "hey freddy",
    "hey frieda",
    "hey fry day",
    "hey fred",
    "friday night",
    "hey fred day",
    "hey friday night",
]
PINS = [
    "torch==2.4.1",
    "torchaudio==2.4.1",
    "numpy<2",
    "scipy<1.15",
    "pyarrow<18",
    "huggingface_hub<0.30",
    "datasets==2.21.0",
    "mutagen==1.47.0",
    "audiomentations==0.33.0",
    "torch_audiomentations",
    "torchinfo",
    "torchmetrics",
    "pyyaml",
    "tqdm",
    "soundfile",
    "pronouncing",
    "onnxruntime",
    "onnx",
    "onnxscript",
    "speechbrain",
    "acoustics",
    "requests",
    "webrtcvad-wheels",
    "piper-tts",
]
CONSTRAINTS = [
    "torch==2.4.1",
    "torchaudio==2.4.1",
    "triton==3.0.0",
    "numpy<2",
    "scipy<1.15",
    "pyarrow<18",
    "huggingface_hub<0.30",
]


def sh(cmd, check=True):
    print("$", cmd, flush=True)
    return subprocess.run(cmd, shell=True, check=check)


def stamp(label, t0):
    print(f"[time] {label}: {(time.time() - t0) / 60:.1f} min", flush=True)


def disk():
    sh(f"df -h {WORK.parent} | tail -1", check=False)


# ---------------------------------------------------------------- setup ----


def setup(args):
    t0 = time.time()
    WORK.mkdir(parents=True, exist_ok=True)
    sh("pip install -q uv")
    if not (VENV / "bin" / "python").exists():
        sh(f"uv venv --python 3.11 {VENV}")
    cons = WORK / "constraints.txt"
    cons.write_text("\n".join(CONSTRAINTS) + "\n")
    py = VENV / "bin" / "python"
    sh(f"uv pip install --python {py} -c {cons} " + " ".join(f'"{p}"' for p in PINS))
    if not OWW.exists():
        sh(f"git clone -q {GH}/dscripka/openWakeWord {OWW}")
    sh(f"git -C {OWW} checkout -q {OWW_COMMIT}")
    sh(f"uv pip install --python {py} -c {cons} --no-deps -e {OWW}")
    if not PSG.exists():
        sh(f"git clone -q {GH}/rhasspy/piper-sample-generator {PSG}")
    sh(f"git -C {PSG} checkout -q {PSG_COMMIT}")
    if not PSG_MODEL.exists() or PSG_MODEL.stat().st_size < 100_000_000:
        sh(f"curl -sSL --retry 5 -o {PSG_MODEL} {PSG_MODEL_URL}")
    models = OWW / "openwakeword" / "resources" / "models"
    models.mkdir(parents=True, exist_ok=True)
    for f in ["embedding_model.onnx", "melspectrogram.onnx"]:
        if not (models / f).exists() or (models / f).stat().st_size < 1000:
            sh(f"curl -sSL --retry 5 -o {models / f} {OWW_MODELS_URL}/{f}")
    patch_generate_samples()
    sh(f"{py} -m pip --version", check=False)
    sh(f"uv pip freeze --python {py} > {WORK / 'pip_freeze.txt'}")
    stamp("setup", t0)
    print("SETUP DONE. Next: python training/train_wakeword.py run")


def patch_generate_samples():
    """train.py calls generate_samples() without `model`: give it a default."""
    path = PSG / "generate_samples.py"
    text = path.read_text()
    old = "    model: Union[str, Path],\n"
    new = f'    model: Union[str, Path] = "{PSG_MODEL}",\n'
    if old in text:
        path.write_text(text.replace(old, new, 1))
        print("patched generate_samples.py (default model path)")
    elif str(PSG_MODEL) in text:
        print("generate_samples.py already patched")
    else:
        raise SystemExit("generate_samples.py layout changed, patch failed")


# ------------------------------------------------------------ run helpers --


def reexec_in_venv():
    py = str(VENV / "bin" / "python")
    if os.path.exists(py) and Path(sys.prefix).resolve() != VENV.resolve():
        os.execv(py, [py, *sys.argv])


def find_data(args):
    if args.data:
        return Path(args.data)
    hits = [Path(p).parent for p in glob.glob("/kaggle/input/**/pos", recursive=True)]
    hits = [h for h in hits if (h / "neg").is_dir()]
    if not hits:
        raise SystemExit("Real-data folder with pos/ and neg/ not found (--data).")
    return hits[0]


def read_wav(path):
    import numpy as np
    import soundfile as sf

    data, rate = sf.read(str(path), dtype="int16")
    if data.ndim > 1:
        data = data[:, 0]
    if rate != 16000:
        raise ValueError(f"{path} is {rate} Hz, expected 16000")
    return np.asarray(data, dtype=np.int16)


def write_wav(path, data):
    import numpy as np
    import soundfile as sf

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.asarray(data, dtype=np.int16), 16000, subtype="PCM_16")


def trim_to_speech(x, head=0.15, tail=0.10, max_len=2.0):
    """Cut a recording down to the phrase (+ a little margin). None = no speech."""
    import numpy as np

    frame = 320
    n = len(x) // frame
    if n < 5:
        return None
    rms = np.sqrt((x[: n * frame].astype(np.float32).reshape(n, frame) ** 2).mean(1))
    floor = float(np.percentile(rms, 10))
    active = np.flatnonzero(rms > max(floor * 4, 300))
    if len(active) < 10:
        return None
    first, last = active[0] * frame, (active[-1] + 1) * frame
    start = max(0, first - int(head * 16000))
    end = min(len(x), last + int(tail * 16000))
    if end - start > int(max_len * 16000):
        start = end - int(max_len * 16000)
    clip = x[start:end].astype(np.float32)
    peak = float(np.abs(clip).max())
    if peak < 1:
        return None
    return (clip * (0.8 * 32767 / peak)).astype(np.int16)


# ------------------------------------------------------------------ config -


def paths(args):
    base = WORK / "out" / NAME
    return {
        "base": base,
        "pos_train": base / "positive_train",
        "pos_test": base / "positive_test",
        "neg_train": base / "negative_train",
        "neg_test": base / "negative_test",
        "cfg": WORK / "hey_friday.yaml",
        "rir": WORK / "rirs",
        "bg": WORK / "background",
        "acav_train": WORK / "acav_train.npy",
        "acav_val": WORK / "acav_val.npy",
    }


def write_config(args, p):
    import yaml

    cfg = {
        "target_phrase": [PHRASE],
        "model_name": NAME,
        "custom_negative_phrases": NEAR_MISSES,
        "n_samples": args.n_samples,
        "n_samples_val": args.n_val,
        "tts_batch_size": args.tts_batch,
        "piper_sample_generator_path": str(PSG),
        "augmentation_rounds": 1,
        "augmentation_batch_size": 16,
        "background_paths": [str(p["bg"])],
        "background_paths_duplication_rate": [1],
        "rir_paths": [str(p["rir"])],
        "output_dir": str(WORK / "out"),
    }
    Path(p["cfg"]).write_text(yaml.dump(cfg, sort_keys=False))
    return cfg


def run_oww(flag, p):
    cmd = f"{sys.executable} {OWW / 'openwakeword' / 'train.py'}"
    sh(f"{cmd} --training_config {p['cfg']} {flag}")


# ------------------------------------------------------- stage: data files --


def stage_data(args, p):
    """RIRs, background audio and the big negative-feature arrays."""
    t0 = time.time()
    p["rir"].mkdir(parents=True, exist_ok=True)
    p["bg"].mkdir(parents=True, exist_ok=True)
    if args.fake:
        fake_data(p)
    else:
        real_rirs(p)
        real_acav(p)
        if not args.no_fma:
            try:
                real_fma(p)
            except Exception as err:  # noqa: BLE001 - background music is optional
                print(f"FMA background skipped: {err}")
    stamp("data files", t0)
    disk()


def fake_data(p):
    import numpy as np

    rng = np.random.default_rng(0)
    if not list(p["rir"].glob("*.wav")):
        for i in range(8):
            t = np.arange(4000) / 16000
            ir = rng.normal(size=4000) * np.exp(-t * (20 + 10 * i))
            write_wav(p["rir"] / f"{i}.wav", ir / abs(ir).max() * 20000)
    if not list(p["bg"].glob("*.wav")):
        for i in range(4):
            noise = np.cumsum(rng.normal(size=16000 * 8))
            noise = noise - np.convolve(noise, np.ones(200) / 200, mode="same")
            write_wav(p["bg"] / f"fake_{i}.wav", noise / abs(noise).max() * 6000)
    if not p["acav_train"].exists():
        np.save(p["acav_train"], rng.normal(size=(300, 16, 96)).astype("float16"))
        np.save(p["acav_val"], rng.normal(size=(4000, 96)).astype("float16"))


def real_rirs(p):
    import numpy as np
    from scipy.signal import resample_poly

    if len(list(p["rir"].glob("*.wav"))) >= 200:
        return
    # Kaggle shares IPs, so Hugging Face rate-limits (429): few threads + retries.
    os.environ["HF_DATASETS_MULTITHREADING_MAX_WORKERS"] = "2"
    import datasets

    ds = None
    for attempt in range(1, 9):
        try:
            ds = datasets.load_dataset(
                "davidscripka/MIT_environmental_impulse_responses", split="train"
            )
            break
        except Exception as err:  # noqa: BLE001 - retry on any download error
            wait = 30 * attempt
            print(f"RIR download try {attempt} failed ({str(err)[:80]}); wait {wait}s")
            time.sleep(wait)
    if ds is None:
        raise SystemExit("Could not download the RIR dataset after 8 tries")
    for i, row in enumerate(ds):
        audio = row["audio"]
        arr = np.asarray(audio["array"], dtype=np.float32)
        if audio["sampling_rate"] != 16000:
            arr = resample_poly(arr, 16000, audio["sampling_rate"])
        write_wav(p["rir"] / f"{i:04d}.wav", np.clip(arr * 32767, -32768, 32767))
    print("RIR files:", len(list(p["rir"].glob("*.wav"))))


def real_acav(p):
    import numpy as np

    if p["acav_train"].exists() and p["acav_val"].exists():
        return
    big = WORK / "acav_full.npy"
    sh(f"curl -L --retry 8 -C - -sS -o {big} {ACAV_URL}")
    arr = np.load(big, mmap_mode="r")
    print("ACAV source", arr.shape, arr.dtype)
    n_train = len(arr) // 10
    n_val = len(arr) // 100
    np.save(p["acav_train"], np.array(arr[:n_train]))
    val = np.array(arr[n_train : n_train + n_val])
    np.save(p["acav_val"], val.reshape(-1, val.shape[-1]))
    del arr
    big.unlink()


def real_fma(p, limit=600):
    import soundfile as sf  # noqa: F401  (checks the venv has it)

    if len(list(p["bg"].glob("fma_*.wav"))) >= limit:
        return
    zip_path = WORK / "fma_small.zip"
    sh(f"curl -L --retry 8 -C - -sS -o {zip_path} {FMA_URL}")
    out = WORK / "fma"
    sh(f"unzip -q -o {zip_path} -d {out}")
    zip_path.unlink()
    mp3s = sorted(glob.glob(f"{out}/**/*.mp3", recursive=True))[:limit]
    for i, mp3 in enumerate(mp3s):
        dst = p["bg"] / f"fma_{i:04d}.wav"
        if not dst.exists():
            sh(f'ffmpeg -y -loglevel error -i "{mp3}" -ac 1 -ar 16000 {dst}', False)
    shutil.rmtree(out, ignore_errors=True)
    print("FMA background files:", len(list(p["bg"].glob("fma_*.wav"))))


# --------------------------------------------------- stage: synthetic clips -


def stage_generate(args, p):
    t0 = time.time()
    run_oww("--generate_clips", p)
    resample_dirs(p)
    stamp("generate clips", t0)


def resample_dirs(p):
    import soundfile as sf
    from scipy.signal import resample_poly

    for key in ["pos_train", "pos_test", "neg_train", "neg_test"]:
        done = 0
        for f in Path(p[key]).glob("*.wav"):
            data, rate = sf.read(str(f), dtype="float32")
            if rate == 16000:
                continue
            sf.write(str(f), resample_poly(data, 16000, rate), 16000)
            done += 1
        print(f"resampled {done} files in {key}")


# ------------------------------------------------------ stage: real clips ---


def stage_real(args, p):
    """Add your real recordings to the training clips (positives, negatives)."""
    import numpy as np

    data = find_data(args)
    rng = np.random.default_rng(1)
    for d in Path(p["pos_train"]).glob("real_*.wav"):
        d.unlink()
    for d in Path(p["neg_train"]).glob("real_*.wav"):
        d.unlink()
    pos = []
    for f in sorted(glob.glob(str(data / "pos" / "*" / "*.wav"))):
        clip = trim_to_speech(read_wav(f))
        if clip is not None:
            pos.append(clip)
    near = []
    for f in sorted(glob.glob(str(data / "neg" / "miss_*" / "*.wav"))):
        clip = trim_to_speech(read_wav(f))
        if clip is not None:
            near.append(clip)
    print(f"real positives kept: {len(pos)}, near-miss clips kept: {len(near)}")
    if not pos:
        raise SystemExit("no real positives found")
    for i, clip in enumerate(pos):
        for k in range(args.real_copies):
            write_wav(p["pos_train"] / f"real_{i:03d}_{k:02d}.wav", clip)
    for i, clip in enumerate(near):
        for k in range(args.real_copies):
            write_wav(p["neg_train"] / f"real_near_{i:03d}_{k:02d}.wav", clip)
    # long negative recordings: random 2 s windows, plus 30 s pieces as background
    made = 0
    for f in sorted(glob.glob(str(data / "neg" / "*" / "part_*.wav"))):
        if "/miss_" in f.replace("\\", "/"):
            continue
        x = read_wav(f)
        per_part = max(1, args.real_neg_windows // 3)
        for _ in range(per_part):
            s = int(rng.integers(0, max(1, len(x) - 32000)))
            write_wav(p["neg_train"] / f"real_talk_{made:05d}.wav", x[s : s + 32000])
            made += 1
        stem = Path(f).stem
        for j in range(0, len(x) - 480000 + 1, 480000):
            write_wav(p["bg"] / f"talk_{stem}_{j // 480000:02d}.wav", x[j : j + 480000])
    print(f"real negative windows: {made}")
    meta = {"real_positives": len(pos), "real_near_miss": len(near), "windows": made}
    (OUT / "real_data_summary.json").write_text(json.dumps(meta))


# ------------------------------------------------------- stage: augment -----


def stage_augment(args, p):
    t0 = time.time()
    for f in glob.glob(str(p["base"] / "*_features_*.npy")):
        os.remove(f)  # a crashed earlier run can leave partial files behind
    run_oww("--augment_clips", p)
    for f in sorted(glob.glob(str(p["base"] / "*_features_*.npy"))):
        print(f, round(os.path.getsize(f) / 1e6, 1), "MB")
    stamp("augment + features", t0)


# --------------------------------------------------------- stage: train -----


class Trainer:
    """Small DNN on (16, 96) openWakeWord features, with the usual curriculum."""

    def __init__(self, args, p):
        import numpy as np
        import torch

        self.args = args
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        load = lambda n: torch.from_numpy(np.load(p["base"] / n).astype("float32")).to(
            self.dev
        )
        self.pos = load("positive_features_train.npy")
        self.neg = load("negative_features_train.npy")
        self.pos_test = load("positive_features_test.npy")
        self.neg_test = load("negative_features_test.npy")
        acav = np.load(p["acav_train"])
        self.acav = torch.from_numpy(acav).to(self.dev)
        val = np.load(p["acav_val"]).astype("float32")
        self.val_hours = len(val) * 0.08 / 3600
        win = np.lib.stride_tricks.sliding_window_view(val, (16, 96))[:, 0]
        self.val_windows = torch.from_numpy(np.ascontiguousarray(win))
        print("positives", tuple(self.pos.shape), "negatives", tuple(self.neg.shape))
        print("acav", tuple(self.acav.shape), f"validation hours {self.val_hours:.2f}")
        self.model = self.build().to(self.dev)
        self.history = []
        self.saved = []

    @staticmethod
    def build():
        from torch import nn

        return nn.Sequential(
            nn.Flatten(),
            nn.Linear(16 * 96, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
            nn.Linear(128, 1),
        )

    def acav_batch(self, k):
        import torch

        n, t, _ = self.acav.shape
        rows = torch.randint(0, n, (k,), device=self.dev)
        starts = torch.randint(0, t - 16 + 1, (k,), device=self.dev)
        idx = starts[:, None] + torch.arange(16, device=self.dev)[None]
        return self.acav[rows[:, None], idx].float()

    def batch(self):
        import torch

        a = self.args
        pi = torch.randint(0, len(self.pos), (a.b_pos,), device=self.dev)
        ni = torch.randint(0, len(self.neg), (a.b_neg,), device=self.dev)
        x = torch.cat([self.pos[pi], self.neg[ni], self.acav_batch(a.b_acav)])
        y = torch.cat(
            [
                torch.ones(a.b_pos, device=self.dev),
                torch.zeros(a.b_neg + a.b_acav, device=self.dev),
            ]
        )
        return x, y

    def validate(self, label):
        import copy

        import torch

        self.model.eval()
        with torch.no_grad():
            recall = (torch.sigmoid(self.model(self.pos_test)) >= 0.5).float().mean()
            neg_ok = (torch.sigmoid(self.model(self.neg_test)) < 0.5).float().mean()
            n_fp = 0
            for i in range(0, len(self.val_windows), 4096):
                chunk = self.val_windows[i : i + 4096].to(self.dev)
                n_fp += int((torch.sigmoid(self.model(chunk)) >= 0.5).sum())
        self.model.train()
        row = {
            "label": label,
            "recall": float(recall),
            "neg_ok": float(neg_ok),
            "n_fp": n_fp,
            "fp_per_hour": n_fp / max(self.val_hours, 1e-6),
        }
        self.history.append(row)
        if len(self.history) >= 3:
            fps = [h["n_fp"] for h in self.history]
            recs = [h["recall"] for h in self.history]
            import numpy as np

            if n_fp <= np.percentile(fps, 50) and row["recall"] >= np.percentile(
                recs, 5
            ):
                self.saved.append((copy.deepcopy(self.model.state_dict()), row))
        print(
            f"  [{label}] recall {row['recall']:.3f} fp/hr {row['fp_per_hour']:.2f}"
            f" neg_ok {row['neg_ok']:.3f}",
            flush=True,
        )

    def stage(self, idx, steps, lr, max_w):
        import math

        import numpy as np
        import torch

        opt = torch.optim.Adam(self.model.parameters(), lr=lr)
        loss_fn = torch.nn.BCEWithLogitsLoss(reduction="none")
        weights = np.linspace(1.0, max_w, steps)
        warm, hold = max(1, steps // 5), steps // 3
        val_steps = set(np.linspace(0, steps - 1, 20).astype(int))
        t0 = time.time()
        pending = []
        print(f"stage {idx}: {steps} steps, lr {lr}, max negative weight {max_w}")
        for step in range(steps):
            if step < warm:
                lr_now = lr * (step + 1) / warm
            elif step < warm + hold:
                lr_now = lr
            else:
                t = (step - warm - hold) / max(1, steps - warm - hold)
                lr_now = lr * 0.5 * (1 + math.cos(math.pi * min(1.0, t)))
            for g in opt.param_groups:
                g["lr"] = lr_now
            x, y = self.batch()
            logits = self.model(x).squeeze(-1)
            prob = torch.sigmoid(logits)
            keep = ((y == 0) & (prob >= 0.001)) | ((y == 1) & (prob < 0.999))
            if keep.any():
                w = torch.where(y[keep] > 0.5, 1.0, float(weights[step]))
                pending.append((logits[keep], y[keep], w))
                if sum(len(t[0]) for t in pending) >= 128:
                    lg = torch.cat([t[0] for t in pending])
                    yy = torch.cat([t[1] for t in pending])
                    ww = torch.cat([t[2] for t in pending])
                    loss = (loss_fn(lg, yy) * ww).mean()
                    opt.zero_grad()
                    loss.backward()
                    opt.step()
                    pending.clear()
            if step in val_steps:
                self.validate(f"stage {idx} step {step}/{steps}")
        print(f"stage {idx} done in {(time.time() - t0) / 60:.1f} min", flush=True)

    def fit(self):
        a = self.args
        self.stage(1, a.steps, 1e-4, a.max_neg_weight)
        best = min(h["fp_per_hour"] for h in self.history)
        w = a.max_neg_weight * (2 if best > a.target_fp else 1)
        self.stage(2, max(a.steps // 10, 200), 1e-5, w)
        self.stage(3, max(a.steps // 10, 200), 1e-6, w)

    def final_state(self):
        import numpy as np
        import torch

        if not self.saved:
            print("no checkpoint saved, using the last weights")
            return self.model.state_dict()
        accs = [r["recall"] for _, r in self.saved]
        fps = [r["fp_per_hour"] for _, r in self.saved]
        ok = [
            (sd, r)
            for sd, r in self.saved
            if r["recall"] >= np.percentile(accs, 90)
            and r["fp_per_hour"] <= np.percentile(fps, 10)
        ]
        if not ok:
            ok = [min(self.saved, key=lambda t: (t[1]["fp_per_hour"], -t[1]["recall"]))]
        print(f"averaging {len(ok)} of {len(self.saved)} saved checkpoints")
        keys = ok[0][0].keys()
        return {k: torch.stack([sd[k].float() for sd, _ in ok]).mean(0) for k in keys}


def stage_train(args, p):
    t0 = time.time()
    tr = Trainer(args, p)
    tr.fit()
    state = tr.final_state()
    import torch

    torch.save(state, OUT / "final_state.pt")
    (OUT / "history.json").write_text(json.dumps(tr.history, indent=1))
    tr.model.load_state_dict(state)
    export_onnx(tr, p)
    stamp("train + export", t0)


def export_onnx(tr, p):
    import numpy as np
    import onnxruntime as ort
    import torch

    class WithSigmoid(torch.nn.Module):
        def __init__(self, base):
            super().__init__()
            self.base = base

        def forward(self, x):
            return torch.sigmoid(self.base(x))

    model = WithSigmoid(tr.model).to("cpu").eval()
    path = OUT / f"{NAME}.onnx"
    dummy = torch.randn(1, 16, 96)
    torch.onnx.export(
        model,
        dummy,
        str(path),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        opset_version=14,
    )
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    pos = tr.pos_test.cpu().numpy()[:200]
    scores = sess.run(None, {sess.get_inputs()[0].name: pos})[0].flatten()
    print(f"wrote {path} ({path.stat().st_size / 1e3:.0f} KB)")
    print(f"synthetic test positives: mean score {scores.mean():.3f}")
    extra = path.with_suffix(".onnx.data")
    print("external data file:", extra.exists())
    np.save(OUT / "score_check.npy", scores)


# ----------------------------------------------------- stage: listen/check --


def stage_listen(args, p):
    """Copy a few generated clips so a human can listen before trusting them."""
    import random

    folder = OUT / "listen"
    folder.mkdir(parents=True, exist_ok=True)
    random.seed(2)
    for key, label, n in [("pos_test", "pos", 10), ("neg_test", "neg", 8)]:
        files = sorted(Path(p[key]).glob("*.wav"))
        for i, f in enumerate(random.sample(files, min(n, len(files)))):
            shutil.copy(f, folder / f"{label}_{i:02d}.wav")
    print("listening samples in", folder)


def stage_package(args, p):
    for f in [p["cfg"], WORK / "pip_freeze.txt"]:
        if Path(f).exists():
            shutil.copy(f, OUT / Path(f).name)
    archive = shutil.make_archive(str(OUT.parent / "ww_result"), "zip", OUT)
    print("result archive:", archive)


# ----------------------------------------------------------------- main -----


def run(args):
    reexec_in_venv()
    OUT.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLBACKEND", "Agg")
    p = paths(args)
    for d in [p["base"], WORK / "out"]:
        d.mkdir(parents=True, exist_ok=True)
    write_config(args, p)
    stages = (
        args.stages.split(",")
        if args.stages != "all"
        else [
            "data",
            "generate",
            "real",
            "listen",
            "augment",
            "train",
            "package",
        ]
    )
    table = {
        "data": stage_data,
        "generate": stage_generate,
        "real": stage_real,
        "listen": stage_listen,
        "augment": stage_augment,
        "train": stage_train,
        "package": stage_package,
    }
    for name in stages:
        print(f"\n===== {name} =====", flush=True)
        table[name](args, p)
    print("\nALL DONE" if args.stages == "all" else "\nSTAGES DONE")


def main():
    os.environ["MPLBACKEND"] = "Agg"  # Kaggle sets a notebook-only backend
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["setup", "run"])
    ap.add_argument("--stages", default="all")
    ap.add_argument("--data", default="")
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--no-fma", action="store_true")
    ap.add_argument("--n-samples", type=int, default=6000)
    ap.add_argument("--n-val", type=int, default=1000)
    ap.add_argument("--tts-batch", type=int, default=50)
    ap.add_argument("--real-copies", type=int, default=24)
    ap.add_argument("--real-neg-windows", type=int, default=1200)
    ap.add_argument("--steps", type=int, default=30000)
    ap.add_argument("--max-neg-weight", type=float, default=100)
    ap.add_argument("--target-fp", type=float, default=0.5)
    ap.add_argument("--b-pos", type=int, default=64)
    ap.add_argument("--b-neg", type=int, default=32)
    ap.add_argument("--b-acav", type=int, default=64)
    args = ap.parse_args()
    if args.cmd == "setup":
        setup(args)
    else:
        run(args)


if __name__ == "__main__":
    main()