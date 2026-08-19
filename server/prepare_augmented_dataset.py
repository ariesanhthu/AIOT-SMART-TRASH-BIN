"""Prepare a reviewed, renamed, augmented train/validation/test image dataset.

The split is deliberately manifest-driven and deterministic. Validation and
test contain originals only; every pre-existing or generated augmentation and
its source lineage stay in train.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


LABELS = ("paper", "plastic", "organic")
LABEL_TO_ID = {label: index for index, label in enumerate(LABELS)}
SPLITS = ("train", "validation", "test")
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
EXISTING_AUGMENTATION = re.compile(
    r"^(?P<source>.+)__aug_v2_(?P<variant>\d{2})$"
)
SEED = 20260813
TARGET_TRAIN_PER_CLASS = 150

# These holdouts were selected after reviewing contact sheets of all 259 input
# files. Common visual object groups are represented in every split.
VALIDATION = {
    "organic": {
        "029cbe89-92f1-4d66-a857-5dbc8be06200",
        "174eb404-de45-41c8-926f-a0a3d817782b",
        "58705416-20d3-4458-aa50-16977a209e9e",
        "0fbc4754-ce81-4c56-94b7-bf4205ba1dfa",
        "31bf9d4a-5c8e-4780-a75e-cf05090b8a6b",
        "8e258721-91b6-47c6-99ba-365d2224cdfd",
    },
    "paper": {
        "01c454eb-99b9-4341-99cb-2bcb6ef2fdfc",
        "0e5b3bdc-d170-48fc-b51b-e98eaa5a2948",
        "1a9c1cdc-beaf-4a6a-b8bc-bc005188d77d",
        "32d970c8-9856-4e05-b143-4b746724ec76",
        "701719a3-bf67-44ce-a9a5-8bea9179ea36",
        "83d1d81b-af4e-4edd-873c-899e3ff3a910",
    },
    "plastic": {
        "0e2388bc-635a-4704-aebf-ee34fe70a5d8",
        "2e185fae-4482-41ee-b8ea-d6a090dd32f7",
        "6a300772-f7c2-4905-a435-fbda86b5e7df",
        "be1a672c-873b-4117-b7af-daa4599b8390",
        "7f459649-2df5-4551-b2e5-8010e3e69531",
        "9aacf7c8-789a-4f9e-ae6c-d60aaccc9f60",
    },
}

TEST = {
    "organic": {
        "4afd3248-c9b2-4404-b523-f770c2598710",
        "a4221828-f488-4c37-9bc1-174f092ebbc1",
        "eb5adf75-d0f9-4eb3-8f87-18c391eacfaa",
        "3de8f373-6b8e-4d8d-a302-543850723399",
        "96fb9347-0c45-43b9-a6fd-cb017402a3fb",
        "cc77529b-271c-4ef7-a047-fb9e8ddb9eb1",
    },
    "paper": {
        "073c6bbb-b467-4b12-b3c0-917e903ab36e",
        "0f733a16-8745-4c19-9904-f0b5c31b91fa",
        "1bec95d6-6a89-46a5-9314-b77b1f4575c5",
        "34707b0a-0f5d-4e02-b499-b5e28cfa7c29",
        "85dd1ad5-d54d-4ebf-95f1-bcb893d92e2d",
        "d6c607ff-e54d-4b58-9170-290051e6d6cf",
    },
    "plastic": {
        "2d923f14-4cc7-4855-b05d-712c80001af2",
        "5136d6c4-9577-4d3e-974a-5fe044dcc39b",
        "940300ac-7bef-4874-9565-9ed7d0fdd807",
        "d4ffff31-b85c-4a2f-9684-8fb528456543",
        "a6cbcabd-830a-4a57-aa0c-8e617d83193d",
        "ea832acc-9f32-4d48-9ad1-a9ad25667819",
    },
}

# Manual review found this paper-labelled image to be a clear plastic bottle.
EXCLUDED = {
    ("paper", "ae41156a-aa81-46b1-97d7-fb8f22cfdad6"): "probable plastic bottle mislabeled as paper",
}

ORGANIC_CUCUMBER = {
    "0fbc4754-ce81-4c56-94b7-bf4205ba1dfa",
    "1bbe3524-aed4-4163-b2d9-8368fc54429f",
    "2ce2ee73-d1b7-4e56-87c3-d2bcbad90c45",
    "31bf9d4a-5c8e-4780-a75e-cf05090b8a6b",
    "37e8f933-178d-492c-b341-e40bb83dcc1e",
    "38901fe7-33a3-46e1-acd9-1e3113e395f0",
    "3de8f373-6b8e-4d8d-a302-543850723399",
    "6fe2210f-9266-462c-84d7-1810e02d795e",
    "8e258721-91b6-47c6-99ba-365d2224cdfd",
    "96fb9347-0c45-43b9-a6fd-cb017402a3fb",
    "b2585b68-2a94-480d-b8bd-c1a7e3f3e997",
    "c8b51d2b-e3d3-449b-a924-6ffb71cea846",
    "cc77529b-271c-4ef7-a047-fb9e8ddb9eb1",
    "dad1b121-8cd0-4287-9842-d0304bb62253",
    "e8cac581-2db8-498a-84dc-2ed19b828365",
    "ed180c1a-cd62-43e2-b424-c6143bd24eb8",
}
ORGANIC_CHILI = {
    "5b19b28c-d021-45ad-80a7-1609642dc69b",
    "afa1a907-bc43-4caf-8b03-16f253ade7f5",
}
ORGANIC_SMALL_FRUIT = {"6da78c88-e719-4ce5-8884-af59627a06e5"}

PLASTIC_FILM_UUID = {
    "7f459649-2df5-4551-b2e5-8010e3e69531",
    "9aacf7c8-789a-4f9e-ae6c-d60aaccc9f60",
    "a6cbcabd-830a-4a57-aa0c-8e617d83193d",
    "ea832acc-9f32-4d48-9ad1-a9ad25667819",
}

PAPER_CARDBOARD_IDS = {
    7, 8, 11, 12, 14, 15, 17, 18, 20, 22, 24, 26, 27, 31, 32, 38, 39,
    41, 46, 47, 48, 49, 51, 53, 54, 57, 61, 62, 63, 64, 65, 67, 69, 70,
    76, 78, 80, 81, 83, 84, 89, 93, 96, 99, 102, 105, 106, 107, 108,
    109, 110, 111, 112, 115, 117, 118, 119, 127, 131, 132, 133, 136,
}

# Stable alphabetical index from the visual review. It avoids embedding 62 UUIDs
# twice while remaining deterministic for this fixed source collection.
PAPER_NAMES = (
    "01c454eb-99b9-4341-99cb-2bcb6ef2fdfc", "073c6bbb-b467-4b12-b3c0-917e903ab36e",
    "08957b4d-b996-4f82-a385-44b1c59b5c64", "095c0464-1e85-4cad-848c-711add2f536a",
    "0a9aa7c9-7b20-4e9c-809f-87dfff800195", "0dc78700-cae4-49d7-af86-780d18f797df",
    "0e5b3bdc-d170-48fc-b51b-e98eaa5a2948", "0f733a16-8745-4c19-9904-f0b5c31b91fa",
    "0f77f478-f518-4d37-874b-d961485e3255", "12a0b7d0-7292-4b7d-bca0-ebefa53d7067",
    "1333e479-d829-4b34-9126-81d276a58278", "14645458-07eb-40f1-a49a-da76033c4dcb",
    "146b8896-93fd-40bf-8163-c9112058ded4", "193590c5-aa85-490c-8142-74db88c2a5c9",
    "1a9c1cdc-beaf-4a6a-b8bc-bc005188d77d", "1bec95d6-6a89-46a5-9314-b77b1f4575c5",
    "1e1e58a4-8052-48c3-a688-7170ddad2e3b", "211fb8cf-5c52-4d08-b5eb-1d775a89d1c8",
    "22f1398d-3ac0-43db-a55f-03defe8b04ab", "25fd15f0-f9b1-405f-a2d4-ca23caccb2ed",
    "269464c7-a65a-46ca-b8e3-a97c1431b28a", "27e3daf1-04a7-47f0-a343-5a9c34e4c141",
    "28bba1f0-ed43-4a0d-b5fd-0b66fd8fe928", "2922f4ef-e8ef-4b23-8bc4-c4da6a4f7c7a",
    "2b8d6ef5-b12c-46e3-ab1e-5f0d5bcb3b01", "2d0c8728-71b1-47c9-a8f9-5e11a8ad54a6",
    "3084c9fd-bb4d-4e7f-86b0-a3b4b6c91616", "3192dd94-fba9-4109-b0f0-cf2ffe513e5f",
    "32d970c8-9856-4e05-b143-4b746724ec76", "34707b0a-0f5d-4e02-b499-b5e28cfa7c29",
    "37035b7b-16f0-46b5-ace9-9c43e1ed4d71", "3a34ee2f-4cd6-4e18-af60-fbbab8355348",
    "3ae52a7d-41a2-4619-ad53-7c332e35c7bb", "3f379179-6410-4c78-a3c3-6f945e407d92",
    "3f6e0572-f9fc-4b17-a234-74b22244b9d3", "3fef7537-8d5b-47c2-bb1c-48e3fc4f4122",
    "40522739-479c-4ab5-9152-a43f4fd12987", "477026dc-2dee-4e4c-8b5a-848be3db40f3",
    "479328cb-ca6c-49d8-9d83-f1562a554366", "49e8e6bd-f15b-4ac9-91c7-a722994491a6",
    "4af49b0a-12ac-4966-8b08-b6b74194a8e6", "4bbba8c5-af2d-45b5-9969-dfd692b4ce3b",
    "4c11fec1-f14d-498d-9fbd-c48bebd39757", "50a368bf-5edc-49f0-88b4-eaed0317a404",
    "51d01d35-9910-443b-bfe3-df075fc920fc", "51f36e9d-13cf-478a-8c2f-8b9cef7cc40a",
    "54e9ee62-7455-48de-92c6-de933012614d", "55bd0adb-1968-4d13-91e8-96c6ba32047c",
    "5f96feed-cbbe-4406-b75c-f77f62db432a", "61ebaa35-9755-4adb-8d93-ee7376fa563f",
    "64f154cc-b457-4ca7-af72-3c8249011c4b", "6797fa38-6af4-49d7-a26d-7a0d0b1a7ada",
    "68579680-1a53-45da-9916-11bae6282076", "6952c088-edc5-43df-98fb-9e98768e3a94",
    "6b567f18-8076-4c0b-93ff-3cfb6df5e258", "6eb401c5-ed18-4be3-91c1-b153fef1b4c6",
    "701719a3-bf67-44ce-a9a5-8bea9179ea36", "7426a024-1c6d-4dc8-98b1-27236d5aedb3",
    "75083768-ebd8-472e-afb7-e0f42423a6ad", "759d3cbb-dfc3-470a-b9da-641f7c5b328a",
    "773e34c7-0ff2-4dba-affa-d26313a6250e", "78764399-aa01-4a12-97b0-1043e905548d",
    "7a3256cc-dde3-46c6-a975-88897ae6d98e", "7be06600-0fbb-4b17-8aeb-dcd034dc0868",
    "7d9f459b-aa7e-4ef5-a915-7623d4076be2", "7e6a3c04-9698-4b46-9900-ae538812c20f",
    "7fbb9fe7-63df-4ebc-a4b3-2426cf548899", "83d1d81b-af4e-4edd-873c-899e3ff3a910",
    "84deb629-fad4-4945-abe6-cac9dcf726cc", "85dd1ad5-d54d-4ebf-95f1-bcb893d92e2d",
    "8641afbf-7b01-4fff-8666-9efb81b55e13", "8686cc84-b144-470d-bf9c-672b674e9a20",
    "8efab3bb-3881-4cae-851d-65e14cfa0d47", "8f908485-4c7d-4a00-8ed8-c0b9dfa31430",
    "904f6d8a-b900-435d-8820-a9170cf3932f", "9367b7f0-bf66-4487-8fec-22ae681fb1d5",
    "98c24a84-9234-4e56-a602-f424b604edb3", "99be9226-a986-4a1b-a68c-4faa0d476a0e",
    "9be5a8d8-61db-4ac1-bcdc-d8d146f806ed", "9c43d53d-6e50-4f02-9c08-cf2342898dc0",
    "9d205c38-ac1a-4fb1-8113-ae94ac91dccf", "a1259918-a359-49bd-851a-d3bfb821a634",
    "a21d2a52-81d7-4884-8534-7ae17ed4149f", "a31abf1a-1ba2-4e7f-8df4-23564c4bf558",
    "a59c2028-effa-4308-8b86-5b38c8a2afa6", "a6b7fe8e-ee2b-47be-8b44-e13baed2adf6",
    "ae41156a-aa81-46b1-97d7-fb8f22cfdad6", "af7d875b-c7cf-411c-bed7-8261a4d346e8",
    "b02c7af6-3c13-4a11-84db-a3bd2761ce08", "b0fa030b-a9f0-4df8-b236-212c1e8dcaa5",
    "b22bb84d-1cf7-46ad-b4d0-22cdf10d932d", "b2d6358d-5b99-4e7e-be98-5a3f92c8310d",
    "b4fe11ce-1020-4f3c-a792-3853c122c0b8", "b7bcf8af-23dd-4ab6-bc66-3e33db394217",
    "b80189b8-83b3-4f8b-9191-3abd9093a1b4", "b83e7b12-2e7f-4908-9152-236192a86184",
    "baa362a3-05f3-4d6c-a1d3-6aac7e049b1f", "bbbbbe07-2e49-4753-a7b7-ace87482c456",
    "bd213f5c-1bd0-4b81-9217-d54f0b51c050", "be40c2d7-39ff-44d4-8621-7c5b01b2fee9",
    "c07ec094-d5b7-478c-9164-b04fe0897de0", "c55e2c3b-5857-4090-b51b-a02080526a51",
    "c6a15a9a-bd2b-4cbb-bd8a-57640244d3b7", "caa69a0d-25ae-488b-9664-e7dee488add4",
    "cc4ab3bf-2d21-4d39-a432-5c15515bfb7f", "cfa0bc8c-16da-40c7-9941-4edf0c62076b",
    "d4f5f8f8-8660-40a6-9a71-20afae2c17b5", "d6c607ff-e54d-4b58-9170-290051e6d6cf",
    "dec328cf-2c34-4f85-8b98-7ce685f993b1", "e0e3ac9f-1dac-46a9-8732-42aefebdc35d",
    "e10977ee-9ada-43cf-9ee8-b896085d36ac", "e430b787-a041-4620-be64-a0acccccd227",
    "e49dbf71-1c4c-4432-8f77-620e2b66e873", "e8c93367-7b40-42e5-926a-f8832a6589e5",
    "e91fd5f8-66e2-4abb-ae22-d909158c112f", "e9dd6578-4b15-4a72-9c0a-32e66b6ba58e",
    "eb675384-3315-40da-a4cb-a2f9332bba69", "ecb21d6d-d87b-4bd3-867f-9e690dabc8c3",
    "ed01d071-f456-4531-b89e-393ff9d48030", "edea9fa3-acb3-40d5-9eaf-6473bcdf41b2",
    "eeb59ade-372f-428d-bf0f-a1a47c3180ae", "f027ccf5-ade4-49ef-8fc1-1ece900c0cd1",
    "f0fc7621-4861-4e0f-a6e5-78982f4e4d6c", "f2513e44-5d15-42bb-aae5-5e19d866d0e5",
    "f3f964a3-065a-4b82-8a45-9eefc18b845e", "f6b07b56-00b3-4c43-b16d-6d35d7a759b5",
    "f80a1882-d4a1-4141-9d28-41c94cba8bc2", "f890c3ed-70be-433f-b8a8-249345c6fa72",
    "fc87e31a-5aff-44b9-9d8c-453e19120835", "fcb840f7-bd50-486f-b397-703b44bb5441",
    "fcd246df-8539-424d-b417-36c64d269d89", "fd4ef339-4664-448f-a422-25b9f11c3cc7",
    "fdc7606e-699d-4b1b-bda0-d468c1afabab", "fe292d4a-8a27-47e1-b617-11421758474e",
    "fe45d128-a7df-47cf-96cc-fbe51ea6ccfe", "fe8b5593-461d-4af0-8f64-651ee922c975",
)
PAPER_CARDBOARD = {PAPER_NAMES[index - 1] for index in PAPER_CARDBOARD_IDS}

MANIFEST_FIELDS = (
    "relative_path", "split", "label", "label_id", "kind", "visual_group",
    "source_group", "source_relative_path", "source_name", "augmentation",
    "source_sha256", "sha256", "width", "height",
)


@dataclass(frozen=True)
class Source:
    path: Path
    label: str
    name: str
    kind: str
    source_name: str
    source_group: str
    visual_group: str
    sha256: str
    width: int
    height: int


def parse_args() -> argparse.Namespace:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=here)
    parser.add_argument("--output", type=Path, default=here / "dataset_augmented_v9")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--target-train", type=int, default=TARGET_TRAIN_PER_CLASS)
    parser.add_argument(
        "--replace-output",
        action="store_true",
        help="atomically replace this script's existing output directory",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_root = args.input.resolve()
    output_root = args.output.resolve()
    if output_root.exists() and not args.replace_output:
        raise FileExistsError(f"Output already exists; refusing to overwrite: {output_root}")
    if output_root.parent != input_root:
        raise ValueError("Output must be a direct child of the input server-tmp directory")
    sources, excluded_rows = scan_sources(input_root)
    validate_review_contract(sources)

    staging = output_root.parent / f".{output_root.name}.staging-{uuid.uuid4().hex}"
    backup = output_root.parent / f".{output_root.name}.backup-{uuid.uuid4().hex}"
    try:
        for split in SPLITS:
            for label in LABELS:
                (staging / split / label).mkdir(parents=True, exist_ok=False)
        rows = materialize(sources, staging, args.seed, args.target_train)
        stats = validate_and_summarize(rows, staging, sources, excluded_rows, args)
        write_manifest(staging / "manifest.csv", rows)
        stats["manifest_sha256"] = sha256(staging / "manifest.csv")
        (staging / "stats.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (staging / "README.md").write_text(
            build_report(stats), encoding="utf-8"
        )
        if output_root.exists():
            output_root.replace(backup)
        try:
            staging.replace(output_root)
        except BaseException:
            if backup.exists() and not output_root.exists():
                backup.replace(output_root)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    except BaseException:
        if staging.exists() and staging.parent == output_root.parent and staging.name.startswith("."):
            shutil.rmtree(staging)
        raise
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def scan_sources(root: Path) -> tuple[list[Source], list[dict[str, str]]]:
    sources: list[Source] = []
    excluded_rows: list[dict[str, str]] = []
    hashes: dict[str, Path] = {}
    for label in LABELS:
        class_dir = root / label
        if not class_dir.is_dir():
            raise FileNotFoundError(class_dir)
        for path in sorted(class_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            name = path.stem
            reason = EXCLUDED.get((label, name))
            if reason:
                excluded_rows.append({
                    "relative_path": path.relative_to(root).as_posix(),
                    "label": label,
                    "reason": reason,
                })
                continue
            digest = sha256(path)
            if digest in hashes:
                raise ValueError(f"Exact input duplicate: {hashes[digest]} and {path}")
            hashes[digest] = path
            match = EXISTING_AUGMENTATION.fullmatch(name)
            if match:
                kind = "existing_augmentation"
                source_name = match.group("source")
            else:
                kind = "original"
                source_name = name
            with Image.open(path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                width, height = image.size
                image.getpixel((0, 0))
            sources.append(Source(
                path=path.resolve(),
                label=label,
                name=name,
                kind=kind,
                source_name=source_name,
                source_group=f"{label}/{source_name}",
                visual_group=visual_group(label, source_name),
                sha256=digest,
                width=width,
                height=height,
            ))
    return sources, excluded_rows


def visual_group(label: str, source_name: str) -> str:
    if label == "organic":
        if source_name in ORGANIC_CUCUMBER:
            return "cucumber"
        if source_name in ORGANIC_CHILI:
            return "chili"
        if source_name in ORGANIC_SMALL_FRUIT:
            return "small_fruit"
        return "lime"
    if label == "plastic":
        if source_name in PLASTIC_FILM_UUID or source_name.startswith("plastic_0"):
            return "plastic_film_or_bag"
        return "plastic_bottle"
    return "paper_cardboard_or_box" if source_name in PAPER_CARDBOARD else "paper_crumpled_or_sheet"


def assigned_split(source: Source) -> str:
    if source.kind == "existing_augmentation":
        return "train"
    if source.name in VALIDATION[source.label]:
        return "validation"
    if source.name in TEST[source.label]:
        return "test"
    return "train"


def validate_review_contract(sources: list[Source]) -> None:
    originals = {(s.label, s.name) for s in sources if s.kind == "original"}
    for label in LABELS:
        overlap = VALIDATION[label] & TEST[label]
        if overlap:
            raise ValueError(f"Holdout overlap for {label}: {sorted(overlap)}")
        expected = {(label, name) for name in VALIDATION[label] | TEST[label]}
        missing = expected - originals
        if missing:
            raise ValueError(f"Reviewed holdouts missing from input: {sorted(missing)}")
        if len(VALIDATION[label]) != 6 or len(TEST[label]) != 6:
            raise ValueError(f"Expected six validation and test originals for {label}")
    original_names = {(s.label, s.name) for s in sources if s.kind == "original"}
    for source in sources:
        if source.kind == "existing_augmentation" and (source.label, source.source_name) not in original_names:
            raise ValueError(f"Augmentation without original source: {source.path}")


def materialize(
    sources: list[Source], staging: Path, seed: int, target_train: int
) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    counters: dict[tuple[str, str, str], int] = {}
    source_rows: dict[tuple[str, str], dict[str, str | int]] = {}
    for source in sorted(sources, key=lambda s: (s.label, assigned_split(s), s.kind, s.name)):
        split = assigned_split(source)
        short_kind = "existing_aug" if source.kind == "existing_augmentation" else "original"
        key = (split, source.label, short_kind)
        counters[key] = counters.get(key, 0) + 1
        filename = f"{source.label}_{split}_{short_kind}_{counters[key]:03d}.jpg"
        destination = staging / split / source.label / filename
        shutil.copy2(source.path, destination)
        row = make_row(source, destination, staging, split, "none")
        rows.append(row)
        if source.kind == "original":
            source_rows[(source.label, source.name)] = row

    original_train = [
        source for source in sources
        if source.kind == "original" and assigned_split(source) == "train"
    ]
    for label in LABELS:
        current = sum(row["split"] == "train" and row["label"] == label for row in rows)
        needed = target_train - current
        if needed < 0:
            raise ValueError(
                f"Train target {target_train} is below existing {label} count {current}"
            )
        candidates = [s for s in original_train if s.label == label]
        lineage_count = {
            s.source_name: sum(
                item.label == label and item.source_name == s.source_name
                and assigned_split(item) == "train" for item in sources
            )
            for s in candidates
        }
        generated = {s.source_name: 0 for s in candidates}
        for aug_index in range(1, needed + 1):
            source = min(
                candidates,
                key=lambda s: (
                    lineage_count[s.source_name] + generated[s.source_name],
                    generated[s.source_name],
                    seeded_rank(seed, s.sha256),
                ),
            )
            generated[source.source_name] += 1
            # Cycle recipes across the class, not merely within one lineage.
            # Large classes may receive only one new variant per source, but
            # still need the full geometry/lighting/noise/blur coverage.
            recipe = AUGMENTATION_RECIPES[(aug_index - 1) % len(AUGMENTATION_RECIPES)]
            destination = staging / "train" / label / f"{label}_train_aug_{aug_index:03d}_{recipe}.jpg"
            variant_seed = variant_seed_for(seed, source.sha256, generated[source.source_name])
            save_augmentation(source.path, destination, variant_seed, recipe)
            rows.append(make_row(source, destination, staging, "train", recipe, kind="generated_augmentation"))
    return rows


def make_row(
    source: Source,
    destination: Path,
    root: Path,
    split: str,
    augmentation: str,
    *,
    kind: str | None = None,
) -> dict[str, str | int]:
    with Image.open(destination) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = image.size
        image.getpixel((0, 0))
    return {
        "relative_path": destination.relative_to(root).as_posix(),
        "split": split,
        "label": source.label,
        "label_id": LABEL_TO_ID[source.label],
        "kind": kind or source.kind,
        "visual_group": source.visual_group,
        "source_group": source.source_group,
        "source_relative_path": source.path.relative_to(root.parent).as_posix(),
        "source_name": source.source_name,
        "augmentation": augmentation,
        "source_sha256": source.sha256,
        "sha256": sha256(destination),
        "width": width,
        "height": height,
    }


AUGMENTATION_RECIPES = (
    "v9_color_noise", "rotate_zoom", "low_light_blur", "bright_warm",
    "cool_cast", "sensor_noise", "soft_focus_scale",
)


def save_augmentation(source: Path, destination: Path, seed: int, recipe: str) -> None:
    rng = np.random.default_rng(seed)
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    width, height = image.size
    border = tuple(int(v) for v in np.median(np.asarray(image), axis=(0, 1)))

    if recipe in {"rotate_zoom", "low_light_blur", "soft_focus_scale"}:
        scale = float(rng.uniform(0.82, 1.18))
        angle = float(rng.choice((-1.0, 1.0)) * rng.uniform(4.0, 14.0))
        image = scale_on_canvas(image, scale, rng, border)
        image = image.rotate(
            angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=border
        )

    pixels = np.asarray(image, dtype=np.float32) / 255.0
    if recipe == "v9_color_noise":
        gamma, exposure, contrast = rng.uniform(0.65, 1.55), rng.uniform(0.62, 1.48), rng.uniform(0.75, 1.30)
        channel_gain = rng.uniform(0.76, 1.24, size=(1, 1, 3))
        noise_sigma = rng.uniform(2.0, 7.0) / 255.0
    elif recipe == "low_light_blur":
        gamma, exposure, contrast = rng.uniform(1.20, 1.62), rng.uniform(0.58, 0.80), rng.uniform(0.82, 1.08)
        channel_gain = rng.uniform(0.88, 1.08, size=(1, 1, 3))
        noise_sigma = rng.uniform(3.0, 8.0) / 255.0
    elif recipe == "bright_warm":
        gamma, exposure, contrast = rng.uniform(0.68, 0.92), rng.uniform(1.10, 1.42), rng.uniform(0.88, 1.18)
        channel_gain = np.array([[[rng.uniform(1.08, 1.22), rng.uniform(0.96, 1.08), rng.uniform(0.74, 0.92)]]])
        noise_sigma = rng.uniform(1.0, 4.0) / 255.0
    elif recipe == "cool_cast":
        gamma, exposure, contrast = rng.uniform(0.82, 1.22), rng.uniform(0.82, 1.18), rng.uniform(0.86, 1.18)
        channel_gain = np.array([[[rng.uniform(0.76, 0.92), rng.uniform(0.96, 1.08), rng.uniform(1.08, 1.24)]]])
        noise_sigma = rng.uniform(1.0, 5.0) / 255.0
    elif recipe == "sensor_noise":
        gamma, exposure, contrast = rng.uniform(0.90, 1.12), rng.uniform(0.88, 1.14), rng.uniform(0.90, 1.16)
        channel_gain = rng.uniform(0.92, 1.08, size=(1, 1, 3))
        noise_sigma = rng.uniform(7.0, 14.0) / 255.0
    else:
        gamma, exposure, contrast = rng.uniform(0.86, 1.18), rng.uniform(0.86, 1.18), rng.uniform(0.86, 1.18)
        channel_gain = rng.uniform(0.90, 1.10, size=(1, 1, 3))
        noise_sigma = rng.uniform(1.0, 5.0) / 255.0

    pixels = np.power(np.clip(pixels, 0.0, 1.0), float(gamma)) * float(exposure)
    mean = pixels.mean(axis=(0, 1), keepdims=True)
    pixels = (pixels - mean) * float(contrast) + mean
    pixels *= channel_gain.astype(np.float32)
    pixels += rng.normal(0.0, noise_sigma, size=pixels.shape).astype(np.float32)
    image = Image.fromarray(np.rint(np.clip(pixels, 0.0, 1.0) * 255.0).astype(np.uint8), "RGB")
    if recipe == "low_light_blur":
        image = image.filter(ImageFilter.GaussianBlur(radius=float(rng.uniform(0.8, 1.6))))
    elif recipe == "soft_focus_scale":
        image = image.filter(ImageFilter.GaussianBlur(radius=float(rng.uniform(0.5, 1.1))))
    elif recipe == "rotate_zoom":
        image = ImageEnhance.Sharpness(image).enhance(float(rng.uniform(0.90, 1.12)))
    image.save(destination, format="JPEG", quality=94, optimize=True)
    if image.size != (width, height):
        raise ValueError(f"Augmentation changed output dimensions: {destination}")


def scale_on_canvas(
    image: Image.Image, scale: float, rng: np.random.Generator, fill: tuple[int, int, int]
) -> Image.Image:
    width, height = image.size
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    resized = image.resize((new_width, new_height), Image.Resampling.BICUBIC)
    jitter_x = int(rng.uniform(-0.04, 0.04) * width)
    jitter_y = int(rng.uniform(-0.04, 0.04) * height)
    if scale >= 1.0:
        left = max(0, min(new_width - width, (new_width - width) // 2 + jitter_x))
        top = max(0, min(new_height - height, (new_height - height) // 2 + jitter_y))
        return resized.crop((left, top, left + width, top + height))
    canvas = Image.new("RGB", (width, height), fill)
    x = max(0, min(width - new_width, (width - new_width) // 2 + jitter_x))
    y = max(0, min(height - new_height, (height - new_height) // 2 + jitter_y))
    canvas.paste(resized, (x, y))
    return canvas


def validate_and_summarize(
    rows: list[dict[str, str | int]],
    root: Path,
    sources: list[Source],
    excluded_rows: list[dict[str, str]],
    args: argparse.Namespace,
) -> dict:
    counts = {
        split: {
            label: sum(r["split"] == split and r["label"] == label for r in rows)
            for label in LABELS
        }
        for split in SPLITS
    }
    expected = {
        "train": {label: args.target_train for label in LABELS},
        "validation": {label: 6 for label in LABELS},
        "test": {label: 6 for label in LABELS},
    }
    if counts != expected:
        raise ValueError(f"Unexpected split counts: {counts}")

    seen_hashes: dict[str, str] = {}
    group_splits: dict[str, set[str]] = {}
    for row in rows:
        path = root / str(row["relative_path"])
        digest = sha256(path)
        if digest != row["sha256"]:
            raise ValueError(f"Checksum mismatch: {path}")
        if digest in seen_hashes:
            raise ValueError(f"Exact output duplicate: {seen_hashes[digest]} and {path}")
        seen_hashes[digest] = str(path)
        group_splits.setdefault(str(row["source_group"]), set()).add(str(row["split"]))
        if row["split"] != "train" and row["kind"] != "original":
            raise ValueError(f"Augmentation outside train: {path}")
        with Image.open(path) as opened:
            opened.verify()
    leakage = {group: sorted(splits) for group, splits in group_splits.items() if len(splits) > 1}
    if leakage:
        raise ValueError(f"Source lineage leakage: {leakage}")

    visual_distribution = {
        split: {
            label: {
                group: sum(
                    row["split"] == split and row["label"] == label
                    and row["visual_group"] == group for row in rows
                )
                for group in sorted({str(r["visual_group"]) for r in rows if r["label"] == label})
            }
            for label in LABELS
        }
        for split in SPLITS
    }
    original_distribution = {
        split: {
            label: {
                group: sum(
                    row["split"] == split and row["label"] == label
                    and row["visual_group"] == group and row["kind"] == "original"
                    for row in rows
                )
                for group in sorted({str(r["visual_group"]) for r in rows if r["label"] == label})
            }
            for label in LABELS
        }
        for split in SPLITS
    }
    common_groups = {
        "paper": ["paper_cardboard_or_box", "paper_crumpled_or_sheet"],
        "plastic": ["plastic_bottle", "plastic_film_or_bag"],
        "organic": ["cucumber", "lime"],
    }
    for label, groups in common_groups.items():
        for group in groups:
            for split in SPLITS:
                if original_distribution[split][label][group] == 0:
                    raise ValueError(f"Missing common visual group {label}/{group} in {split}")

    kind_counts = {
        split: {
            kind: sum(r["split"] == split and r["kind"] == kind for r in rows)
            for kind in ("original", "existing_augmentation", "generated_augmentation")
        }
        for split in SPLITS
    }
    return {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "seed": args.seed,
        "labels": list(LABELS),
        "class_to_index": LABEL_TO_ID,
        "input_images_reviewed": len(sources) + len(excluded_rows),
        "input_images_used": len(sources),
        "excluded_after_review": excluded_rows,
        "counts": counts,
        "kind_counts": kind_counts,
        "total_output_images": len(rows),
        "visual_distribution_all_files": visual_distribution,
        "visual_distribution_originals": original_distribution,
        "split_strategy": "manual visual subtype stratification; class-balanced holdouts; source-lineage isolation",
        "augmentation_policy": {
            "train_only": True,
            "materialized": True,
            "generated_from_originals_only": True,
            "recipes": list(AUGMENTATION_RECIPES),
            "operations": ["V9-style gamma/exposure/contrast/channel cast", "rotation", "scale/resize on canvas", "translation jitter", "Gaussian sensor noise", "Gaussian blur"],
            "output_dimensions": [320, 240],
        },
        "checks": {
            "decoded_images": len(rows),
            "exact_duplicate_outputs": 0,
            "source_group_leakage": 0,
            "augmentations_in_validation_or_test": 0,
            "class_balance_errors": 0,
            "common_visual_group_coverage_errors": 0,
        },
        "coverage_limitations": [
            "organic/chili has only 2 originals and organic/small_fruit has only 1; they remain train-only because independent three-way coverage is impossible without collecting more originals",
            "validation and test are small (6 originals per class); use a later independent capture session for a deployment-grade estimate",
        ],
    }


def build_report(stats: dict) -> str:
    counts = stats["counts"]
    kinds = stats["kind_counts"]
    original = stats["visual_distribution_originals"]
    lines = [
        "# Dataset augmented V9\n",
        "Dataset này được tạo sau khi review trực quan toàn bộ ảnh nguồn. Split không cắt ngẫu nhiên theo tên file. Ảnh validation/test chỉ là ảnh gốc; mọi augmentation cùng lineage chỉ nằm trong train.\n",
        "## Phân bố\n",
        "| Split | paper | plastic | organic | Tổng |",
        "|---|---:|---:|---:|---:|",
    ]
    for split in SPLITS:
        values = counts[split]
        lines.append(f"| {split} | {values['paper']} | {values['plastic']} | {values['organic']} | {sum(values.values())} |")
    lines.extend(["", "## Loại file", "", "| Split | Gốc | Augment có sẵn | Augment mới |", "|---|---:|---:|---:|"])
    for split in SPLITS:
        values = kinds[split]
        lines.append(f"| {split} | {values['original']} | {values['existing_augmentation']} | {values['generated_augmentation']} |")
    lines.extend(["", "## Coverage ảnh gốc theo nhóm vật thể", ""])
    for label in LABELS:
        lines.append(f"### {label}\n")
        groups = original["train"][label].keys()
        lines.extend(["| Nhóm | train | validation | test |", "|---|---:|---:|---:|"])
        for group in groups:
            lines.append(f"| {group} | {original['train'][label][group]} | {original['validation'][label][group]} | {original['test'][label][group]} |")
        lines.append("")
    lines.extend([
        "## Augmentation",
        "",
        "Ảnh mới được lưu vật lý ở `train/` với 7 recipe luân phiên: màu/ánh sáng kiểu V9, xoay + zoom/resize, low-light + blur, warm/bright, cool cast, sensor noise và soft-focus + scale. Kích thước đầu ra giữ 320×240.",
        "",
        "## Audit",
        "",
        "- Exact duplicate output: 0.",
        "- Source-group leakage: 0.",
        "- Augmentation trong validation/test: 0.",
        "- Mỗi class trong train có đúng 150 ảnh; validation/test có 6 ảnh gốc/class.",
        "- Các nhóm phổ biến xuất hiện ở cả ba split: lime/cucumber, bottle/film, cardboard/crumpled-paper.",
        "- Loại 1 ảnh `paper/ae41156a-aa81-46b1-97d7-fb8f22cfdad6.jpg` vì review cho thấy nhiều khả năng là chai nhựa trong suốt bị gán nhãn paper.",
        "",
        "## Giới hạn",
        "",
        "Ớt chỉ có 2 ảnh gốc và nhóm quả nhỏ chỉ có 1 ảnh gốc, nên không thể phủ độc lập train/validation/test. Các ảnh hiếm này được giữ ở train; cần chụp thêm ảnh gốc trước khi đánh giá riêng các nhóm đó. Validation/test hiện cũng còn nhỏ (6 ảnh/class).",
        "",
        "`manifest.csv` lưu lineage, nhóm vật thể, tên/path gốc, recipe, kích thước và SHA-256 của từng file. `stats.json` lưu toàn bộ phân bố và kết quả audit.\n",
    ])
    return "\n".join(lines)


def write_manifest(path: Path, rows: list[dict[str, str | int]]) -> None:
    rows.sort(key=lambda row: (SPLITS.index(str(row["split"])), str(row["label"]), str(row["relative_path"])))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def seeded_rank(seed: int, digest: str) -> str:
    return hashlib.sha256(f"{seed}\0{digest}".encode("ascii")).hexdigest()


def variant_seed_for(seed: int, digest: str, variant: int) -> int:
    payload = f"{seed}\0{digest}\0{variant}".encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
