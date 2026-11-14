
"""
DocuRecon - Clean Layout Experimental Sample

Creates a separate image-based synthetic PDF
with a corrected Part C timestamp field.

Original benchmark PDFs remain unchanged.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import pymupdf
import io


ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT / "sample_data" / "paperwork"
    / "DocuRecon_SYNTHETIC_937_SYN-937-002.pdf"
)

OUTPUT_DIR = (
    ROOT / "sample_data" / "layout_experiments"
)

OUTPUT = (
    OUTPUT_DIR
    / "DocuRecon_LAYOUT_CLEAN_937_SYN-937-002.pdf"
)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with pymupdf.open(SOURCE) as original:
        new_pdf = pymupdf.open()

        for page_number, page in enumerate(original):

            pix = page.get_pixmap(
                matrix=pymupdf.Matrix(2, 2),
                alpha=False,
            )

            image = Image.open(
                io.BytesIO(pix.tobytes("png"))
            ).convert("RGB")

            # Page 2 is Part C in this synthetic layout.
            if page_number == 1:
                draw = ImageDraw.Draw(image)

                width, height = image.size

                # Cover the existing time-cell region.
                # These are layout-specific coordinates.
                left = int(width * 0.86)
                top = int(height * 0.865)
                right = int(width * 0.96)
                bottom = int(height * 0.887)

                draw.rectangle(
                    (left, top, right, bottom),
                    fill="white",
                )

                font = ImageFont.truetype(
                    "arial.ttf", 28
                )

                draw.text(
                    (
                        int(width * 0.875),
                        int(height * 0.871),
                    ),
                    "12:42 PM",
                    fill="black",
                    font=font,
                )

            buffer = io.BytesIO()
            image.save(buffer, format="PNG")

            new_page = new_pdf.new_page(
                width=page.rect.width,
                height=page.rect.height,
            )

            new_page.insert_image(
                new_page.rect,
                stream=buffer.getvalue(),
            )

        new_pdf.save(OUTPUT)
        new_pdf.close()

    print(f"\nCreated: {OUTPUT}")


if __name__ == "__main__":
    main()
