import shutil
import sys
from pathlib import Path

assets_dir = Path(__file__).parent.parent.resolve() / "assets"


def configure_ocr_model():
    assets_ocr_dir = assets_dir / "MaaCommonAssets" / "OCR"
    if not assets_ocr_dir.is_dir():
        print(f"File Not Found: {assets_ocr_dir!r}")
        sys.exit(1)

    ocr_dir = assets_dir / "resource" / "model" / "ocr"

    shutil.copytree(
        assets_dir / "MaaCommonAssets" / "OCR" / "ppocr_v4" / "zh_cn",
        ocr_dir,
        dirs_exist_ok=True,
    )


if __name__ == "__main__":
    configure_ocr_model()

    print("OCR model configured.")
