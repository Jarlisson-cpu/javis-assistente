"""Baixa o modelo de voz offline (Vosk) em português para models/vosk.

Uso:
    python scripts/baixar_modelo_vosk.py            # modelo pequeno (~31 MB), rápido
    python scripts/baixar_modelo_vosk.py --grande   # modelo completo (~1,6 GB), mais preciso

Com o modelo instalado, `voice.stt_engine: auto` passa a usar o Vosk: o áudio
nunca sai do computador.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

MODELS = {
    "pequeno": "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip",
    "grande": "https://alphacephei.com/vosk/models/vosk-model-pt-fb-v0.1.1-20220516_2113.zip",
}
DESTINATION = Path(__file__).resolve().parent.parent / "models" / "vosk"


def _progress(blocks: int, block_size: int, total: int) -> None:
    if total > 0:
        done = min(blocks * block_size, total)
        sys.stdout.write(f"\r  {done / 1024**2:6.1f} / {total / 1024**2:.1f} MB")
        sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--grande", action="store_true", help="baixa o modelo completo (mais preciso, ~1,6 GB)")
    args = parser.parse_args()
    url = MODELS["grande" if args.grande else "pequeno"]

    if DESTINATION.exists() and any(DESTINATION.iterdir()):
        answer = input(f"Já existe um modelo em {DESTINATION}. Substituir? [s/N]: ").strip().lower()
        if answer not in ("s", "sim"):
            return

    with tempfile.TemporaryDirectory() as temp:
        archive = Path(temp) / "modelo.zip"
        print(f"Baixando {url}")
        urllib.request.urlretrieve(url, archive, _progress)
        print("\nExtraindo...")
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.namelist():
                target = (Path(temp) / "x" / member).resolve()
                if not target.is_relative_to((Path(temp) / "x").resolve()):
                    raise RuntimeError(f"Arquivo suspeito no zip: {member}")
            bundle.extractall(Path(temp) / "x")
        root = next((Path(temp) / "x").iterdir())
        if DESTINATION.exists():
            shutil.rmtree(DESTINATION)
        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root), DESTINATION)
    print(f"Modelo instalado em {DESTINATION}. Rode: python main.py --voice")


if __name__ == "__main__":
    main()
