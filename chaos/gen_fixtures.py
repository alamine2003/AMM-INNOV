"""Génère des PDF « scannés » valides (image + texte lisible par l'OCR) pour les scénarios."""
import io, sys
import img2pdf
from PIL import Image, ImageDraw

for i in range(12):
    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    lines = [
        "REPUBLIQUE DU SENEGAL - DIRECTION DE LA PHARMACIE",
        "AUTORISATION DE MISE SUR LE MARCHE",
        f"N° AMM : SN-2026-{1000 + i:04d}",
        "Produit : PRODUIT LAB 001 CPR B/10",
        f"Date de debut : 0{1 + i % 9}/03/2026",
        "Duree de validite : 5 ans",
    ]
    for k, line in enumerate(lines):
        draw.text((120, 200 + 90 * k), line, fill="black")
    buf = io.BytesIO(); img.save(buf, format="PNG")
    open(f"/out/scan{i:02d}.pdf", "wb").write(img2pdf.convert(buf.getvalue()))
print("ok")
