r"""Собирает «монстр»-датасет из всех датасетов проекта: дедуп по содержимому,
лучшая разметка на кадр, только кадры с головой + проверенный фон.

Зачем так, а не просто слить папки:
  • один кадр лежит в нескольких датасетах под разными именами → дедуп по md5
    содержимого, иначе train и val пересекутся (утечка);
  • один кадр размечен по-разному в разных датасетах (старая грубая vs новая
    точная makesense) → берём ЛУЧШУЮ (приоритет makesense, затем наличие головы);
  • кадры со старой разметкой без головы исключаем — иначе модель учится, что у
    врага «головы нет», и недоучивает класс EnemyHead;
  • фон (пустые кадры) фильтруем от тех, где автолейблер видит объект — там
    объект есть, но он не размечен (killcam/пропуски).

Запуск:  python -m scripts.build_monster_dataset
"""

import csv
import hashlib
import os
import random
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"C:\AI\dataset")
OUT = ROOT / "aimify_monster_20260612"
PRED_CSV = ROOT / "aimify_relabel_20260611_all" / "predictions.csv"
SKIP_TXT = {"classes.txt", "labels.txt", "notes.txt", "readme.txt"}
IMG_EXT = (".jpg", ".jpeg", ".png")
VAL_FRAC = 0.15
SEED = 42
HEAD_CLASS = 2


def md5(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def classes_of(lp: Path) -> set[int]:
    cs: set[int] = set()
    try:
        for ln in open(lp):
            t = ln.split()
            if len(t) >= 5:
                cs.add(int(float(t[0])))
    except OSError:
        pass
    return cs


def label_score(lp: Path):
    """Приоритет разметки: makesense > наличие головы > teammate > число классов."""
    cls = classes_of(lp)
    p = str(lp).replace("\\", "/")
    src = 2 if "labels_my-project-name" in p else (1 if "aimify_relabel" in p else 0)
    return (HEAD_CLASS in cls, src, 1 in cls, len(cls))


def main() -> None:
    img_by_stem: dict[str, list[Path]] = defaultdict(list)
    lbl_by_stem: dict[str, list[Path]] = defaultdict(list)
    for ds in ROOT.iterdir():
        if not ds.is_dir() or ds.name.startswith("aimify_monster"):
            continue
        for p in ds.rglob("*"):
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if ext in IMG_EXT:
                img_by_stem[p.stem].append(p)
            elif ext == ".txt" and p.name.lower() not in SKIP_TXT:
                lbl_by_stem[p.stem].append(p)

    # дедуп по содержимому: stem -> {md5}, md5 -> один путь картинки
    stem_hashes: dict[str, set[str]] = defaultdict(set)
    hash_img: dict[str, Path] = {}
    for stem, paths in img_by_stem.items():
        for p in paths:
            hh = md5(p)
            stem_hashes[stem].add(hh)
            hash_img.setdefault(hh, p)

    hash_labels: dict[str, list[Path]] = defaultdict(list)
    for stem, lbls in lbl_by_stem.items():
        for hh in stem_hashes.get(stem, ()):
            hash_labels[hh].extend(lbls)

    # подозрительный фон: автолейблер нашёл объект, а разметки нет
    suspicious: set[str] = set()
    if PRED_CSV.exists():
        for row in csv.DictReader(open(PRED_CSV, newline="")):
            if float(row["confidence"]) >= 0.5:
                suspicious.add(os.path.splitext(row["image"])[0])

    # keep: (img, label_or_None, hash). Берём кадр, если разметка из makesense
    # (точная — даже без головы это валидный кадр) ИЛИ содержит голову.
    keep: list[tuple[Path, Path | None, str]] = []
    skipped_nohead = skipped_susp = good_label = bg = 0
    for hh, img in hash_img.items():
        lbls = hash_labels.get(hh, [])
        nonempty = [lp for lp in lbls if classes_of(lp)]
        if nonempty:
            best = max(nonempty, key=label_score)
            is_makesense = "labels_my-project-name" in str(best).replace("\\", "/")
            if HEAD_CLASS in classes_of(best) or is_makesense:
                keep.append((img, best, hh)); good_label += 1
            else:
                skipped_nohead += 1  # только старая разметка без головы — исключаем
        elif lbls:  # есть пустой .txt = проверенный фон
            stems = {s for s, hs in stem_hashes.items() if hh in hs}
            if stems & suspicious:
                skipped_susp += 1
            else:
                keep.append((img, None, hh)); bg += 1
        # без .txt вообще — неизвестно, пропускаем

    if OUT.exists():
        shutil.rmtree(OUT)
    random.seed(SEED)
    random.shuffle(keep)
    n_val = round(len(keep) * VAL_FRAC)
    val = set(range(n_val))
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    for i, (img, lbl, hh) in enumerate(keep):
        sp = "val" if i in val else "train"
        name = f"{hh[:16]}_{img.stem[:40]}"  # уникальное имя (стемы пересекаются)
        shutil.copy2(img, OUT / "images" / sp / f"{name}{img.suffix.lower()}")
        out_lbl = OUT / "labels" / sp / f"{name}.txt"
        if lbl is not None:
            shutil.copy2(lbl, out_lbl)
        else:
            open(out_lbl, "w").close()

    (OUT / "data.yaml").write_text(
        f"path: {OUT.as_posix()}\ntrain: images/train\nval: images/val\n"
        "nc: 3\nnames: [enemy, teammate, EnemyHead]\n",
        encoding="utf-8",
    )
    print(f"labeled(head/makesense)={good_label} background={bg} "
          f"skipped_old_nohead={skipped_nohead} skipped_suspicious={skipped_susp}")
    print(f"total={len(keep)} train={len(keep)-n_val} val={n_val}")
    print(f"OUT={OUT}")


if __name__ == "__main__":
    main()
