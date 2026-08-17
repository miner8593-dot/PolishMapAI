from pathlib import Path
import zipfile

from polishmapai.mp import MpDocument
from polishmapai.ns2 import NavitelNs2Skin


SKIN = """Navitel Skin Version 1.6
colors {
BackgroundColorMap 0xCBD8C3
}
polygons {
white
0x50 0x0 -1 0xCBD8C3 none none black white Font0 -1/none x x 14
0x6c 0x0 -1 0xE3D9D2 0x848484 none black white Font0 -1/none x x 14
}
polylines {
ltgray
0x0 0xc 0x1 0x1 solid 8 0xdfb547/none/none 2 0xbe7f4d Font0 black white false none 14
}
"""


def test_load_navitel_ns2_cartographic_tables(tmp_path: Path):
    path=tmp_path/"Navitel.ns2"
    with zipfile.ZipFile(path,"w") as archive:archive.writestr("800x480x192/day.skin",SKIN)
    skin=NavitelNs2Skin.load(path)
    assert skin.version=="1.6" and skin.background=="#cbd8c3"
    forest=MpDocument.from_bytes(b"[POLYGON]\r\nType=0x50\r\nData0=(1,1),(1,2),(1,1)\r\n[END]\r\n").objects()[0]
    road=MpDocument.from_bytes(b"[POLYLINE]\r\nType=0x6\r\nRouteParam=4,1,0,0,0,0,0,0,0,0,0,0\r\nData0=(1,1),(2,2)\r\n[END]\r\n").objects()[0]
    assert skin.style_for(forest).fill=="#cbd8c3"
    assert skin.style_for(road).color=="#dfb547"
