import re
import urllib.request
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin


WEB_URL = "https://gamrentals.com/es/noticias"
BASE_URL = "https://gamrentals.com"
ARCHIVO_RSS = "gam.xml"


def descargar_pagina(url):
    solicitud = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "es-ES,es;q=0.9",
        },
    )

    with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
        return respuesta.read()


def limpiar_texto(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def extraer_fecha(soup):
    texto = limpiar_texto(soup.get_text(" ", strip=True))

    meses = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }

    coincidencia = re.search(
        r"(\d{1,2})\s+de\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
        r"septiembre|octubre|noviembre|diciembre)"
        r"\s+de\s+(\d{4})",
        texto,
        re.IGNORECASE,
    )

    if coincidencia:
        dia = int(coincidencia.group(1))
        mes = meses[coincidencia.group(2).lower()]
        anio = int(coincidencia.group(3))

        fecha = datetime(
            anio,
            mes,
            dia,
            8,
            0,
            tzinfo=timezone.utc,
        )

        return format_datetime(fecha)

    return None


def extraer_descripcion(soup):
    meta = soup.find(
        "meta",
        attrs={"name": re.compile("^description$", re.I)},
    )

    if meta and meta.get("content"):
        descripcion = limpiar_texto(meta["content"])

        if descripcion:
            return descripcion

    articulo = soup.find("article") or soup.find("main")

    if articulo:
        parrafos = articulo.find_all("p")

        for parrafo in parrafos:
            texto = limpiar_texto(parrafo.get_text(" ", strip=True))

            if len(texto) >= 80:
                return texto[:500]

    return "Noticia publicada por GAM."


def obtener_noticias():
    contenido = descargar_pagina(WEB_URL)
    soup = BeautifulSoup(contenido, "html.parser")

    noticias = []
    enlaces_vistos = set()

    rutas_excluidas = (
        "/es/noticias/general",
        "/es/noticias/blog",
        "/es/noticias/servicios",
        "/es/noticias/category/",
    )

    for encabezado in soup.select("h1, h2, h3"):
        enlace = encabezado.find("a", href=True)

        if enlace is None and encabezado.parent:
            enlace = encabezado.parent.find("a", href=True)

        if enlace is None:
            continue

        titulo = limpiar_texto(encabezado.get_text(" ", strip=True))
        url = urljoin(BASE_URL, enlace["href"]).split("#")[0].rstrip("/")

        if not titulo or len(titulo) < 15:
            continue

        if not url.startswith(f"{BASE_URL}/es/noticias/"):
            continue

        if any(ruta in url for ruta in rutas_excluidas):
            continue

        if url in enlaces_vistos:
            continue

        enlaces_vistos.add(url)

        try:
            detalle = descargar_pagina(url)
            soup_detalle = BeautifulSoup(detalle, "html.parser")

            titulo_detalle = soup_detalle.find("h1")

            if titulo_detalle:
                titulo = limpiar_texto(
                    titulo_detalle.get_text(" ", strip=True)
                )

            fecha = extraer_fecha(soup_detalle)
            descripcion = extraer_descripcion(soup_detalle)

        except Exception as error:
            print(f"No se pudo abrir {url}: {error}")
            fecha = None
            descripcion = "Noticia publicada por GAM."

        noticias.append(
            {
                "titulo": titulo,
                "url": url,
                "fecha": fecha,
                "descripcion": descripcion,
            }
        )

        if len(noticias) >= 30:
            break

    if not noticias:
        raise RuntimeError(
            "No se encontraron noticias en la página de GAM"
        )

    return noticias


def crear_rss(noticias):
    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
        },
    )

    canal = ET.SubElement(rss, "channel")

    ET.SubElement(canal, "title").text = "Noticias de GAM"
    ET.SubElement(canal, "link").text = WEB_URL
    ET.SubElement(canal, "description").text = (
        "Últimas noticias publicadas por GAM Rentals"
    )
    ET.SubElement(canal, "language").text = "es-es"

    ET.SubElement(
        canal,
        "{http://www.w3.org/2005/Atom}link",
        {
            "href": (
                "https://raw.githubusercontent.com/"
                "plis2100/rss-gam/main/gam.xml"
            ),
            "rel": "self",
            "type": "application/rss+xml",
        },
    )

    ahora = datetime.now(timezone.utc)
    ET.SubElement(canal, "lastBuildDate").text = format_datetime(ahora)

    for noticia in noticias:
        elemento = ET.SubElement(canal, "item")

        ET.SubElement(elemento, "title").text = noticia["titulo"]
        ET.SubElement(elemento, "link").text = noticia["url"]
        ET.SubElement(
            elemento,
            "guid",
            {"isPermaLink": "true"},
        ).text = noticia["url"]

        ET.SubElement(
            elemento,
            "description",
        ).text = noticia["descripcion"]

        if noticia["fecha"]:
            ET.SubElement(
                elemento,
                "pubDate",
            ).text = noticia["fecha"]

    arbol = ET.ElementTree(rss)
    ET.indent(arbol, space="  ")

    arbol.write(
        ARCHIVO_RSS,
        encoding="utf-8",
        xml_declaration=True,
    )


def main():
    noticias = obtener_noticias()
    crear_rss(noticias)

    if not Path(ARCHIVO_RSS).exists():
        raise RuntimeError("No se pudo crear el archivo RSS")

    print(
        f"RSS creada correctamente: "
        f"{ARCHIVO_RSS} ({len(noticias)} noticias)"
    )


if __name__ == "__main__":
    main()
