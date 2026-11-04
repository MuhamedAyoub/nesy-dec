"""Benchmark subjects for the Java pipeline and the analyzer configs built from them.

Scope decisions are recorded in results/SUBJECTS.md (sections 2, 3 and 5):
  * acmeair: the six modules listed in settings.gradle, wxs parsed from source
    (its objectgrid dependency is proprietary); acmeair-reporter excluded.
  * the two literature variants are not built; their classpath comes from a
    classpath-only pom per variant under java_pipeline/classpath/ that lists
    the libraries their own pom.xml declares (Maven Central equivalents).

Usage: python3 -m java_pipeline.subjects   (writes results/<app>/facts/config.json)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "datasets_java"
# JAVA_RESULTS_DIR redirects every output, so a from-scratch rerun (Phase 8)
# can be written next to the reported results and compared with them
OUT = Path(os.environ.get("JAVA_RESULTS_DIR", REPO / "results"))

# app id -> (source roots, classpath files written by the builds, role)
SUBJECTS: dict[str, dict] = {
    "jpetstore-6": {
        "roots": ["jpetstore-6/src/main/java"],
        "classpath_files": ["jpetstore-6/target/classpath.txt"],
        "set": "footnote",
    },
    "acmeair": {
        "roots": [f"acmeair/{m}/src/main/java" for m in (
            "acmeair-common", "acmeair-services", "acmeair-services-wxs",
            "acmeair-services-morphia", "acmeair-loader", "acmeair-webapp")],
        "classpath_files": [f"acmeair/{m}/build/classpath.txt" for m in (
            "acmeair-common", "acmeair-services", "acmeair-services-morphia",
            "acmeair-loader", "acmeair-webapp")],
        "set": "both",
    },
    "daytrader7": {
        "roots": ["sample.daytrader7/daytrader-ee7-ejb/src/main/java",
                  "sample.daytrader7/daytrader-ee7-web/src/main/java"],
        "classpath_files": ["sample.daytrader7/daytrader-ee7-ejb/target/classpath.txt",
                            "sample.daytrader7/daytrader-ee7-web/target/classpath.txt"],
        "set": "both",
    },
    "plantsbywebsphere": {
        "roots": ["sample.plantsbywebsphere/src/main/java"],
        "classpath_files": ["sample.plantsbywebsphere/target/classpath.txt"],
        "set": "footnote",
    },
    "lit-jpetstore": {
        "roots": ["KimJongSung__jPetStore/src/main/java"],
        "classpath_files": ["../java_pipeline/classpath/lit-jpetstore/classpath.txt"],
        "set": "literature",
    },
    "lit-pbw": {
        "roots": ["SteeleDesmond__sample.mono-to-ms.pbw-monolith/PlantsByWebSphere/src/main/java",
                  "SteeleDesmond__sample.mono-to-ms.pbw-monolith/pbw-lib/src/main/java"],
        "classpath_files": ["../java_pipeline/classpath/lit-pbw/classpath.txt"],
        "set": "literature",
    },
}


def classpath(app: str) -> list[str]:
    jars: list[str] = []
    for f in SUBJECTS[app]["classpath_files"]:
        p = DATA / f
        if not p.is_file():
            raise SystemExit(f"[subjects] missing classpath file {p}; build {app} first")
        for e in p.read_text().strip().split(":"):
            e = os.path.expanduser(e)   # the shipped classpath files use ~/.m2 in place of a home directory
            if e.endswith(".jar") and e not in jars:
                jars.append(e)
    return jars


def config(app: str) -> dict:
    return {
        "app": app,
        "sourceRoots": [str(DATA / r) for r in SUBJECTS[app]["roots"]],
        "classpath": classpath(app),
        "languageLevel": "JAVA_17",
    }


def facts_dir(app: str) -> Path:
    return OUT / app / "facts"


def main() -> None:
    for app in SUBJECTS:
        d = facts_dir(app)
        d.mkdir(parents=True, exist_ok=True)
        c = config(app)
        (d / "config.json").write_text(json.dumps(c, indent=2))
        print(f"{app:20s} roots={len(c['sourceRoots'])} jars={len(c['classpath'])} -> {d/'config.json'}")


if __name__ == "__main__":
    main()
