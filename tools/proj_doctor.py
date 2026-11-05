"""Diagnose a PROJ data/library mismatch inside the image, then report what fixes CRS use.

Two vendored libproj copies (pyproj's and rasterio's GDAL) each demand a proj.db layout
newer than the other's data, and pyproj adds its own data directory to the search path at
C level, so a PROJ_DATA environment variable alone does not settle it. This prints the
facts and tests each candidate remedy instead of guessing.
"""
from __future__ import annotations

import glob
import os
import sqlite3
import subprocess
import sys

LAYOUT_CODES = ("DATABASE.LAYOUT.VERSION.MAJOR", "DATABASE.LAYOUT.VERSION.MINOR")


def layout(db_path: str) -> str:
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT code, value FROM proj_parameters WHERE code IN (?, ?)", LAYOUT_CODES
            ).fetchall()
        finally:
            con.close()
        return " ".join(f"{code.rsplit('.', 1)[-1].lower()}={value}" for code, value in rows) or "no layout rows"
    except Exception as exc:  # noqa: BLE001 - diagnostics must keep going
        return f"unreadable ({type(exc).__name__}: {exc})"


def probe(label: str) -> None:
    """Can rasterio build a UTM CRS right now? That is the only thing config.py needs."""
    code = (
        "import rasterio; from rasterio.crs import CRS;"
        "print('   crs ok', CRS.from_epsg(3435).to_epsg());"
        "import pyproj;"
        "print('   pyproj crs ok', pyproj.CRS.from_epsg(3435).to_epsg())"
    )
    print(f"[{label}]")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=os.environ)
    out = (result.stdout + result.stderr).strip().splitlines()
    for line in out[-4:]:
        print("   " + line)


def main() -> int:
    print("PROJ_DATA =", os.environ.get("PROJ_DATA"))
    print("PROJ_LIB  =", os.environ.get("PROJ_LIB"))

    import pyproj

    proj_version = getattr(pyproj.proj, "PROJ_VERSION_STRING", "?")
    print("pyproj", pyproj.__version__, "libproj", proj_version,
          "datadir", pyproj.datadir.get_data_dir())
    rasterio = __import__("rasterio")
    print("rasterio", rasterio.__version__, "gdal", rasterio.__gdal_version__)

    found = sorted(set(glob.glob("/usr/**/proj.db", recursive=True) + glob.glob("/app/**/proj.db", recursive=True)))
    for db in found:
        print(f"db {layout(db):28} {db}")
    if not found:
        print("no proj.db found under /usr or /app")

    probe("as built")

    candidate = "/usr/share/proj/proj.db"
    if os.path.exists(candidate) and pyproj.datadir.get_data_dir() != "/usr/share/proj":
        pyproj.datadir.set_data_dir("/usr/share/proj")
        os.environ["PROJ_DATA"] = "/usr/share/proj"
        os.environ["PROJ_LIB"] = "/usr/share/proj"
        probe("after pyproj.datadir.set_data_dir('/usr/share/proj')")

    return 0


if __name__ == "__main__":
    sys.exit(main())
