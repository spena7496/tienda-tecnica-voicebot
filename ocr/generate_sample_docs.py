"""
Generate sample product datasheets (PDF) for the tienda técnica use case.

These stand in for the 3-5 real documents you would normally download.
They are rasterised + OCR'd by run_ocr.py, so the pipeline is a *real* OCR
pipeline (image -> text), not just reading a text PDF.

Run once:
    python generate_sample_docs.py
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "sample_docs"
OUT.mkdir(exist_ok=True)

# Each datasheet carries regex-friendly fields: reference (TEC-######),
# price (€), warranty (meses), release date (DD/MM/YYYY).
DATASHEETS = [
    {
        "file": "ficha_router_x200.pdf",
        "title": "Router WiFi 6 ProNet X200",
        "ref": "TEC-004521",
        "price": "89,90 €",
        "warranty": "24 meses",
        "release": "12/03/2024",
        "specs": [
            "Estandar: WiFi 6 (802.11ax), doble banda 2.4/5 GHz",
            "Velocidad maxima agregada: 3000 Mbps",
            "Puertos: 4x Gigabit LAN, 1x WAN, 1x USB 3.0",
            "Antenas: 4 externas de alta ganancia",
            "Consumo tipico: 12 W",
            "Dimensiones: 220 x 160 x 55 mm",
        ],
        "notes": "Compatible con malla ProNet Mesh. Firmware actualizable por OTA.",
    },
    {
        "file": "ficha_ssd_nova1tb.pdf",
        "title": "SSD NVMe Nova 1TB",
        "ref": "TEC-007810",
        "price": "74,50 €",
        "warranty": "60 meses",
        "release": "05/09/2023",
        "specs": [
            "Interfaz: PCIe 4.0 x4, NVMe 1.4",
            "Capacidad: 1 TB",
            "Lectura secuencial: 7000 MB/s",
            "Escritura secuencial: 5300 MB/s",
            "TBW: 600 TB",
            "Formato: M.2 2280",
        ],
        "notes": "Incluye disipador de aluminio. Garantia limitada de 5 anios o 600 TBW.",
    },
    {
        "file": "ficha_monitor_vision27.pdf",
        "title": "Monitor Vision 27 QHD",
        "ref": "TEC-003298",
        "price": "219,00 €",
        "warranty": "36 meses",
        "release": "21/11/2024",
        "specs": [
            "Panel: IPS 27 pulgadas, 2560 x 1440 (QHD)",
            "Frecuencia de refresco: 165 Hz",
            "Tiempo de respuesta: 1 ms (MPRT)",
            "Brillo: 350 cd/m2, HDR10",
            "Conectividad: 2x HDMI 2.0, 1x DisplayPort 1.4, USB-C",
            "Soporte: ajustable en altura, inclinacion y pivote",
        ],
        "notes": "Compatible con AMD FreeSync Premium. VESA 100x100.",
    },
    {
        "file": "ficha_teclado_mecanico_k85.pdf",
        "title": "Teclado Mecanico K85 RGB",
        "ref": "TEC-009142",
        "price": "64,99 €",
        "warranty": "24 meses",
        "release": "30/01/2025",
        "specs": [
            "Switches: mecanicos rojos lineales, hot-swap",
            "Formato: TKL (87 teclas), distribucion espanola",
            "Iluminacion: RGB por tecla, 16.8M colores",
            "Conexion: USB-C desmontable y Bluetooth 5.1",
            "Bateria: 4000 mAh, hasta 120 h sin RGB",
            "Keycaps: PBT double-shot",
        ],
        "notes": "Software de macros incluido. Reposamunecas magnetico de serie.",
    },
]


def build(ds: dict) -> None:
    path = OUT / ds["file"]
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 30 * mm

    c.setFont("Helvetica-Bold", 20)
    c.drawString(25 * mm, y, ds["title"])
    y -= 10 * mm

    c.setFont("Helvetica", 11)
    c.drawString(25 * mm, y, "TecnoStore - Ficha tecnica de producto")
    y -= 12 * mm

    c.setFont("Helvetica-Bold", 12)
    for label, key in [("Referencia", "ref"), ("Precio", "price"),
                       ("Garantia", "warranty"), ("Fecha de lanzamiento", "release")]:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(25 * mm, y, f"{label}:")
        c.setFont("Helvetica", 12)
        c.drawString(75 * mm, y, ds[key])
        y -= 8 * mm

    y -= 4 * mm
    c.setFont("Helvetica-Bold", 13)
    c.drawString(25 * mm, y, "Especificaciones")
    y -= 8 * mm
    c.setFont("Helvetica", 11)
    for spec in ds["specs"]:
        c.drawString(28 * mm, y, f"- {spec}")
        y -= 6.5 * mm

    y -= 4 * mm
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(25 * mm, y, ds["notes"])

    c.showPage()
    c.save()
    print(f"  wrote {path.name}")


if __name__ == "__main__":
    print(f"Generating {len(DATASHEETS)} datasheets into {OUT}/ ...")
    for ds in DATASHEETS:
        build(ds)
    print("Done.")
