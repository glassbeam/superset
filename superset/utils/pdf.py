import logging
from io import BytesIO

from superset.commands.report.exceptions import ReportSchedulePdfFailedError

logger = logging.getLogger(__name__)

try:
    from PIL import Image
except ModuleNotFoundError:
    logger.error("PIL (Pillow) module is not installed. PDF generation from screenshots will fail.")
    Image = None  # Prevent NameError

def build_pdf_from_screenshots(snapshots: list[bytes]) -> bytes:
    if Image is None:
        raise ReportSchedulePdfFailedError("PIL is not installed. Cannot convert screenshots to PDF.")

    images = []
    for snap in snapshots:
        try:
            img = Image.open(BytesIO(snap))
            if img.mode == "RGBA":
                img = img.convert("RGB")
            images.append(img)
        except Exception as e:
            raise ReportSchedulePdfFailedError(f"Failed to process screenshot: {e}")

    logger.info("Building PDF from screenshots...")

    try:
        new_pdf = BytesIO()
        images[0].save(new_pdf, "PDF", save_all=True, append_images=images[1:])
        new_pdf.seek(0)
        return new_pdf.read()
    except Exception as ex:
        raise ReportSchedulePdfFailedError(
            f"Failed converting screenshots to PDF: {str(ex)}"
        ) from ex

