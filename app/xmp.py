"""XMP sidecar writing for Felicity (F6).

Pure XML helpers that build MWG-Regions face metadata into an .xmp sidecar, with no
database or API coupling. The scan worker (workers.py) calls these to write/refresh
sidecars next to tagged photos so other DAM apps (digiKam, Lightroom, etc.) can read
the face regions and names.

Regions follow the Metadata Working Group "Regions" schema: each face is a normalized
rectangle (centre x/y + width/height in 0..1) carrying the person's name. Coordinates
must be normalized against the same dimensions the bounding boxes were detected on (the
EXIF-transposed image), so the caller passes those dimensions in.
"""

import os
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional

XMP_NS = 'adobe:ns:meta/'
RDF_NS = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
MWG_NS = 'http://www.metadataworkinggroup.com/schemas/regions/'
ST_AREA_NS = 'http://ns.adobe.com/xmp/sType/Area#'
ST_DIM_NS = 'http://ns.adobe.com/xap/1.0/sType/Dimensions#'

# Register prefixes once so serialized output uses readable namespace prefixes
# (mwg-rs:, stArea:, ...) instead of ElementTree's auto-generated ns0/ns1.
ET.register_namespace('x', XMP_NS)
ET.register_namespace('rdf', RDF_NS)
ET.register_namespace('mwg-rs', MWG_NS)
ET.register_namespace('stArea', ST_AREA_NS)
ET.register_namespace('stDim', ST_DIM_NS)

_XPACKET_HEADER = "<?xpacket begin=\"﻿\" id=\"W5M0MpCehiHzreSzNTczkc9d\"?>\n"
_XPACKET_FOOTER = "\n<?xpacket end=\"w\"?>\n"


def _extract_xmp_xml(content: str) -> Optional[str]:
    """Pull the <xmpmeta> element out of a sidecar's text, ignoring the xpacket
    envelope and any surrounding whitespace. Handles both the x:xmpmeta prefixed
    form and a bare xmpmeta. Returns None if no xmpmeta element is present."""
    start = content.find('<x:xmpmeta')
    if start == -1:
        start = content.find('<xmpmeta')
    if start == -1:
        return None

    end = content.rfind('</x:xmpmeta>')
    if end != -1:
        end += len('</x:xmpmeta>')
    else:
        end = content.rfind('</xmpmeta>')
        if end != -1:
            end += len('</xmpmeta>')

    if end == -1 or end <= start:
        return None

    return content[start:end]


def load_existing_xmp_root(sidecar_path: str) -> ET.Element:
    """Return the parsed xmpmeta root of an existing sidecar so its other metadata is
    preserved, or a fresh empty xmpmeta/RDF/Description skeleton if the file is absent
    or unparseable."""
    if os.path.exists(sidecar_path):
        try:
            with open(sidecar_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            xml = _extract_xmp_xml(content)
            if xml:
                return ET.fromstring(xml)
        except Exception:
            pass

    root = ET.Element(f'{{{XMP_NS}}}xmpmeta')
    rdf = ET.SubElement(root, f'{{{RDF_NS}}}RDF')
    desc = ET.SubElement(rdf, f'{{{RDF_NS}}}Description')
    desc.set(f'{{{RDF_NS}}}about', '')
    return root


def upsert_mwg_regions(xmp_root: ET.Element, faces: List[Dict], width: int, height: int):
    """Replace the MWG Regions block on xmp_root with one region per face.

    Felicity owns the face-region block: any existing mwg-rs:Regions is removed and
    rebuilt from the given faces, so the sidecar always reflects the current tags.
    Each face dict needs bbox_x1/y1/x2/y2 (pixel coords in the detection image space)
    and name. width/height are that same image's dimensions.
    """
    rdf = xmp_root.find(f'.//{{{RDF_NS}}}RDF')
    if rdf is None:
        rdf = ET.SubElement(xmp_root, f'{{{RDF_NS}}}RDF')

    desc = rdf.find(f'./{{{RDF_NS}}}Description')
    if desc is None:
        desc = ET.SubElement(rdf, f'{{{RDF_NS}}}Description')
        desc.set(f'{{{RDF_NS}}}about', '')

    for child in list(desc):
        if child.tag == f'{{{MWG_NS}}}Regions':
            desc.remove(child)

    regions = ET.SubElement(desc, f'{{{MWG_NS}}}Regions')
    regions_desc = ET.SubElement(regions, f'{{{RDF_NS}}}Description')

    applied = ET.SubElement(regions_desc, f'{{{MWG_NS}}}AppliedToDimensions')
    applied_desc = ET.SubElement(applied, f'{{{RDF_NS}}}Description')
    applied_desc.set(f'{{{ST_DIM_NS}}}w', str(width))
    applied_desc.set(f'{{{ST_DIM_NS}}}h', str(height))
    applied_desc.set(f'{{{ST_DIM_NS}}}unit', 'pixel')

    region_list = ET.SubElement(regions_desc, f'{{{MWG_NS}}}RegionList')
    bag = ET.SubElement(region_list, f'{{{RDF_NS}}}Bag')

    w = float(width) if width else 1.0
    h = float(height) if height else 1.0

    for face in faces:
        x1 = float(face['bbox_x1'])
        y1 = float(face['bbox_y1'])
        x2 = float(face['bbox_x2'])
        y2 = float(face['bbox_y2'])

        # Clamp to the image; detection boxes can spill slightly past the edges.
        x1 = max(0.0, min(w, x1))
        x2 = max(0.0, min(w, x2))
        y1 = max(0.0, min(h, y1))
        y2 = max(0.0, min(h, y2))

        if x2 <= x1 or y2 <= y1:
            continue

        # MWG Area is the region centre plus its size, all normalized to 0..1.
        cx = ((x1 + x2) / 2.0) / w
        cy = ((y1 + y2) / 2.0) / h
        aw = (x2 - x1) / w
        ah = (y2 - y1) / h

        li = ET.SubElement(bag, f'{{{RDF_NS}}}li')
        li.set(f'{{{RDF_NS}}}parseType', 'Resource')

        name_el = ET.SubElement(li, f'{{{MWG_NS}}}Name')
        name_el.text = str(face['name'])

        type_el = ET.SubElement(li, f'{{{MWG_NS}}}Type')
        type_el.text = 'Face'

        area = ET.SubElement(li, f'{{{MWG_NS}}}Area')
        area.set(f'{{{ST_AREA_NS}}}x', f"{cx:.6f}")
        area.set(f'{{{ST_AREA_NS}}}y', f"{cy:.6f}")
        area.set(f'{{{ST_AREA_NS}}}w', f"{aw:.6f}")
        area.set(f'{{{ST_AREA_NS}}}h', f"{ah:.6f}")
        area.set(f'{{{ST_AREA_NS}}}unit', 'normalized')


def serialize_xmp(xmp_root: ET.Element) -> bytes:
    """Serialize an xmpmeta root to the full sidecar byte payload (xpacket envelope
    wrapping the indented XML). Returned as bytes so the caller can compare against an
    existing file and skip rewriting when nothing changed."""
    tree = ET.ElementTree(xmp_root)
    try:
        ET.indent(tree, space="  ")
    except Exception:
        pass

    xml_bytes = ET.tostring(xmp_root, encoding='utf-8', xml_declaration=True)
    xml_text = xml_bytes.decode('utf-8', errors='replace')
    return (_XPACKET_HEADER + xml_text + _XPACKET_FOOTER).encode('utf-8')
